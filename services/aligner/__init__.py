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
    DocumentRole,
    EdgeSpec,
    Requirement,
    VERDICTS_REQUIRING_CITATION,
    describe_edges,
    document_role,
    edge_id,
    load_config,
    requirement_id,
    resolve_edges,
)
from .pipeline import run_pipeline

__all__ = [
    "ALIGNMENT_VERDICTS",
    "LLMClientProtocol",
    "AlignmentConfig",
    "AlignmentDocument",
    "AlignmentEdge",
    "AlignmentFinding",
    "AlignmentResult",
    "AlignmentVerdict",
    "DocumentInput",
    "DocumentRole",
    "EdgeSpec",
    "Requirement",
    "VERDICTS_REQUIRING_CITATION",
    "describe_edges",
    "document_role",
    "edge_id",
    "load_config",
    "requirement_id",
    "resolve_edges",
    "run_pipeline",
]
