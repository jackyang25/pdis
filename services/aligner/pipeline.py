"""Aligner's entry point: identify documents, resolve comparisons, parse, compare.

Each comparison runs in two steps, and the split is the design: the reference
document's requirements are read once, then each requirement is judged separately
against the comparison document. Extraction is one call because how many requirements a
document states is a fact about the whole document; judgement is one call per
requirement because each verdict must stand on its own.

Note what is absent: no document count, no source type, no notion of which pair compares
to which. All of that is read from config, so supporting a new document type never
reaches this file — a new `edges` entry produces another comparison here without a line
changing.
"""

from __future__ import annotations

from typing import Sequence

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from shared.batching import map_ordered
from shared.request_budget import check_request

from .models import (
    AlignmentConfig,
    AlignmentDocument,
    AlignmentEdge,
    AlignmentFinding,
    AlignmentResult,
    DocumentInput,
    LLMClientProtocol,
    Requirement,
    document_role,
    resolve_edges,
)
from .contract import validate_result_contract
from .context import format_blocks, image_inputs
from .stages.assessor import assess_requirement
from .stages.requirements import extract_requirements

# Documents parse independently, so they parse at once. Bounded because a parse
# renders slides and pages, which is the memory-heavy part of a run.
MAX_PARALLEL_DOCUMENTS = 3

# Requirements are judged independently, so they are judged at once. The same bound
# Screener uses for its questions: enough to keep a run to about a minute, low enough that
# one run does not exhaust a shared rate limit.
MAX_PARALLEL_REQUIREMENTS = 6


def run_pipeline(
    documents: Sequence[DocumentInput],
    *,
    org: str,
    intervention_class: str,
    indication: str,
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    progress_callback=None,
) -> AlignmentResult:
    """Parse every document, then judge every requirement each comparison resolves.

    Comparisons are resolved before any parsing, so a set of documents that
    forms none fails immediately rather than after the expensive part.
    """
    if len(documents) < 2:
        raise ValueError("Aligner needs at least two documents to compare")
    doc_ids = [document.doc_id for document in documents]
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("Aligner documents must have distinct filenames")

    chunker_configs = {
        document.doc_id: find_chunker_config(
            org, document.source_type, intervention_class
        )
        for document in documents
    }
    identified = [
        AlignmentDocument(
            doc_id=document.doc_id,
            source_type=document.source_type,
            display_name=chunker_configs[document.doc_id].display_name,
        )
        for document in documents
    ]
    # Before parsing, not after: resolving no comparison is a configuration
    # mistake, and finding that out costs nothing here.
    edges = resolve_edges(config, identified)

    if progress_callback:
        progress_callback("parse", completed=0, total=len(documents))

    # Parse only. No Aligner stage reads a section label - a requirement is read out of
    # the whole reference document and judged against the whole comparison document - so
    # the section-mapping call Chunker makes when given a model was one per document,
    # spent on labels nothing read.
    def parse(document: DocumentInput) -> list[ContentBlock]:
        chunker_config = chunker_configs[document.doc_id]
        return chunker_run_pipeline(
            document.file_path,
            doc_id=document.doc_id,
            org=chunker_config.org,
            source_type=chunker_config.source_type,
            intervention_class=chunker_config.intervention_class,
            indication=indication,
        )

    parsed = dict(zip(doc_ids, map_ordered(
        documents, parse, workers=MAX_PARALLEL_DOCUMENTS,
        on_progress=_reporter(progress_callback, "parse"),
    )))

    findings = _compare_edges(
        edges,
        documents=identified,
        blocks_by_doc=parsed,
        config=config,
        llm_client=llm_client,
        progress_callback=progress_callback,
    )

    result = AlignmentResult(
        documents=identified,
        edges=edges,
        org=org,
        intervention_class=intervention_class,
        indication=indication,
        # Ordered by the documents as supplied rather than by completion, so two
        # identical runs produce byte-identical results.
        blocks=[block for document in documents for block in parsed[document.doc_id]],
        findings=findings,
    )
    return validate_result_contract(result, config)


def _reporter(progress_callback, stage: str):
    if progress_callback is None:
        return None
    return lambda completed, total: progress_callback(stage, completed=completed, total=total)


def _compare_edges(
    edges: Sequence[AlignmentEdge],
    *,
    documents: Sequence[AlignmentDocument],
    blocks_by_doc: dict[str, list[ContentBlock]],
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    progress_callback=None,
) -> list[AlignmentFinding]:
    """Every requirement of every comparison, judged.

    Two flat queues, each counted to its end. Every comparison's requirements are read
    first, so the second step knows how many requirements the whole run holds before
    judging any; then every requirement of every comparison is judged in one queue.
    Counting per comparison restarted the bar at zero for the second edge of a
    three-document run, so it went backwards halfway through.
    """
    source_types = {document.doc_id: document.source_type for document in documents}

    # Both stages send a whole document per request - extraction the reference, judgement
    # the comparison - so each document a comparison sends is measured before either runs.
    for doc_id in dict.fromkeys(
        doc_id for edge in edges for doc_id in (edge.reference_doc_id, edge.comparison_doc_id)
    ):
        document_blocks = blocks_by_doc[doc_id]
        check_request(f"Aligner's reading of {doc_id}", text=format_blocks(document_blocks),
                      images=image_inputs(document_blocks))

    def read(edge: AlignmentEdge) -> list[Requirement]:
        return extract_requirements(
            edge_id=edge.edge_id,
            role=document_role(config, source_types[edge.reference_doc_id]),
            question=edge.question,
            blocks=blocks_by_doc[edge.reference_doc_id],
            llm_client=llm_client,
        )

    if progress_callback:
        # Counted in comparisons read, not requirements found: the number of
        # requirements is what this step is about to discover.
        progress_callback("requirements", completed=0, total=len(edges))
    requirements_by_edge = map_ordered(
        edges, read, workers=MAX_PARALLEL_REQUIREMENTS,
        on_progress=_reporter(progress_callback, "requirements"),
    )

    # Ordered by comparison and then by the requirements as read, not by completion,
    # so two identical runs produce byte-identical results.
    work = [
        (edge, requirement)
        for edge, requirements in zip(edges, requirements_by_edge)
        for requirement in requirements
    ]

    def judge(item: tuple[AlignmentEdge, Requirement]) -> AlignmentFinding:
        edge, requirement = item
        return assess_requirement(
            requirement,
            edge_id=edge.edge_id,
            role=document_role(config, source_types[edge.comparison_doc_id]),
            question=edge.question,
            blocks=blocks_by_doc[edge.comparison_doc_id],
            llm_client=llm_client,
        )

    if progress_callback:
        progress_callback("compare", completed=0, total=len(work))
    return map_ordered(
        work, judge, workers=MAX_PARALLEL_REQUIREMENTS,
        on_progress=_reporter(progress_callback, "compare"),
    )
