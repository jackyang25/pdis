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

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Sequence

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from shared.batching import map_ordered

from .models import (
    AlignmentConfig,
    AlignmentDocument,
    AlignmentEdge,
    AlignmentFinding,
    AlignmentResult,
    DocumentInput,
    LLMClientProtocol,
    describe_document,
    resolve_edges,
)
from .contract import validate_result_contract
from .stages.assessor import assess_requirement
from .stages.requirements import extract_requirements

DEFAULT_MAX_OUTPUT_TOKENS = 12000

# Documents parse independently, so they parse at once. Bounded because each one
# fans out into its own chunker calls.
MAX_PARALLEL_DOCUMENTS = 3

# Requirements are judged independently, so they are judged at once. The same bound
# Expert uses for its questions: enough to keep a run to about a minute, low enough that
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
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
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

    total = len(documents)
    if progress_callback:
        progress_callback("parse", completed=0, total=total)
    parse_lock = threading.Lock()
    parsed_count = {"value": 0}

    def parse(document: DocumentInput) -> tuple[str, list[ContentBlock]]:
        blocks = chunker_run_pipeline(
            document.file_path,
            doc_id=document.doc_id,
            config=chunker_configs[document.doc_id],
            llm_client=llm_client,
            max_tokens=max_tokens,
            indication=indication,
        )
        if progress_callback:
            with parse_lock:
                parsed_count["value"] += 1
                progress_callback("parse", completed=parsed_count["value"], total=total)
        return document.doc_id, blocks

    parsed: dict[str, list[ContentBlock]] = {}
    with ThreadPoolExecutor(
        max_workers=min(MAX_PARALLEL_DOCUMENTS, total)
    ) as executor:
        futures = [executor.submit(parse, document) for document in documents]
        for future in as_completed(futures):
            doc_id, blocks = future.result()
            parsed[doc_id] = blocks

    findings = _compare_edges(
        edges,
        documents=identified,
        blocks_by_doc=parsed,
        config=config,
        llm_client=llm_client,
        max_tokens=max_tokens,
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


def _compare_edges(
    edges: Sequence[AlignmentEdge],
    *,
    documents: Sequence[AlignmentDocument],
    blocks_by_doc: dict[str, list[ContentBlock]],
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int,
    progress_callback=None,
) -> list[AlignmentFinding]:
    """Every requirement of every comparison, judged.

    Edges run in sequence and requirements fan out inside each one. Sequential edges
    keep the progress count honest — a run reports how many requirements it has and how
    many are done, and it cannot know the first until the first extraction returns.
    """
    source_types = {document.doc_id: document.source_type for document in documents}
    findings: list[AlignmentFinding] = []

    for position, edge in enumerate(edges):
        if progress_callback:
            # Counted in comparisons read, not requirements found: the number of
            # requirements is what this step is about to discover.
            progress_callback("requirements", completed=position, total=len(edges))
        requirements = extract_requirements(
            edge_id=edge.edge_id,
            role=describe_document(config, source_types[edge.reference_doc_id]),
            question=edge.question,
            blocks=blocks_by_doc[edge.reference_doc_id],
            llm_client=llm_client,
            max_tokens=max_tokens,
        )

        comparison_blocks = blocks_by_doc[edge.comparison_doc_id]
        comparison_role = describe_document(
            config, source_types[edge.comparison_doc_id]
        )
        total = len(requirements)
        if progress_callback:
            progress_callback("compare", completed=0, total=total)
        judged = {"value": 0}
        lock = threading.Lock()

        def judge(requirement, edge=edge, blocks=comparison_blocks, role=comparison_role):
            finding = assess_requirement(
                requirement,
                edge_id=edge.edge_id,
                role=role,
                question=edge.question,
                blocks=blocks,
                llm_client=llm_client,
                max_tokens=max_tokens,
            )
            if progress_callback:
                with lock:
                    judged["value"] += 1
                    progress_callback(
                        "compare", completed=judged["value"], total=total
                    )
            return finding

        # Ordered by the requirements as read, not by completion, so two identical runs
        # produce byte-identical results.
        findings.extend(
            map_ordered(requirements, judge, workers=MAX_PARALLEL_REQUIREMENTS)
        )

    return findings
