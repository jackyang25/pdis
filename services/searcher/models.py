"""Searcher data shapes and the LLM client contract it requires.

Public types live here - they are re-exported by __init__.py. Consumers
should import from `services.searcher`, never from this module directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class SourceSpec:
    """Public metadata and execution policy for one retrieval source adapter."""

    key: str
    label: str
    worker_limit: int
    default_enabled: bool = True


@dataclass(frozen=True)
class SourceQueryIntent:
    """One provider-agnostic query intent supplied by an upstream consumer."""

    text: str
    tracks: tuple[str, ...] = ()
    document_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalIntent:
    """Neutral context a source adapter uses to create native requests."""

    scope_ref: str
    topic: str
    description: str
    indication: str
    intervention_class: str
    queries: tuple[SourceQueryIntent, ...]


@dataclass(frozen=True)
class SearchRequest:
    """One immutable, source-native retrieval request."""

    scope_ref: str
    source: str
    query: str
    tracks: tuple[str, ...] = ()
    document_refs: tuple[str, ...] = ()
    options: tuple[tuple[str, str], ...] = ()

    def option(self, name: str, default: str = "") -> str:
        return dict(self.options).get(name, default)


@dataclass
class SearchOutcome:
    """One request result; empty success and adapter failure remain distinct."""

    request: SearchRequest
    findings: list["Finding"] = field(default_factory=list)
    status: str = "complete"
    error: str = ""


@dataclass
class SearchRuntime:
    """Injected capabilities available to adapters, never global provider state."""

    llm_client: "SearcherLLMClientProtocol"
    ncbi_api_key: str | None = None
    integrations: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalPath:
    """One exact query/lane path by which a URL was retrieved."""

    query: str
    lane: str


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
    # URL deduplication must not erase how a source was discovered. ``query``
    # and ``source`` remain the primary values for compatibility; these lists
    # retain every retrieval path merged into the Finding.
    queries: list[str] = field(default_factory=list)
    source_lanes: list[str] = field(default_factory=list)
    source_labels: dict[str, str] = field(default_factory=dict)
    retrieval_paths: list[RetrievalPath] = field(default_factory=list)
    title_source_lane: str = ""
    excerpt_source_lane: str = ""
    published_source_lane: str = ""

    def __post_init__(self) -> None:
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
    existing.retrieval_paths = list(
        dict.fromkeys([*existing.retrieval_paths, *incoming.retrieval_paths])
    )
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
