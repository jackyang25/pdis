"""Monitor - derives web Insights from uploaded docs + the 4 primitives.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

v0 reuses chunker (parsing) and searcher (web findings). v1 will add
benchmarker comparison (Claims vs Insights -> Matches) - not built yet.
"""

from .models import (
    Insight,
    MonitorTypeConfig,
    OpenAIClientProtocol,
    SearchClientProtocol,
    find_config,
    insights_to_dicts,
    load_config,
)
from .pipeline import run_pipeline

__all__ = [
    "Insight",
    "MonitorTypeConfig",
    "OpenAIClientProtocol",
    "SearchClientProtocol",
    "find_config",
    "insights_to_dicts",
    "load_config",
    "run_pipeline",
]
