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
from typing import Sequence

from shared.batching import map_ordered

from services.chunker import (
    DOCUMENT_SUFFIXES,
    ContentBlock,
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
from .stages.assessor import assess_question, check_selection
from .stages.selector import check_document, select_evidence

# Documents are parsed concurrently but bounded: each parse is itself parallel
# inside chunker, and an unbounded fan-out here would multiply that.
MAX_PARALLEL_DOCUMENTS = 3

# Both model phases use this ceiling, sequentially. Pair selection has one flat
# queue, never a document pool nested inside a question pool.
#
# Twelve, measured through the gateway on 48 real selection calls (twelve documents):
# 93 s at 6, 63 s at 12, 66 s at 24. Past twelve the gateway is the limit, so more
# workers buy nothing; twelve also leaves two concurrent runs at a tested 24 in flight.
# Concurrency changes only when calls are made, never which calls or what they say.
MAX_PARALLEL_QUESTIONS = 12


def run_pipeline(
    documents: Sequence[DocumentInput],
    *,
    org: str,
    intervention_class: str,
    indication: str,
    config: GateConfig,
    llm_client: LLMClientProtocol,
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
        if Path(document.file_path).suffix.lower() not in DOCUMENT_SUFFIXES:
            raise ValueError(f"Unsupported document format: {document.file_path}")

    # Resolve first: the one state config owns is decided here, with no I/O, and a
    # bank that has nothing to say about this product fails now rather than after
    # every document has been parsed.
    if progress_callback:
        progress_callback("resolve")
    resolutions = resolve_questions(config, intervention_class=intervention_class)

    def parse(document: DocumentInput) -> list[ContentBlock]:
        blocks = chunker_run_pipeline(
            str(Path(document.file_path)),
            doc_id=document.doc_id,
            org=org,
            intervention_class=intervention_class,
            indication=indication,
        )
        if not blocks:
            raise ValueError(f"Document {document.doc_id!r} produced no readable content.")
        return blocks

    # Counted, so a run abandoned while it parses stops at the next document rather
    # than after every one: progress is where a closed stream is noticed.
    parsed = map_ordered(
        list(documents), parse, workers=MAX_PARALLEL_DOCUMENTS,
        on_progress=_reporter(progress_callback, "parse", len(documents)),
    )
    # Source order is independent of worker completion order.
    blocks = [block for document_blocks in parsed for block in document_blocks]

    assessments = _assess(
        resolutions,
        parsed=parsed,
        blocks=blocks,
        indication=indication,
        intervention_class=intervention_class,
        llm_client=llm_client,
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
    if queued:
        for document_blocks in parsed:
            check_document(document_blocks, indication=indication,
                           intervention_class=intervention_class)

    def select_pair(pair: tuple[QuestionResolution, list[ContentBlock]]) -> list[ContentBlock]:
        item, document_blocks = pair
        return select_evidence(
            item.question, document_blocks,
            indication=indication, intervention_class=intervention_class,
            llm_client=llm_client,
        )

    selections = map_ordered(
        pairs, select_pair, workers=MAX_PARALLEL_QUESTIONS,
        on_progress=_reporter(progress_callback, "select", len(pairs)),
    )
    selected_ids = {item.question.id: set() for item in queued}
    for (item, _), selected in zip(pairs, selections, strict=True):
        selected_ids[item.question.id].update(block.id for block in selected)

    evidence = {
        item.question.id: [block for block in blocks if block.id in selected_ids[item.question.id]]
        for item in queued
    }
    for item in queued:
        check_selection(item.question, evidence[item.question.id], indication=indication,
                        intervention_class=intervention_class)

    def ask(resolution: QuestionResolution) -> QuestionAssessment:
        return assess_question(
            resolution.question,
            blocks=evidence[resolution.question.id],
            indication=indication,
            intervention_class=intervention_class,
            llm_client=llm_client,
        )

    assessed = map_ordered(
        queued, ask, workers=MAX_PARALLEL_QUESTIONS,
        on_progress=_reporter(progress_callback, "assess", len(queued)),
    )
    for assessment in assessed:
        settled[assessment.id] = assessment
    return settled


def _reporter(progress_callback, stage: str, total: int):
    """Announce a fan-out stage at zero and hand back its per-item counter."""
    if not progress_callback:
        return None
    progress_callback(stage, completed=0, total=total)
    return lambda completed, total: progress_callback(stage, completed=completed, total=total)


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
