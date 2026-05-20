"""Evidence — claim extraction + binding + appraisal service.

Public contract: consumers import from this package root only.
Internals (`stages/`, `cli.py`) are not part of the contract.

Service shape: documents in → claims out. The store (`FileClaimsStore`) is
exposed for consumers that want to read accumulated claims as a queryable
substrate. In production this becomes a Delta-backed store with the same
interface.
"""

from .models import (
    AttributeConfig,
    BatchResult,
    Claim,
    claims_to_dicts,
    find_config,
)
from .pipeline import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    EXTRACTORS,
    default_source_id_from_path,
    run_pipeline,
    run_pipeline_batch,
)
from .store import ClaimsStore, FileClaimsStore

__all__ = [
    "AttributeConfig",
    "BatchResult",
    "Claim",
    "ClaimsStore",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "EXTRACTORS",
    "FileClaimsStore",
    "claims_to_dicts",
    "default_source_id_from_path",
    "find_config",
    "run_pipeline",
    "run_pipeline_batch",
]
