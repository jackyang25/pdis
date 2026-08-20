"""Searcher data shapes and the LLM client contract it requires.

Public types live here - they are re-exported by __init__.py. Consumers
should import from `services.searcher`, never from this module directly.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from shared.vocabulary import ENTITY_TYPES, EVIDENCE_DOMAINS

FINDING_ROLES = frozenset({"evidence", "reference"})
DEVELOPMENT_RECORD_TYPES = frozenset(
    {"clinical_trial", "compound_catalog", "regulatory_label", "regulatory_clearance"}
)
SAFETY_RECORD_TYPES = frozenset(
    {"label_warning", "reported_event", "device_event", "recall"}
)
SAFETY_SOURCE_SYSTEMS = frozenset({"fda_label", "faers", "maude", "fda_recall"})
SOURCE_ROLES = frozenset(
    {"experimental", "comparator", "control", "co_intervention", "unknown"}
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
    # Most requests one intent may become. Request count became variable when
    # adapters started narrowing by stated facets, so a source declares its own
    # budget beside its other limits. 0 means the source sets no bound.
    max_requests_per_intent: int = 0
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
class QueryFacets:
    """The stated parts of one query, for adapters whose grammar needs fields.

    A consumer authors the query text and these facets together, so they cannot
    drift apart. An adapter selects the facets its own API accepts; it must never
    recover them by re-parsing the text. A blank facet means the consumer did not
    state that dimension, and the adapter falls back to its intent's scope.
    """

    condition: str = ""
    intervention: str = ""
    population: str = ""
    outcome: str = ""

    def __post_init__(self) -> None:
        for name in ("condition", "intervention", "population", "outcome"):
            object.__setattr__(self, name, " ".join(getattr(self, name).split()))

    def phrases(self) -> tuple[str, ...]:
        """Return the stated facets in a stable order, without blanks."""
        return tuple(
            value
            for value in (
                self.condition,
                self.intervention,
                self.population,
                self.outcome,
            )
            if value
        )


@dataclass(frozen=True)
class SourceQueryIntent:
    """One provider-agnostic query intent supplied by an upstream consumer."""

    text: str
    tracks: tuple[str, ...] = ()
    document_refs: tuple[str, ...] = ()
    target_refs: tuple[str, ...] = ()
    intent_id: str = ""
    facets: QueryFacets = field(default_factory=QueryFacets)

    def __post_init__(self) -> None:
        if self.intent_id:
            return
        material = "\n".join(
            (
                self.text,
                *self.tracks,
                *self.document_refs,
                *self.target_refs,
                *self.facets.phrases(),
            )
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
    target_refs: tuple[str, ...] = ()
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
    source_role: str = "unknown"

    def __post_init__(self) -> None:
        if not self.program_name.strip():
            raise ValueError("development program name cannot be empty")
        if self.record_type not in DEVELOPMENT_RECORD_TYPES:
            raise ValueError(f"unknown development record type: {self.record_type}")
        if self.source_role not in SOURCE_ROLES:
            raise ValueError(f"unknown source role: {self.source_role}")


@dataclass(frozen=True)
class SafetyObservationRecord:
    """One structured, non-causal safety observation from a source record."""

    product_name: str
    record_type: str
    source_system: str
    label: str
    detail: str = ""
    report_count: int | None = None
    qualification: str = ""
    source_role: str = "unknown"

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("safety product name cannot be empty")
        if self.record_type not in SAFETY_RECORD_TYPES:
            raise ValueError(f"unknown safety record type: {self.record_type}")
        if self.source_system not in SAFETY_SOURCE_SYSTEMS:
            raise ValueError(f"unknown safety source system: {self.source_system}")
        if not self.label.strip():
            raise ValueError("safety observation label cannot be empty")
        if self.report_count is not None and self.report_count < 0:
            raise ValueError("safety report count cannot be negative")
        if self.source_system == "faers" and self.report_count is None:
            raise ValueError("FAERS report count is required")
        if self.source_system != "faers" and self.report_count is not None:
            raise ValueError("only FAERS observations may carry a report count")
        if self.source_role not in SOURCE_ROLES:
            raise ValueError(f"unknown source role: {self.source_role}")


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
    safety_observations: list[SafetyObservationRecord] = field(default_factory=list)
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
        self.url = _canonical_url(self.url)
        if self.evidence_role not in FINDING_ROLES:
            raise ValueError(f"unknown finding evidence role: {self.evidence_role}")
        self.development_records = list(dict.fromkeys(self.development_records))
        self.safety_observations = list(dict.fromkeys(self.safety_observations))
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


def _canonical_url(url: str) -> str:
    """Normalize source identity without discarding meaningful query options."""
    split = urlsplit(url.strip())
    if not split.scheme or not split.netloc:
        return url.strip()
    query = "&".join(
        part
        for part in split.query.split("&")
        if part
        and not unquote_plus(part.partition("=")[0]).casefold().startswith("utm_")
    )
    host = split.netloc.casefold()
    return urlunsplit((split.scheme.casefold(), host, split.path, query, ""))


class SearcherLLMClientProtocol(Protocol):
    """Contract searcher requires from any injected LLM client.

    Library code depends only on this Protocol - the concrete client
    (OpenAIClient, a mock, anything) is passed in by the caller.

    Deliberately named apart from the other services' ``LLMClientProtocol``: this
    one requires a web-search capability, not schema-bound completion, so a client
    that satisfies one does not satisfy the other. The names differ because the
    contracts differ.
    """

    def search_web(self, query: str, *, max_tokens: int, max_uses: int) -> Any:
        ...


def merge_findings(existing: Finding, incoming: Finding) -> Finding:
    """Merge duplicate URLs without discarding retrieval or source provenance."""
    existing_was_evidence = existing.evidence_role == "evidence"
    incoming_is_evidence = incoming.evidence_role == "evidence"
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
    existing.safety_observations = list(
        dict.fromkeys(
            [*existing.safety_observations, *incoming.safety_observations]
        )
    )
    # A duplicate retrieved as evidence in any lane remains eligible for
    # reasoning, but its reasoning excerpt must also come from an evidence
    # retrieval path. A longer reference/catalog description must never leak
    # into the LLM merely because another lane found the same URL as evidence.
    if incoming_is_evidence:
        existing.evidence_role = "evidence"
    # `source_lanes` is the authoritative multi-source provenance. Keep the
    # first lane as the canonical scalar value rather than embedding a brittle
    # global ranking that every new adapter would need to modify.
    existing.source = existing.source_lanes[0] if existing.source_lanes else existing.source
    if incoming_is_evidence and not existing_was_evidence:
        existing.excerpt = incoming.excerpt
        existing.excerpt_source_lane = (
            incoming.excerpt_source_lane or incoming.source
            if incoming.excerpt
            else ""
        )
    elif (
        incoming.excerpt
        and incoming_is_evidence == existing_was_evidence
        and len(incoming.excerpt) > len(existing.excerpt or "")
    ):
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


@dataclass
class SearchReport:
    """What one free-text search produced, and what every lane did to produce it.

    Two fields because a reader needs both and they answer different questions.
    `findings` is the deduplicated union, which is what there is to read. `outcomes`
    is one entry per native request, which is the only place an empty lane, a skipped
    lane and a failed lane stay distinguishable — they are identical in `findings`,
    where all three are absence.

    Kept together rather than returned separately so a caller cannot render the
    findings while dropping the outcomes, which is exactly what happened before.
    """

    findings: list["Finding"] = field(default_factory=list)
    outcomes: list["SearchOutcome"] = field(default_factory=list)


def outcomes_to_dicts(outcomes: list["SearchOutcome"]) -> list[dict]:
    """Project outcomes to what a reader needs: which lane, what it asked, what it got.

    The native query, not the text a user typed. They differ for every field-addressed
    source — a typed sentence reaches ClinicalTrials.gov as `condition:<that sentence>`
    and returns nothing, and no reader could diagnose that from the sentence alone.

    `returned` counts what the request itself returned, before cross-lane deduplication.
    So the per-lane numbers may exceed the number of findings shown, and that is the
    honest reading: two lanes that both found one URL each did each return one.
    """
    return [
        {
            "source": outcome.request.source,
            "query": outcome.request.query,
            "status": outcome.status,
            "error": outcome.error,
            "returned": len(outcome.findings),
        }
        for outcome in outcomes
    ]


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
