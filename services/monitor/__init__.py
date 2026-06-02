"""Monitor - derives doc-aware Matches from uploaded docs + the 4 primitives.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

v0 reuses chunker (parsing) and searcher (web findings). v1 will enrich
Matches with benchmarker claim IDs - not built yet.
"""

from .models import (
    Insight,
    LLMClientProtocol,
    Match,
    MonitorTypeConfig,
    SearchClientProtocol,
    VALID_RELATIONS,
    find_config,
    insights_to_dicts,
    load_config,
    matches_to_dicts,
)
from .pipeline import run_pipeline

__all__ = [
    "Insight",
    "LLMClientProtocol",
    "Match",
    "MonitorTypeConfig",
    "SearchClientProtocol",
    "VALID_RELATIONS",
    "find_config",
    "insights_to_dicts",
    "load_config",
    "matches_to_dicts",
    "run_pipeline",
]
