"""Searcher - pluggable external-evidence retrieval service.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

Source adapters plan native requests and normalize them to Findings. The public
surface below is the cross-service contract; consumers never reach into an
adapter or stage.
"""

from .errors import RETRIEVAL_ERROR_CODES, RetrievalError
from .models import (
    CROSS_LANE_IDENTIFIER_SCHEMES,
    DEVELOPMENT_RECORD_TYPES,
    DevelopmentRecord,
    EVIDENCE_DOMAINS,
    ENTITY_TYPES,
    EXCERPT_KINDS,
    FINDING_ROLES,
    Finding,
    IDENTIFIER_SCHEMES,
    OUTCOME_WARNING_CODES,
    OutcomeWarning,
    INDICATOR_SPATIAL_TYPES,
    QueryFacets,
    RetrievalEntity,
    RetrievalIntent,
    RetrievalPath,
    SearchOutcome,
    SearchReport,
    SearchRequest,
    SearchRuntime,
    LLMClientProtocol,
    SAFETY_RECORD_TYPES,
    SAFETY_SOURCE_SYSTEMS,
    SOURCE_ROLES,
    SafetyObservationRecord,
    SourceAttribution,
    SourceQueryIntent,
    SourceSpec,
    dedupe_findings,
    findings_to_dicts,
    merge_findings,
    outcomes_to_dicts,
)
from .dates import PUBLISHED_PRECISIONS
from .connectors import TavilyHTTPConnector, ToolUniverseHTTPConnector
from .sources.tavily import TAVILY_INTEGRATION
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
from .pipeline import SEARCH_ENTITIES_DESCRIPTION, SEARCH_ENTITY_FIELDS, SEARCH_TEXT_FIELDS, run_pipeline
from .stages.searcher import DEFAULT_MAX_TOKENS

__all__ = [
    "CROSS_LANE_IDENTIFIER_SCHEMES",
    "EXCERPT_KINDS",
    "IDENTIFIER_SCHEMES",
    "OUTCOME_WARNING_CODES",
    "OutcomeWarning",
    "PUBLISHED_PRECISIONS",
    "RETRIEVAL_ERROR_CODES",
    "RetrievalError",
    "dedupe_findings",
    "DEFAULT_MAX_TOKENS",
    "SEARCH_ENTITIES_DESCRIPTION",
    "SEARCH_ENTITY_FIELDS",
    "SEARCH_TEXT_FIELDS",
    "TAVILY_INTEGRATION",
    "TavilyHTTPConnector",
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
    "LLMClientProtocol",
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
