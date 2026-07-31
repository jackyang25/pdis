"""Chunker — document parsing & section labeling service.

Public contract: consumers import from this package root only.
Internals (`stages/`, `cli.py`, internal helpers) are not part of the contract.

In the future-distributed shape, this is a service that runs in the
background or is called synchronously by tools and other services. Today
it's a Python package in this monorepo. The public surface below is the
wire protocol — keep it small and stable.
"""

from .models import (
    LLMClientProtocol,
    ContentBlock,
    DocumentTypeConfig,
    ImageAsset,
    PipelineResult,
    blocks_to_dicts,
    available_configs,
    find_config,
)
from .pipeline import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DOCUMENT_SUFFIXES,
    map_blocks_batch,
    parse_context_file,
    run_pipeline,
    run_pipeline_batch,
)

__all__ = [
    "LLMClientProtocol",
    "ContentBlock",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DOCUMENT_SUFFIXES",
    "DocumentTypeConfig",
    "ImageAsset",
    "PipelineResult",
    "blocks_to_dicts",
    "available_configs",
    "find_config",
    "map_blocks_batch",
    "parse_context_file",
    "run_pipeline",
    "run_pipeline_batch",
]
