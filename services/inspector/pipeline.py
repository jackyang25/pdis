from __future__ import annotations

from pathlib import Path

from shared.batching import map_ordered

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from .assembly import assess_sections, rank_findings
from .contract import validate_result_contract
from .models import (
    BatchInspectionResult,
    InspectionConfig,
    InspectionResult,
    LLMClientProtocol,
)
from .stages.assessor import assess_document, check_cross_section

DEFAULT_MAX_OUTPUT_TOKENS = 32000


def run_pipeline(
    file_path: str,
    *,
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
    doc_id: str | None = None,
) -> InspectionResult:
    """End-to-end document inspection: parse → label → grade → report.

    `doc_id` is stamped on every block. Pass the original filename stem
    when `file_path` points to a temp file (e.g., from an HTTP upload),
    so block ids don't end up prefixed with the temp filename.
    """
    source_path = Path(file_path)
    resolved_doc_id = doc_id or source_path.stem
    chunker_config = find_chunker_config(
        config.org, config.source_type, config.intervention_class
    )
    # Delegate parse + label to chunker via its public surface
    labeled_blocks = chunker_run_pipeline(
        str(source_path),
        doc_id=resolved_doc_id,
        config=chunker_config,
        llm_client=llm_client,
        max_tokens=max_tokens,
        indication=indication,
        progress_callback=progress_callback,
    )
    return inspect_blocks(
        labeled_blocks,
        config=config,
        llm_client=llm_client,
        indication=indication,
        max_tokens=max_tokens,
        progress_callback=progress_callback,
    )


def inspect_blocks(
    blocks: list[ContentBlock],
    *,
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
) -> InspectionResult:
    """Assess and assemble a document whose blocks are already parsed and labeled."""
    if progress_callback:
        progress_callback("assess")
    findings, mapped_blocks = assess_document(
        blocks,
        config,
        llm_client,
        max_tokens=max_tokens,
        progress=progress_callback,
    )

    # The whole-document pass is the one place that sees every section at once. It
    # runs before assembly because its findings share one ranking with the rest.
    if progress_callback:
        progress_callback("consistency")
    document_findings, consistency_status = check_cross_section(
        blocks, config, llm_client, max_tokens=max_tokens
    )

    sections = assess_sections(
        config,
        findings,
        mapped_blocks=mapped_blocks,
    )
    rank_findings(config, sections, document_findings)

    result = InspectionResult(
        doc_id=blocks[0].doc_id if blocks else "",
        sections=sections,
        document_findings=document_findings,
        consistency_status=consistency_status,
        assessment_status="complete",
        org=config.org,
        source_type=config.source_type,
        intervention_class=config.intervention_class,
        indication=indication,
        blocks=blocks,
    )
    return validate_result_contract(result, config)


def run_pipeline_batch(
    jobs: list[tuple[str, str]],
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchInspectionResult]:
    """Run `run_pipeline` (parse → label → grade) over many documents in parallel."""
    return map_ordered(
        jobs,
        lambda job: _run_pipeline_one_batch(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    indication=indication,
                    max_tokens=max_tokens,
                ),
        workers=max_workers,
    )


def _run_pipeline_one_batch(
    file_path: str,
    doc_key: str,
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None,
    max_tokens: int,
) -> BatchInspectionResult:
    try:
        llm_client = llm_client_factory()
        inspection = run_pipeline(
            file_path,
            config=config,
            llm_client=llm_client,
            indication=indication,
            max_tokens=max_tokens,
        )
        inspection.doc_id = doc_key
        return BatchInspectionResult(doc_key=doc_key, inspection=inspection)
    except Exception as exc:
        return BatchInspectionResult(doc_key=doc_key, error=str(exc))


def inspect_blocks_batch(
    jobs: list[tuple[str, list[ContentBlock]]],
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchInspectionResult]:
    """Run `inspect_blocks` over many already-parsed documents in parallel.

    Args:
        jobs: list of (doc_key, blocks) pairs.
        llm_client_factory: zero-arg callable returning a fresh OpenAIClient per worker.

    Returns:
        list[BatchInspectionResult] in the same order as `jobs`.
    """
    return map_ordered(
        jobs,
        lambda job: _inspect_one_batch(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    indication=indication,
                    max_tokens=max_tokens,
                ),
        workers=max_workers,
    )


def _inspect_one_batch(
    doc_key: str,
    blocks: list[ContentBlock],
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None,
    max_tokens: int,
) -> BatchInspectionResult:
    try:
        llm_client = llm_client_factory()
        inspection = inspect_blocks(
            blocks,
            config=config,
            llm_client=llm_client,
            indication=indication,
            max_tokens=max_tokens,
        )
        return BatchInspectionResult(doc_key=doc_key, inspection=inspection)
    except Exception as exc:
        return BatchInspectionResult(doc_key=doc_key, error=str(exc))
