"""Europe PMC adapter executed through an injected ToolUniverse connector.

A third literature lane, and not a redundant one. Europe PMC indexes what PubMed does and
adds what PubMed does not: preprints from bioRxiv and medRxiv, and open-access full text.
Both matter for a competitive read - a trial result reaches a preprint server before a
journal, so a lane that only sees journals sees the landscape late.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..dates import iso_partial_date, partial_date
from ..errors import RetrievalError
from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks, build_europepmc_query, queries_for_track
from .planning import request_lineage
from .tooluniverse_records import TOOLUNIVERSE_INTEGRATION, run_tool

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
        # The same Boolean shape as PubMed: the intent's anchor AND any query's subject.
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
                    query=build_europepmc_query(intent, track, queries),
                    tracks=(track,),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TOOLUNIVERSE_INTEGRATION,
                    operation=SEARCH_TOOL,
                    options=(("published_since", intent.published_since),),
                )
            )
        return requests

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        result = run_tool(
            runtime,
            self.spec,
            SEARCH_TOOL,
            {
                "query": _bounded(request.query, request.option("published_since")),
                "limit": self.spec.max_results,
            },
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in _records(result):
            source_db = _text(record.get("source_db"))
            article_id = _text(record.get("article_id"))
            url = _text(record.get("doi_url")) or _text(record.get("url"))
            # Europe PMC's own record identity. A record without one cannot be told
            # apart from another, so it is not kept - as a trial without an NCT ID is not.
            if not url or not (source_db and article_id):
                continue
            excerpt = _text(record.get("abstract"))
            if len(excerpt) > MAX_EXCERPT_CHARS:
                excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."
            published_at, precision = _published(record)
            findings.append(
                Finding(
                    url=url,
                    title=_text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    published_at=published_at,
                    published_precision=precision,
                    excerpt=excerpt or None,
                    identifiers={
                        "doi": _text(record.get("doi")),
                        "pmid": _text(record.get("pmid")),
                        "pmcid": _text(record.get("pmcid")),
                    },
                    record_key=f"europepmc:{source_db}/{article_id}",
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
    """The tool's article list, or a stated failure.

    The tool reports an upstream failure as a single article titled "Error" whose `error`
    field holds the reason, inside a successful envelope. Read as records, that became a
    record with no URL, was skipped, and the request reported success with nothing found.
    """
    if isinstance(result, dict):
        if result.get("status") == "error" or result.get("error"):
            raise RetrievalError(
                "Europe PMC", "tool_error", str(result.get("error") or "search failed")
            )
        result = result.get("data", [])
    if not isinstance(result, list):
        raise RetrievalError("Europe PMC", "invalid_response", "unexpected result shape")
    records = [item for item in result if isinstance(item, dict)]
    for record in records:
        if record.get("error"):
            raise RetrievalError("Europe PMC", "tool_error", str(record["error"]))
    return records


def _published(record: dict[str, Any]) -> tuple[datetime | None, str]:
    """The first publication date when the tool returns one, else the year alone.

    A year is kept as a year: it is not 1 January, and a window starting mid-year must
    not drop a record that may have been published after it.
    """
    published_at, precision = iso_partial_date(record.get("first_publication_date"))
    if published_at is not None:
        return published_at, precision
    year = str(record.get("year") or "").strip()
    if not year.isdigit() or len(year) != 4:
        return None, ""
    return partial_date(int(year))


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""
