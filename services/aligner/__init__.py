"""Aligner — cross-document comparison for product-development artifacts.

Between designs. The extract-and-link analysis has been removed; what remains is
the boundary the rest of the suite talks to, so a new analysis is added behind
this same surface rather than around it.
"""

from .models import (
    LLMClientProtocol,
    AlignmentConfig,
    AlignmentDocument,
    AlignmentEdge,
    AlignmentResult,
    DocumentInput,
    EdgeSpec,
    alignment_result_to_dict,
    describe_document,
    describe_edges,
    load_config,
    resolve_edges,
)
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, run_pipeline

__all__ = [
    "LLMClientProtocol",
    "AlignmentConfig",
    "AlignmentDocument",
    "AlignmentEdge",
    "AlignmentResult",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DocumentInput",
    "EdgeSpec",
    "alignment_result_to_dict",
    "describe_document",
    "describe_edges",
    "load_config",
    "resolve_edges",
    "run_pipeline",
]
