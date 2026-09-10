"""Inspector — document-quality and rubric inspection service.

Consumes Chunker's public parsing/labeling contract and produces an InspectionResult
per document. Public contract below; internals
(`stages/`, `cli.py`) are not part of the contract.
"""

from .models import (
    LLMClientProtocol,
    BatchInspectionResult,
    InspectionConfig,
    InspectionResult,
    AggregateInspectionResult,
    inspection_result_to_dict,
)
from .pipeline import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    inspect_blocks,
    inspect_blocks_batch,
    run_pipeline,
    run_pipeline_batch,
)

__all__ = [
    "available_configs",
    "LLMClientProtocol",
    "BatchInspectionResult",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "InspectionConfig",
    "InspectionResult",
    "AggregateInspectionResult",
    "find_config",
    "has_config",
    "inspect_blocks",
    "inspect_blocks_batch",
    "inspection_result_to_dict",
    "run_pipeline",
    "run_pipeline_batch",
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
