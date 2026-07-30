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
    find_config,
    has_config,
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
    "LLMClientProtocol",
    "BatchInspectionResult",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "InspectionConfig",
    "InspectionResult",
    "find_config",
    "has_config",
    "inspect_blocks",
    "inspect_blocks_batch",
    "inspection_result_to_dict",
    "run_pipeline",
    "run_pipeline_batch",
]
