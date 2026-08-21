"""Europe PMC adapter executed through an injected ToolUniverse connector.

A third literature lane, and not a redundant one. Europe PMC indexes what PubMed does and
adds what PubMed does not: preprints from bioRxiv and medRxiv, and open-access full text.
Both matter for a competitive read - a trial result reaches a preprint server before a
journal, so a lane that only sees journals sees the landscape late.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks, build_semantic_scholar_query, queries_for_track
from .planning import request_lineage

TOOLUNIVERSE_INTEGRATION = "tooluniverse"
SEARCH_TOOL = "EuropePMC_search_articles"
MAX_RESULTS = 10
MAX_EXCERPT_CHARS = 16_000


class EuropePMCSource:
    spec = SourceSpec(
        key="europepmc",
        label="Europe PMC",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL,),
        attribution=SourceAttribution(
            label="Europe PMC",
            url="https://europepmc.org/",
            prefix="Literature metadata provided by",
        ),
        evidence_class="literature",
        jurisdiction="global",
        # The same grammar as the other literature lanes: a plain-text expression built
        # from the intent's anchor and each query's subject phrase.
        reads=(
            "text",
            "condition",
            "intervention",
            "product",
            "population",
            "outcome",
            "subject",
        ),
        feeds=("insights",),
        honors_date_bound=True,
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for track in active_tracks(intent):
            queries = queries_for_track(intent, track)
            intent_ids, input_queries, document_refs = request_lineage(queries)
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    # Europe PMC accepts a Lucene-like expression, so the plain-text
                    # compiler is the right grammar rather than a fielded one.
                    query=build_semantic_scholar_query(intent, track, queries),
                    tracks=(track,),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TOOLUNIVERSE_INTEGRATION,
                    operation=SEARCH_TOOL,
                    options=(
                        ("limit", str(MAX_RESULTS)),
                        ("published_since", intent.published_since),
                    ),
                )
            )
        return requests

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        connector = runtime.integrations.get(TOOLUNIVERSE_INTEGRATION)
        if connector is None or not callable(getattr(connector, "run", None)):
            raise RuntimeError("ToolUniverse connector is not configured")
        result = connector.run(
            SEARCH_TOOL,
            {
                "query": _bounded(request.query, request.option("published_since")),
                "limit": int(request.option("limit", str(MAX_RESULTS))),
            },
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in _records(result):
            url = _text(record.get("doi_url")) or _text(record.get("url"))
            if not url:
                continue
            excerpt = _text(record.get("abstract"))
            if len(excerpt) > MAX_EXCERPT_CHARS:
                excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."
            findings.append(
                Finding(
                    url=url,
                    title=_text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    published_at=_published(record),
                    excerpt=excerpt or None,
                    source=self.spec.key,
                )
            )
        return findings


def _bounded(query: str, published_since: str) -> str:
    """Add the window as Europe PMC's own date field, not as a term to match.

    `FIRST_PDATE` is a field in the provider's query grammar, which is why the bound
    belongs in the expression here and a year would not: `2026` as a bare term matches
    records mentioning it, while `FIRST_PDATE:[2026-01-01 TO ...]` matches records
    published then. Verified against live results - unbounded returns a spread of years,
    bounded returns only the window.

    The upper bound is a fixed far date because the field needs a range and the caller
    stated only a lower one.
    """
    if not published_since:
        return query
    return f"{query} AND FIRST_PDATE:[{published_since} TO 3000-12-31]"


def _records(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        if result.get("status") == "error" or result.get("error"):
            raise RuntimeError(str(result.get("error") or "Europe PMC failed"))
        result = result.get("data", [])
    if not isinstance(result, list):
        raise RuntimeError("Europe PMC returned an unexpected result shape")
    return [item for item in result if isinstance(item, dict)]


def _published(record: dict[str, Any]) -> datetime | None:
    """Europe PMC states a publication year, not a date.

    Read as 1 January of that year, which is the earliest date consistent with it. A
    window is a lower bound, so the earliest reading is the one that cannot exclude a
    record the caller asked for.
    """
    year = _text(record.get("year"))
    if not year.isdigit() or len(year) != 4:
        return None
    return datetime(int(year), 1, 1, tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""
