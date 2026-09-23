"""Screener's run: resolve, parse, select evidence, assess, assemble.

Resolution happens before parsing for the
same reason Aligner resolves its comparisons first — fail before the expensive
part, and never let a run that assessed nothing look like a run that found nothing
wrong.

There is deliberately no reconciliation stage. The question bank's coordination map
has Translational Medicine and Clinical Pharmacology reach dose selection
independently and disagree in public at EOP1 and EOP2. A step that merged their
answers would destroy the one thing the bank was built to produce, so the absence
of that step is a design decision rather than an omission.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Sequence

from shared.batching import map_ordered

from services.chunker import (
    ContentBlock,
    TEXT_EXTRACTION_SUFFIXES,
    run_pipeline as chunker_run_pipeline,
)

from .contract import validate_result_contract
from .models import (
    DisciplineReview,
    DocumentInput,
    GateConfig,
    GateReview,
    LLMClientProtocol,
    QuestionAssessment,
    QuestionResolution,
    ReviewDocument,
    resolve_questions,
)
from .stages.assessor import assess_question
from .stages.selector import select_evidence

DEFAULT_MAX_OUTPUT_TOKENS = 16000
SUPPORTED_DOCUMENT_SUFFIXES = TEXT_EXTRACTION_SUFFIXES

# Documents are parsed concurrently but bounded: each parse is itself parallel
# inside chunker, and an unbounded fan-out here would multiply that.
MAX_PARALLEL_DOCUMENTS = 3

# Both model phases use this ceiling, sequentially. Pair selection has one flat
# queue, never a document pool nested inside a question pool.
MAX_PARALLEL_QUESTIONS = 6


def run_pipeline(
    documents: Sequence[DocumentInput],
    *,
    org: str,
    intervention_class: str,
    indication: str,
    config: GateConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
) -> GateReview:
    """Triage one gate's questions against a set of documents."""
    if not documents:
        raise ValueError("Screener needs at least one document to read.")

    doc_ids = [document.doc_id for document in documents]
    if any(not doc_id.strip() for doc_id in doc_ids):
        raise ValueError("Every document needs a non-empty doc_id.")
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("Two documents share a doc_id; filenames must be distinct.")
    for document in documents:
        if Path(document.file_path).suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise ValueError(f"Unsupported document format: {document.file_path}")

    # Resolve first: the one state config owns is decided here, with no I/O, and a
    # bank that has nothing to say about this product fails now rather than after
    # every document has been parsed.
    if progress_callback:
        progress_callback("resolve")
    resolutions = resolve_questions(config, intervention_class=intervention_class)

    if progress_callback:
        progress_callback("parse")

    def parse(document: DocumentInput) -> list[ContentBlock]:
        blocks = chunker_run_pipeline(
            str(Path(document.file_path)),
            doc_id=document.doc_id,
            org=org,
            intervention_class=intervention_class,
            indication=indication,
            accepted_suffixes=SUPPORTED_DOCUMENT_SUFFIXES,
        )
        if not blocks:
            raise ValueError(f"Document {document.doc_id!r} produced no readable content.")
        return blocks

    parsed = map_ordered(list(documents), parse, workers=MAX_PARALLEL_DOCUMENTS)
    # Source order is independent of worker completion order.
    blocks = [block for document_blocks in parsed for block in document_blocks]

    assessments = _assess(
        resolutions,
        parsed=parsed,
        blocks=blocks,
        indication=indication,
        intervention_class=intervention_class,
        llm_client=llm_client,
        max_tokens=max_tokens,
        progress_callback=progress_callback,
    )

    review = GateReview(
        gate_id=config.gate_id,
        gate_label=config.gate_label,
        bank_source=config.mirrors,
        documents=[
            ReviewDocument(doc_id=document.doc_id)
            for document in documents
        ],
        disciplines=_group(config, assessments),
        org=org,
        intervention_class=intervention_class,
        indication=indication,
        blocks=blocks,
    )
    return validate_result_contract(review, config)


def _assess(
    resolutions: list[QuestionResolution],
    *,
    parsed: list[list[ContentBlock]],
    blocks: list[ContentBlock],
    indication: str,
    intervention_class: str,
    llm_client: LLMClientProtocol,
    max_tokens: int,
    progress_callback=None,
) -> dict[str, QuestionAssessment]:
    """Read every question/document pair, then assess combined source selections."""
    settled: dict[str, QuestionAssessment] = {}
    queued: list[QuestionResolution] = []

    for item in resolutions:
        if item.queued:
            queued.append(item)
            continue
        assert item.state is not None
        settled[item.question.id] = item.question.assessment(item.state)

    pairs = [(item, document_blocks) for item in queued for document_blocks in parsed]
    completed = 0
    progress_lock = Lock()
    if progress_callback:
        progress_callback("select", completed=0, total=len(pairs))

    def select_pair(pair: tuple[QuestionResolution, list[ContentBlock]]) -> list[ContentBlock]:
        nonlocal completed
        item, document_blocks = pair
        selected = select_evidence(
            item.question, document_blocks,
            indication=indication, intervention_class=intervention_class,
            llm_client=llm_client, max_tokens=max_tokens,
        )
        if progress_callback:
            with progress_lock:
                completed += 1
                progress_callback("select", completed=completed, total=len(pairs))
        return selected

    selections = map_ordered(pairs, select_pair, workers=MAX_PARALLEL_QUESTIONS)
    selected_ids = {item.question.id: set() for item in queued}
    for (item, _), selected in zip(pairs, selections, strict=True):
        selected_ids[item.question.id].update(block.id for block in selected)

    if progress_callback:
        progress_callback("assess")

    def ask(resolution: QuestionResolution) -> QuestionAssessment:
        return assess_question(
            resolution.question,
            blocks=[block for block in blocks if block.id in selected_ids[resolution.question.id]],
            indication=indication,
            intervention_class=intervention_class,
            llm_client=llm_client,
            max_tokens=max_tokens,
        )

    for assessment in map_ordered(queued, ask, workers=MAX_PARALLEL_QUESTIONS):
        settled[assessment.id] = assessment
    return settled


def _group(
    config: GateConfig,
    assessments: dict[str, QuestionAssessment],
) -> list[DisciplineReview]:
    """Bank order, always: discipline sequence then question number.

    Nothing re-ranks. The author's sequence is the order, so two runs on one gate
    compare line by line and there is no weighting for anyone to argue with.
    """
    return [
        DisciplineReview(
            id=discipline.id,
            label=discipline.label,
            questions=[assessments[question.id] for question in discipline.questions],
        )
        for discipline in config.disciplines
    ]
