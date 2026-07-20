"""Searcher data shapes and the LLM client contract it requires.

Public types live here - they are re-exported by __init__.py. Consumers
should import from `services.searcher`, never from this module directly.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol

EVIDENCE_DOMAINS = frozenset(
    {
        "general",
        "biological",
        "clinical",
        "safety",
        "regulatory",
        "product",
        "manufacturing",
        "delivery",
        "commercial_access",
    }
)
ENTITY_TYPES = frozenset(
    {
        "disease",
        "pathogen",
        "protein",
        "gene",
        "antigen",
        "vaccine",
        "drug",
        "compound",
        "biomarker",
        "device",
        "other",
    }
)
FINDING_ROLES = frozenset({"evidence", "reference"})
DEVELOPMENT_RECORD_TYPES = frozenset(
    {"clinical_trial", "compound_catalog", "regulatory_label", "regulatory_clearance"}
)
SAFETY_SIGNAL_TYPES = frozenset(
    {"label_warning", "reported_event", "device_event", "recall"}
)


@dataclass(frozen=True)
class SourceAttribution:
    """Optional public attribution notice owned by a retrieval source."""

    label: str
    url: str
    prefix: str = "Source data provided by"


@dataclass(frozen=True)
class SourceSpec:
    """Public metadata and execution policy for one retrieval source adapter."""

    key: str
    label: str
    worker_limit: int
    # Minimum spacing between adapter request starts. This is appropriate when
    # one adapter request maps to one provider request (for example Semantic
    # Scholar). Sources that fan one adapter request into several provider
    # calls retain endpoint-level throttling inside their adapter stage.
    request_interval_seconds: float = 0.0
    default_enabled: bool = True
    integration_key: str = ""
    operations: tuple[str, ...] = ()
    attribution: SourceAttribution | None = None
    evidence_domains: tuple[str, ...] = ()
    required_entity_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.worker_limit < 1:
            raise ValueError("source worker_limit must be positive")
        if self.request_interval_seconds < 0:
            raise ValueError("source request interval cannot be negative")
        unknown_domains = set(self.evidence_domains) - EVIDENCE_DOMAINS
        if unknown_domains:
            raise ValueError(
                f"unknown source evidence domain(s): {', '.join(sorted(unknown_domains))}"
            )
        unknown_entities = set(self.required_entity_types) - ENTITY_TYPES
        if unknown_entities:
            raise ValueError(
                f"unknown required entity type(s): {', '.join(sorted(unknown_entities))}"
            )


@dataclass(frozen=True)
class SourceQueryIntent:
    """One provider-agnostic query intent supplied by an upstream consumer."""

    text: str
    tracks: tuple[str, ...] = ()
    document_refs: tuple[str, ...] = ()
    intent_id: str = ""

    def __post_init__(self) -> None:
        if self.intent_id:
            return
        material = "\n".join(
            (self.text, *self.tracks, *self.document_refs)
        )
        object.__setattr__(
            self,
            "intent_id",
            "q-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16],
        )


@dataclass(frozen=True)
class RetrievalEntity:
    name: str
    entity_type: str
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unknown retrieval entity type: {self.entity_type}")
        if not self.name.strip():
            raise ValueError("retrieval entity name cannot be empty")


@dataclass(frozen=True)
class RetrievalIntent:
    """Neutral context a source adapter uses to create native requests."""

    scope_ref: str
    topic: str
    description: str
    indication: str
    intervention_class: str
    queries: tuple[SourceQueryIntent, ...]
    document_target: str = ""
    definition_mode: str = "fixed"
    evidence_domain: str = ""
    entities: tuple[RetrievalEntity, ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_domain and self.evidence_domain not in EVIDENCE_DOMAINS:
            raise ValueError(f"unknown retrieval evidence domain: {self.evidence_domain}")


@dataclass(frozen=True)
class SearchRequest:
    """One immutable, source-native retrieval request."""

    scope_ref: str
    source: str
    query: str
    tracks: tuple[str, ...] = ()
    document_refs: tuple[str, ...] = ()
    # Exact neutral intents compiled into this native request. These fields are
    # deliberately carried beside the native query so compaction can never
    # erase or overstate its input coverage.
    intent_ids: tuple[str, ...] = ()
    input_queries: tuple[str, ...] = ()
    connector: str = ""
    operation: str = ""
    options: tuple[tuple[str, str], ...] = ()
    applicability: str = "applicable"  # applicable | not_applicable
    applicability_reason: str = ""

    def option(self, name: str, default: str = "") -> str:
        return dict(self.options).get(name, default)


@dataclass
class SearchOutcome:
    """One request result; empty success and adapter failure remain distinct."""

    request: SearchRequest
    findings: list["Finding"] = field(default_factory=list)
    status: str = "complete"  # complete | failed | skipped
    error: str = ""


@dataclass
class SearchRuntime:
    """Injected capabilities available to adapters, never global provider state."""

    llm_client: "SearcherLLMClientProtocol"
    ncbi_api_key: str | None = None
    integrations: Mapping[str, Any] = field(default_factory=dict)
    global_worker_limit: int = 48


@dataclass(frozen=True)
class RetrievalPath:
    """One exact query/lane path by which a URL was retrieved."""

    query: str
    lane: str
    connector: str = ""
    operation: str = ""


@dataclass(frozen=True)
class DevelopmentRecord:
    """Source-normalized facts about one named development program.

    Adapters populate only fields explicitly present in the provider record.
    Scout may group these records for display, but must not infer a missing
    sponsor, phase, or status.
    """

    program_name: str
    record_type: str
    record_id: str = ""
    sponsor: str = ""
    phase: str = ""
    status: str = ""

    def __post_init__(self) -> None:
        if not self.program_name.strip():
            raise ValueError("development program name cannot be empty")
        if self.record_type not in DEVELOPMENT_RECORD_TYPES:
            raise ValueError(f"unknown development record type: {self.record_type}")


@dataclass(frozen=True)
class SafetyRecord:
    """One structured, non-causal safety observation from a source record."""

    product_name: str
    signal_type: str
    signal: str
    detail: str = ""
    count: int | None = None
    qualification: str = ""

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("safety product name cannot be empty")
        if self.signal_type not in SAFETY_SIGNAL_TYPES:
            raise ValueError(f"unknown safety signal type: {self.signal_type}")
        if not self.signal.strip():
            raise ValueError("safety signal label cannot be empty")
        if self.count is not None and self.count < 0:
            raise ValueError("safety report count cannot be negative")


@dataclass
class Finding:
    """One atomic, source-attributed result from a retrieval backend.

    Stays intentionally primitive. No synthesis, no relevance scores.
    `excerpt` is a lane-provided cited passage, abstract/full-text extract, or
    structured registry summary. Otherwise it is None.
    """

    url: str
    title: str
    query: str
    retrieved_at: datetime
    excerpt: str | None = None
    published_at: datetime | None = None
    source: str = "unknown"
    # Reference records may provide entity or catalog metadata but are not fed
    # into Scout's evidence reasoning. Structured projections may still use
    # their normalized development facts.
    evidence_role: str = "evidence"  # evidence | reference
    development_records: list[DevelopmentRecord] = field(default_factory=list)
    safety_records: list[SafetyRecord] = field(default_factory=list)
    # URL deduplication must not erase how a source was discovered. ``query``
    # and ``source`` remain the primary values for compatibility; these lists
    # retain every retrieval path merged into the Finding.
    queries: list[str] = field(default_factory=list)
    source_lanes: list[str] = field(default_factory=list)
    source_labels: dict[str, str] = field(default_factory=dict)
    source_attributions: dict[str, SourceAttribution] = field(default_factory=dict)
    retrieval_paths: list[RetrievalPath] = field(default_factory=list)
    title_source_lane: str = ""
    excerpt_source_lane: str = ""
    published_source_lane: str = ""

    def __post_init__(self) -> None:
        if self.evidence_role not in FINDING_ROLES:
            raise ValueError(f"unknown finding evidence role: {self.evidence_role}")
        self.development_records = list(dict.fromkeys(self.development_records))
        self.safety_records = list(dict.fromkeys(self.safety_records))
        if self.query and self.query not in self.queries:
            self.queries.insert(0, self.query)
        if self.source and self.source not in self.source_lanes:
            self.source_lanes.insert(0, self.source)
        path = RetrievalPath(query=self.query, lane=self.source)
        if self.query and self.source and path not in self.retrieval_paths:
            self.retrieval_paths.append(path)
        self.title_source_lane = self.title_source_lane or self.source
        if self.excerpt:
            self.excerpt_source_lane = self.excerpt_source_lane or self.source
        if self.published_at:
            self.published_source_lane = self.published_source_lane or self.source


class SearcherLLMClientProtocol(Protocol):
    """Contract searcher requires from any injected LLM client.

    Library code depends only on this Protocol - the concrete client
    (OpenAIClient, a mock, anything) is passed in by the caller.
    """

    def search_web(self, query: str, *, max_tokens: int, max_uses: int) -> Any:
        ...


def merge_findings(existing: Finding, incoming: Finding) -> Finding:
    """Merge duplicate URLs without discarding retrieval or source provenance."""
    existing.queries = list(
        dict.fromkeys(
            query
            for query in [
                *existing.queries,
                existing.query,
                *incoming.queries,
                incoming.query,
            ]
            if query
        )
    )
    existing.source_lanes = list(
        dict.fromkeys(
            lane
            for lane in [
                *existing.source_lanes,
                existing.source,
                *incoming.source_lanes,
                incoming.source,
            ]
            if lane
        )
    )
    existing.source_labels = {
        **existing.source_labels,
        **incoming.source_labels,
    }
    existing.source_attributions = {
        **existing.source_attributions,
        **incoming.source_attributions,
    }
    existing.retrieval_paths = list(
        dict.fromkeys([*existing.retrieval_paths, *incoming.retrieval_paths])
    )
    existing.development_records = list(
        dict.fromkeys(
            [*existing.development_records, *incoming.development_records]
        )
    )
    existing.safety_records = list(
        dict.fromkeys([*existing.safety_records, *incoming.safety_records])
    )
    # A duplicate retrieved as evidence in any lane remains eligible for
    # reasoning. Reference-only is the conservative default for metadata.
    if incoming.evidence_role == "evidence":
        existing.evidence_role = "evidence"
    # `source_lanes` is the authoritative multi-source provenance. Keep the
    # first lane as the compatibility primary rather than embedding a brittle
    # global ranking that every new adapter would need to modify.
    existing.source = existing.source_lanes[0] if existing.source_lanes else existing.source
    if incoming.excerpt and len(incoming.excerpt) > len(existing.excerpt or ""):
        existing.excerpt = incoming.excerpt
        existing.excerpt_source_lane = incoming.excerpt_source_lane or incoming.source
    if (not existing.title or existing.title == existing.url) and incoming.title:
        existing.title = incoming.title
        existing.title_source_lane = incoming.title_source_lane or incoming.source
    if existing.published_at is None and incoming.published_at is not None:
        existing.published_at = incoming.published_at
        existing.published_source_lane = (
            incoming.published_source_lane or incoming.source
        )
    return existing


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    """Convert Finding objects to plain dictionaries (datetimes -> ISO strings)."""
    out: list[dict] = []
    for finding in findings:
        d = asdict(finding)
        d["retrieved_at"] = finding.retrieved_at.isoformat()
        d["published_at"] = (
            finding.published_at.isoformat() if finding.published_at else None
        )
        out.append(d)
    return out
