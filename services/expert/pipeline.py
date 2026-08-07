"""Expert's run: resolve, parse, assess, assemble.

Two code stages and one model stage. Resolution happens before parsing for the
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
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from .contract import validate_result_contract
from .models import (
    ContextItem,
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

DEFAULT_MAX_OUTPUT_TOKENS = 16000

# Documents are parsed concurrently but bounded: each parse is itself parallel
# inside chunker, and an unbounded fan-out here would multiply that.
MAX_PARALLEL_DOCUMENTS = 3

# One call per question, so throughput is fan-out. Matches Inspector's per-unit
# bound, since the calls are the same size and hit the same provider limits.
MAX_PARALLEL_QUESTIONS = 6


def run_pipeline(
    documents: Sequence[DocumentInput],
    *,
    org: str,
    intervention_class: str,
    indication: str,
    config: GateConfig,
    llm_client: LLMClientProtocol,
    context_items: Sequence[ContextItem] = (),
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
) -> GateReview:
    """Triage one gate's questions against a set of documents."""
    if not documents:
        raise ValueError("Expert needs at least one document to read.")

    items = list(context_items)
    _reject_duplicate_labels(items)

    # Resolve first: the one state config owns is decided here, with no I/O, and a
    # bank that has nothing to say about this product fails now rather than after
    # every document has been parsed.
    if progress_callback:
        progress_callback("resolve")
    resolutions = resolve_questions(config, intervention_class=intervention_class)

    # Resolve chunker configs before parsing, so a missing document configuration
    # fails at once rather than partway through a parallel parse.
    chunker_configs = [
        find_chunker_config(org, document.source_type, intervention_class)
        for document in documents
    ]

    if progress_callback:
        progress_callback("parse")

    def parse(pair: tuple[DocumentInput, object]) -> list[ContentBlock]:
        document, chunker_config = pair
        return chunker_run_pipeline(
            str(Path(document.file_path)),
            doc_id=document.doc_id,
            config=chunker_config,
            llm_client=llm_client,
            max_tokens=max_tokens,
            indication=indication,
        )

    parsed = map_ordered(
        list(zip(documents, chunker_configs)),
        parse,
        workers=MAX_PARALLEL_DOCUMENTS,
    )
    # Ordered by the order documents were supplied, so a rerun with the same inputs
    # produces a byte-identical result.
    blocks = [block for document_blocks in parsed for block in document_blocks]
    if not blocks and not items:
        raise ValueError(
            "Nothing readable was supplied: the documents produced no content and no "
            "context was pasted, so no question could be assessed."
        )

    if progress_callback:
        progress_callback("assess")
    assessments = _assess(
        resolutions,
        blocks=blocks,
        context_items=items,
        llm_client=llm_client,
        max_tokens=max_tokens,
    )

    review = GateReview(
        gate_id=config.gate_id,
        gate_label=config.gate_label,
        bank_source=config.mirrors,
        documents=[
            ReviewDocument(doc_id=document.doc_id, source_type=document.source_type)
            for document in documents
        ],
        disciplines=_group(config, assessments),
        context_labels=[item.label for item in items],
        org=org,
        intervention_class=intervention_class,
        indication=indication,
        blocks=blocks,
    )
    return validate_result_contract(review, config)


def _assess(
    resolutions: list[QuestionResolution],
    *,
    blocks: list[ContentBlock],
    context_items: list[ContextItem],
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> dict[str, QuestionAssessment]:
    """One assessment per applicable question, each against everything supplied.

    Every queued question sees the same material. That is what makes the run honest —
    nothing is withheld because of a guess about where its answer lives — and it is
    also what makes it affordable: an identical document context across every call is
    a cacheable prompt prefix, which a per-question subset could never be.
    """
    settled: dict[str, QuestionAssessment] = {}
    queued: list[QuestionResolution] = []

    for item in resolutions:
        if item.queued:
            queued.append(item)
            continue
        assert item.state is not None
        settled[item.question.id] = item.question.assessment(item.state)

    def ask(resolution: QuestionResolution) -> QuestionAssessment:
        return assess_question(
            resolution.question,
            blocks=blocks,
            context_items=context_items,
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


def _reject_duplicate_labels(items: list[ContextItem]) -> None:
    labels = [item.label.strip() for item in items]
    if any(not label for label in labels):
        raise ValueError("Every context item needs a label.")
    if len(set(labels)) != len(labels):
        raise ValueError(
            "Two context items share a label. Labels are how an answer names its "
            "source, so they must be distinct."
        )
