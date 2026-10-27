"""Semantic Scholar paper search, called directly through its Graph API."""

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
from .literature import (
    active_tracks,
    build_semantic_scholar_query,
    queries_for_track,
)
from .planning import request_lineage
from .records import bounded, text

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
#: The rate group, and the key's name in `SearchRuntime.credentials`.
SEMANTIC_SCHOLAR = "semantic_scholar"
MAX_RESULTS = 10
#: An issued key is limited to one request per second across all endpoints. Stay just
#: below it.
MIN_REQUEST_INTERVAL_SECONDS = 1.1
#: What a finding reads, and nothing else. `tldr` is fetched only as the excerpt of a
#: paper without an abstract.
FIELDS = "paperId,title,abstract,tldr,year,publicationDate,externalIds,url"


class SemanticScholarSource:
    spec = SourceSpec(
        key="semantic_scholar",
        label="Semantic Scholar",
        # Calls start one a second, so more workers would only wait their turn.
        worker_limit=2,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        rate_group=SEMANTIC_SCHOLAR,
        # Required, not optional: keyless calls share one public pool, which answered
        # the first call of a live check with 429. A lane that fails every request
        # without its key reports itself unconfigured instead.
        required_credential=SEMANTIC_SCHOLAR,
        attribution=SourceAttribution(
            label="Semantic Scholar",
            url="https://www.semanticscholar.org/?utm_source=api",
            prefix="Academic metadata provided by",
        ),
        evidence_class="literature",
        jurisdiction="global",
        reads=("text", "condition", "intervention", "product", "population", "outcome", "subject"),
        feeds=("insights",),
        # `publicationDateOrYear`, which bounds by date and admits a paper dated only
        # by its year when that year can fall inside the window.
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
                    query=build_semantic_scholar_query(intent, track, queries),
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
        query: dict[str, Any] = {
            "query": request.query,
            "limit": self.spec.max_results,
            "fields": FIELDS,
        }
        if since := request.option("published_since"):
            query["publicationDateOrYear"] = f"{since}:"
        key = runtime.credential(SEMANTIC_SCHOLAR)
        payload = provider_request(
            runtime,
            self.spec,
            operation="paper/search",
            url=SEARCH_URL,
            query=query,
            auth_headers={"x-api-key": key} if key else None,
        )
        records = payload.get("data") if isinstance(payload, dict) else None
        # A search matching nothing omits `data`; one that failed carries no `total`.
        if records is None and isinstance(payload, dict) and "total" in payload:
            records = []
        if not isinstance(records, list):
            raise RetrievalError("Semantic Scholar", "invalid_response", "no result list")
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            paper_id = text(record.get("paperId"))
            if not paper_id:
                continue
            ids = record.get("externalIds") if isinstance(record.get("externalIds"), dict) else {}
            doi = text(ids.get("DOI"))
            url = f"https://doi.org/{doi}" if doi else (
                text(record.get("url")) or f"https://www.semanticscholar.org/paper/{paper_id}"
            )
            abstract = text(record.get("abstract"))
            tldr = record.get("tldr") if isinstance(record.get("tldr"), dict) else {}
            # A TLDR is Semantic Scholar's model-written summary, not the paper's words.
            excerpt = abstract or text(tldr.get("text"))
            published_at, precision = _published(record)
            findings.append(
                Finding(
                    url=url,
                    title=text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=bounded(excerpt) or None,
                    excerpt_kind="passage" if abstract else "generated",
                    published_at=published_at,
                    published_precision=precision,
                    identifiers={
                        "doi": doi,
                        "pmid": text(ids.get("PubMed")),
                        "pmcid": text(ids.get("PubMedCentral")),
                    },
                    record_key=f"semantic_scholar:{paper_id}",
                    source=self.spec.key,
                )
            )
        return findings


def _published(record: dict[str, Any]) -> tuple[datetime | None, str]:
    """The publication date when the record states one, else its year alone."""
    published_at, precision = iso_partial_date(record.get("publicationDate"))
    if published_at is not None:
        return published_at, precision
    year = record.get("year")
    if isinstance(year, int) and 1000 <= year <= 9999:
        return partial_date(year)
    return None, ""
