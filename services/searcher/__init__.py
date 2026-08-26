"""Searcher - pluggable external-evidence retrieval service.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

Source adapters plan native requests and normalize them to Findings. The public
surface below is the cross-service contract; consumers never reach into an
adapter or stage.
"""

from .models import (
    DEVELOPMENT_RECORD_TYPES,
    DevelopmentRecord,
    EVIDENCE_DOMAINS,
    ENTITY_TYPES,
    FINDING_ROLES,
    Finding,
    INDICATOR_SPATIAL_TYPES,
    QueryFacets,
    RetrievalEntity,
    RetrievalIntent,
    RetrievalPath,
    SearchOutcome,
    SearchReport,
    SearchRequest,
    SearchRuntime,
    SearcherLLMClientProtocol,
    SAFETY_RECORD_TYPES,
    SAFETY_SOURCE_SYSTEMS,
    SOURCE_ROLES,
    SafetyObservationRecord,
    SourceAttribution,
    SourceQueryIntent,
    SourceSpec,
    findings_to_dicts,
    merge_findings,
    outcomes_to_dicts,
)
from .connectors import TavilyHTTPConnector, ToolUniverseHTTPConnector
from .controller import (
    integration_operations,
    lane_class,
    plan_requests,
    run_requests,
    source_keys,
    source_specs,
    validate_source_keys,
    unconfigured_source_keys,
)
from .net import prefer_ipv4
from .pipeline import run_pipeline
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES

# Make the direct-HTTP lanes (PubMed, ClinicalTrials.gov) resilient in
# IPv6-less containers - see net.py. Cheap, idempotent, applied on import.
prefer_ipv4()

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "TavilyHTTPConnector",
    "DEFAULT_MAX_USES",
    "DEVELOPMENT_RECORD_TYPES",
    "DevelopmentRecord",
    "EVIDENCE_DOMAINS",
    "ENTITY_TYPES",
    "FINDING_ROLES",
    "Finding",
    "INDICATOR_SPATIAL_TYPES",
    "QueryFacets",
    "RetrievalEntity",
    "RetrievalIntent",
    "RetrievalPath",
    "SearchOutcome",
    "SearchReport",
    "SearchRequest",
    "SearchRuntime",
    "SearcherLLMClientProtocol",
    "SAFETY_RECORD_TYPES",
    "SAFETY_SOURCE_SYSTEMS",
    "SOURCE_ROLES",
    "SafetyObservationRecord",
    "SourceAttribution",
    "SourceQueryIntent",
    "SourceSpec",
    "ToolUniverseHTTPConnector",
    "findings_to_dicts",
    "integration_operations",
    "lane_class",
    "merge_findings",
    "outcomes_to_dicts",
    "plan_requests",
    "run_requests",
    "run_pipeline",
    "source_keys",
    "source_specs",
    "validate_source_keys",
    "unconfigured_source_keys",
]
