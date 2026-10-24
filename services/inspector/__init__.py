"""Inspector — document-quality and rubric inspection service.

Consumes Chunker's public parsing/labeling contract and produces one
AggregateInspectionResult per document: a peer review per included rubric. Public contract below; internals
(`stages/`, `cli.py`) are not part of the contract.
"""

from .models import (
    LLMClientProtocol,
    InspectionConfig,
    InspectionResult,
    AggregateInspectionResult,
    inspection_result_to_dict,
)
__all__ = [
    "available_configs",
    "LLMClientProtocol",
    "InspectionConfig",
    "InspectionResult",
    "AggregateInspectionResult",
    "find_config",
    "has_config",
    "inspection_result_to_dict",
]

from .configuration import (
    available_configs,
    find_config,
    has_config,
    InspectionProfile,
    available_rubric_configs,
    find_profile,
    profile_catalog,
    resolve_profile,
    validate_product_facts,
)
from .pipeline import inspect_blocks_with_profile, run_profile_pipeline

__all__ += [
    "available_rubric_configs",
    "InspectionProfile",
    "find_profile", "profile_catalog", "resolve_profile",
    "validate_product_facts",
    "inspect_blocks_with_profile", "run_profile_pipeline",
]
