"""Aligner — cross-document traceability for product-development artifacts."""

from .models import (
    LLMClientProtocol,
    AlignmentConfig,
    AlignmentDocument,
    AlignmentLink,
    AlignmentResult,
    AlignmentStats,
    AlignmentUnit,
    alignment_result_to_dict,
    load_config,
)
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, run_pipeline

__all__ = [
    "LLMClientProtocol",
    "AlignmentConfig",
    "AlignmentDocument",
    "AlignmentLink",
    "AlignmentResult",
    "AlignmentStats",
    "AlignmentUnit",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "alignment_result_to_dict",
    "load_config",
    "run_pipeline",
]
