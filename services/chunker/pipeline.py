"""Stateless chunker pipeline.

Wires the two stages — parse (deterministic, format-specific) and an
optional LLM mapper — into one function for single docs and one for
batches. The interface and CLI both go through these so orchestration
lives in exactly one place.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .models import (
    ContentBlock,
    DocumentTypeConfig,
    LLMClientProtocol,
    PipelineResult,
)
from .stages.image_describer import describe_images
from .stages.mapper import label_blocks
from .stages.parser import parse_document

DEFAULT_MAX_OUTPUT_TOKENS = 16000


def run_pipeline(
    file_path: str,
    doc_id: str,
    *,
    config: DocumentTypeConfig | None = None,
    llm_client: LLMClientProtocol | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    org: str | None = None,
    source_type: str | None = None,
    intervention_class: str | None = None,
    indication: str | None = None,
    progress_callback=None,
) -> list[ContentBlock]:
    """Parse a document, then optionally run the mapper to assign section labels.

    Header fields (org / source_type / intervention_class / indication)
    are stamped onto every returned block. If not provided, the pipeline reads
    them from `config` (chunker configs declare the full header internally).

    Raises on parse or mapping failure. For batch use with per-document
    error capture, call `run_pipeline_batch`.
    """
    describe = bool(config and config.image_lens and llm_client)
    if progress_callback:
        progress_callback("parse")
    blocks = parse_document(file_path, doc_id, extract_images=describe)
    if describe:
        if progress_callback:
            progress_callback("describe")
        blocks = describe_images(blocks, file_path, config, llm_client)
    if config is not None and llm_client is not None:
        if progress_callback:
            progress_callback("label")
        blocks = label_blocks(blocks, config, llm_client, max_tokens=max_tokens)
    _stamp_header(
        blocks,
        org=org if org is not None else (config.org if config else None),
        source_type=source_type
        if source_type is not None
        else (config.source_type if config else None),
        intervention_class=intervention_class
        if intervention_class is not None
        else (config.intervention_class if config else None),
        indication=indication,
    )
    return blocks


def _stamp_header(
    blocks: list[ContentBlock],
    *,
    org: str | None,
    source_type: str | None,
    intervention_class: str | None,
    indication: str | None,
) -> None:
    for block in blocks:
        block.org = org
        block.source_type = source_type
        block.intervention_class = intervention_class
        block.indication = indication


def run_pipeline_batch(
    jobs: list[tuple[str, str]],
    *,
    config: DocumentTypeConfig | None = None,
    llm_client_factory=None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
    indication: str | None = None,
) -> list[PipelineResult]:
    """Run `run_pipeline` over many documents in parallel, capturing per-doc errors.

    Args:
        jobs: list of (file_path, doc_id) pairs.
        config / llm_client_factory: if either is None, the mapper is skipped.
            `llm_client_factory` is a zero-arg callable returning a fresh
            OpenAIClient per worker (avoids sharing a client across threads).
        max_tokens: mapper token budget.
        max_workers: parallel worker count.

    Returns:
        list[PipelineResult] in the same order as `jobs`.
    """
    if not jobs:
        return []
    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda job: _run_one(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    max_tokens=max_tokens,
                    indication=indication,
                ),
                jobs,
            )
        )


def _run_one(
    file_path: str,
    doc_id: str,
    *,
    config: DocumentTypeConfig | None,
    llm_client_factory,
    max_tokens: int,
    indication: str | None = None,
) -> PipelineResult:
    result = PipelineResult(file_path=file_path, doc_id=doc_id)
    describe = bool(config and config.image_lens and llm_client_factory)
    try:
        result.blocks = parse_document(file_path, doc_id, extract_images=describe)
    except Exception as exc:
        result.parse_error = str(exc)
        return result

    if config is not None and llm_client_factory is not None:
        try:
            llm_client = llm_client_factory()
            if describe:
                result.blocks = describe_images(
                    result.blocks, file_path, config, llm_client
                )
            result.blocks = label_blocks(
                result.blocks, config, llm_client, max_tokens=max_tokens
            )
        except Exception as exc:
            result.mapping_error = str(exc)

    _stamp_header(
        result.blocks,
        org=config.org if config else None,
        source_type=config.source_type if config else None,
        intervention_class=config.intervention_class if config else None,
        indication=indication,
    )
    return result


def map_blocks_batch(
    jobs: list[tuple[str, list[ContentBlock]]],
    *,
    config: DocumentTypeConfig,
    llm_client_factory,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[PipelineResult]:
    """Run the mapper over many already-parsed documents in parallel.

    Args:
        jobs: list of (doc_id, blocks) pairs where blocks are the parser output.
        config: mapper config (single config applied to all jobs).
        llm_client_factory: zero-arg callable returning a fresh OpenAIClient per worker.
        max_tokens: mapper token budget.
        max_workers: parallel worker count.

    Returns:
        list[PipelineResult] in the same order as `jobs`. Per-doc mapper
        failures are captured in `mapping_error` (blocks remain the input).
    """
    if not jobs:
        return []
    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda job: _map_one(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    max_tokens=max_tokens,
                ),
                jobs,
            )
        )


def _map_one(
    doc_id: str,
    blocks: list[ContentBlock],
    *,
    config: DocumentTypeConfig,
    llm_client_factory,
    max_tokens: int,
) -> PipelineResult:
    result = PipelineResult(file_path="", doc_id=doc_id, blocks=blocks)
    try:
        llm_client = llm_client_factory()
        result.blocks = label_blocks(blocks, config, llm_client, max_tokens=max_tokens)
    except Exception as exc:
        result.mapping_error = str(exc)
    return result
