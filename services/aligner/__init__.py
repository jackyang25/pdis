"""Aligner — one-way comparison between product-development artifacts.

A comparison runs in one direction: the reference document's requirements are the
rubric, and each one is judged against the comparison document. What compares to what
is configuration, so the surface below never names a document type.
"""

from .models import (
    ALIGNMENT_VERDICTS,
    LLMClientProtocol,
    AlignmentConfig,
    AlignmentDocument,
    AlignmentEdge,
    AlignmentFinding,
    AlignmentResult,
    AlignmentVerdict,
    DocumentInput,
    EdgeSpec,
    Requirement,
    VERDICTS_REQUIRING_CITATION,
    VERDICTS_REQUIRING_GAP,
    alignment_result_to_dict,
    describe_document,
    describe_edges,
    edge_id,
    load_config,
    requirement_id,
    resolve_edges,
)
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, run_pipeline

__all__ = [
    "ALIGNMENT_VERDICTS",
    "LLMClientProtocol",
    "AlignmentConfig",
    "AlignmentDocument",
    "AlignmentEdge",
    "AlignmentFinding",
    "AlignmentResult",
    "AlignmentVerdict",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DocumentInput",
    "EdgeSpec",
    "Requirement",
    "VERDICTS_REQUIRING_CITATION",
    "VERDICTS_REQUIRING_GAP",
    "alignment_result_to_dict",
    "describe_document",
    "describe_edges",
    "edge_id",
    "load_config",
    "requirement_id",
    "resolve_edges",
    "run_pipeline",
]
