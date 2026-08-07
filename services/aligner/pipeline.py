"""Aligner's entry point: identify documents, resolve comparisons, parse, publish.

Everything here is work the suite asks of every tool - resolve a chunker config
per document, parse, assemble a result, validate it. The analysis that used to
sit between the parse and the result has been removed, so this is the substrate a
new design builds on rather than a pipeline with a hole in it.

Note what is absent: no document count, no source type, no notion of which pair
compares to which. All of that is read from config, so supporting a new document
type never reaches this file.
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

from .models import (
    AlignmentConfig,
    AlignmentDocument,
    AlignmentResult,
    DocumentInput,
    LLMClientProtocol,
    resolve_edges,
)
from .contract import validate_result_contract

DEFAULT_MAX_OUTPUT_TOKENS = 12000

# Documents parse independently, so they parse at once. Bounded because each one
# fans out into its own chunker calls.
MAX_PARALLEL_DOCUMENTS = 3


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
    """Parse every document and return them with the comparisons they resolve.

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

    result = AlignmentResult(
        documents=identified,
        edges=edges,
        org=org,
        intervention_class=intervention_class,
        indication=indication,
        # Ordered by the documents as supplied rather than by completion, so two
        # identical runs produce byte-identical results.
        blocks=[block for document in documents for block in parsed[document.doc_id]],
    )
    return validate_result_contract(result, config)
