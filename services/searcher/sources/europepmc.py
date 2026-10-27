"""Europe PMC literature search, called directly through its REST API.

A third literature lane, and not a redundant one. Europe PMC indexes what PubMed does and
adds what PubMed does not: preprints from bioRxiv and medRxiv, and open-access full text.
Both matter for a competitive read - a trial result reaches a preprint server before a
journal, so a lane that only sees journals sees the landscape late.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..calls import provider_request
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
from .records import bounded, text

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAX_RESULTS = 10
#: Europe PMC publishes no rate limit and asks clients to be reasonable: ten calls a
#: second, process-wide, is well inside what it answers.
MIN_REQUEST_INTERVAL_SECONDS = 0.1


class EuropePMCSource:
    spec = SourceSpec(
        key="europepmc",
        label="Europe PMC",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
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
        payload = provider_request(
            runtime,
            self.spec,
            operation="search",
            url=SEARCH_URL,
            query={
                "query": _bounded(request.query, request.option("published_since")),
                "format": "json",
                # `core` carries the abstract, the identifiers and the first publication
                # date; `lite` carries none of the three.
                "resultType": "core",
                "pageSize": self.spec.max_results,
            },
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in _records(payload):
            source_db = text(record.get("source"))
            article_id = text(record.get("id"))
            # Europe PMC's own record identity. A record without one cannot be told
            # apart from another, so it is not kept - as a trial without an NCT ID is not.
            if not (source_db and article_id):
                continue
            doi = text(record.get("doi"))
            url = (
                f"https://doi.org/{doi}"
                if doi
                else f"https://europepmc.org/article/{source_db}/{article_id}"
            )
            published_at, precision = _published(record)
            findings.append(
                Finding(
                    url=url,
                    title=text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    published_at=published_at,
                    published_precision=precision,
                    excerpt=bounded(text(record.get("abstractText"))) or None,
                    identifiers={
                        "doi": doi,
                        "pmid": text(record.get("pmid")),
                        "pmcid": text(record.get("pmcid")),
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


def _records(payload: Any) -> list[dict[str, Any]]:
    """The search's result list, or a stated failure.

    A query Europe PMC cannot parse is answered with an empty list and a 200, which is the
    same answer as a query that matched nothing; only a missing list is a failure.
    """
    results = (
        (payload.get("resultList") or {}).get("result")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(results, list):
        raise RetrievalError("Europe PMC", "invalid_response", "no result list")
    return [record for record in results if isinstance(record, dict)]


def _published(record: dict[str, Any]) -> tuple[datetime | None, str]:
    """The first publication date when the record states one, else the year alone.

    A year is kept as a year: it is not 1 January, and a window starting mid-year must
    not drop a record that may have been published after it.
    """
    published_at, precision = iso_partial_date(record.get("firstPublicationDate"))
    if published_at is not None:
        return published_at, precision
    year = text(record.get("pubYear"))
    if not year.isdigit() or len(year) != 4:
        return None, ""
    return partial_date(int(year))
