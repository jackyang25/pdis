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
) -> list[ContentBlock]:
    """Parse a document, then optionally run the mapper to assign section labels.

    Raises on parse or mapping failure. For batch use with per-document
    error capture, call `run_pipeline_batch`.
    """
    blocks = parse_document(file_path, doc_id)
    if config is not None and llm_client is not None:
        blocks = label_blocks(blocks, config, llm_client, max_tokens=max_tokens)
    return blocks


def run_pipeline_batch(
    jobs: list[tuple[str, str]],
    *,
    config: DocumentTypeConfig | None = None,
    llm_client_factory=None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[PipelineResult]:
    """Run `run_pipeline` over many documents in parallel, capturing per-doc errors.

    Args:
        jobs: list of (file_path, doc_id) pairs.
        config / llm_client_factory: if either is None, the mapper is skipped.
            `llm_client_factory` is a zero-arg callable returning a fresh
            LLMClient per worker (avoids sharing a client across threads).
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
) -> PipelineResult:
    result = PipelineResult(file_path=file_path, doc_id=doc_id)
    try:
        result.blocks = parse_document(file_path, doc_id)
    except Exception as exc:
        result.parse_error = str(exc)
        return result

    if config is None or llm_client_factory is None:
        return result

    try:
        llm_client = llm_client_factory()
        result.blocks = label_blocks(
            result.blocks, config, llm_client, max_tokens=max_tokens
        )
    except Exception as exc:
        result.mapping_error = str(exc)
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
        llm_client_factory: zero-arg callable returning a fresh LLMClient per worker.
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
