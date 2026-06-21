"""Monitor - derives doc-aware Matches from uploaded docs + the 4 primitives.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

Monitor parses docs for drift context, searches per shared attribute
variable, and emits doc-aware Matches.
"""

from .models import (
    Attribute,
    ConformityScore,
    EvidenceAssessment,
    FunnelStats,
    Insight,
    LLMClientProtocol,
    Match,
    Measurement,
    MonitorResult,
    MonitorTypeConfig,
    SearchClientProtocol,
    VALID_EVIDENCE_BASIS,
    VALID_EVIDENCE_STRENGTHS,
    VALID_RELATIONS,
    assessments_to_dicts,
    conformity_to_dicts,
    find_config,
    insights_to_dicts,
    load_attributes,
    load_config,
    matches_to_dicts,
)
from .pipeline import run_pipeline

__all__ = [
    "Attribute",
    "ConformityScore",
    "EvidenceAssessment",
    "FunnelStats",
    "Insight",
    "LLMClientProtocol",
    "Match",
    "Measurement",
    "MonitorResult",
    "MonitorTypeConfig",
    "SearchClientProtocol",
    "VALID_EVIDENCE_BASIS",
    "VALID_EVIDENCE_STRENGTHS",
    "VALID_RELATIONS",
    "assessments_to_dicts",
    "conformity_to_dicts",
    "find_config",
    "insights_to_dicts",
    "load_attributes",
    "load_config",
    "matches_to_dicts",
    "run_pipeline",
]
