"""WHO guidelines from IRIS, WHO's institutional repository, through its search API.

The first lane in the `guidance` class, and the one that most directly serves an LMIC
read. A regulator says what is permitted in its own market; WHO says what should be done,
and that is what ministries of health and procurement bodies follow where no national
regulator has ruled. For a programme aimed at the global south, "what does WHO recommend
for this condition" is often the standard a target has to beat.

Guidance is not regulatory, and the two are separate classes for a reason a reader can
check: someone asking what a label permits would not accept a WHO recommendation, and
someone asking what the recommended regimen is would not accept an FDA label. Sources in
one class have to be alternatives.

Findings are `evidence`. The first draft of this lane marked them `reference` by analogy
to a company announcement, and that analogy was wrong: a press release is an interested
party's claim about its own product, while a WHO guideline is an independent authority's
published position with citable text. "WHO recommends three doses" is exactly the kind of
standard a target has to be judged against, and its excerpt is the page's own words rather
than a model's summary, so it can support a quantitative claim like any other document.

What makes a record a guideline is WHO's own subject tag, `WHO guideline`, which IRIS
applies to the guidelines its Guidelines Review Committee approved. The search is filtered
by it at the provider. The lane once scraped WHO's website instead: a health-topic page's
publication links when the condition had one, and otherwise the site's list of recent
guidelines - whatever WHO had last published, on any subject, filed as guidance for this
one. The excerpt is the record's abstract, WHO's own summary of the guideline, which the
search returns, so a guideline costs no second call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..calls import provider_request
from ..dates import iso_partial_date
from ..errors import RetrievalError
from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks
from .planning import request_lineage
from .records import bounded, text

SEARCH_URL = "https://iris.who.int/server/api/discover/search/objects"
#: Small on purpose: WHO's guideline set for one condition is a curated handful rather
#: than a literature corpus, so the top few by relevance is the whole useful answer.
MAX_RESULTS = 5
MAX_EXCERPT_CHARS = 8_000
#: IRIS publishes no rate limit. Four calls a second, process-wide, answered cleanly in a
#: measured burst (a third of a second each); two workers keep that pace.
MIN_REQUEST_INTERVAL_SECONDS = 0.25


class WHOGuidelinesSource:
    spec = SourceSpec(
        key="who_guidelines",
        label="WHO Guidelines",
        worker_limit=2,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        attribution=SourceAttribution(
            label="World Health Organization",
            url="https://www.who.int/publications/who-guidelines",
            prefix="Guidance provided by",
        ),
        evidence_class="guidance",
        jurisdiction="global",
        # The condition is the whole request. Declaring only what it can act on is the
        # point of `reads`.
        reads=("text", "condition"),
        feeds=("insights",),
        # The `dateIssued` filter.
        honors_date_bound=True,
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        # The condition is the whole request and is the intent's anchor, so no query can
        # vary it: one request per intent, carrying every query in its lineage.
        intent_ids, input_queries, document_refs = request_lineage(list(intent.queries))
        condition = (intent.indication or intent.topic).strip()
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=condition,
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                options=(("published_since", intent.published_since),),
            )
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        filters = [
            ("f.subject", "WHO guideline,equals"),
            # English: a guideline's translations are separate records with the same
            # recommendations, and would fill the handful this lane keeps.
            ("f.language", "en,equals"),
        ]
        if since := request.option("published_since"):
            filters.append(("f.dateIssued", f"[{since} TO *],equals"))
        payload = provider_request(
            runtime,
            self.spec,
            operation="discover/search",
            url=SEARCH_URL,
            query={
                "query": request.query,
                "dsoType": "ITEM",
                "size": self.spec.max_results,
                **dict(filters),
            },
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for item in _items(payload):
            handle = text(item.get("handle"))
            if not handle:
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            url = _value(metadata, "dc.identifier.uri") or f"https://iris.who.int/handle/{handle}"
            published_at, precision = iso_partial_date(_value(metadata, "dc.date.issued"))
            findings.append(
                Finding(
                    url=url,
                    title=_value(metadata, "dc.title") or text(item.get("name")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=bounded(_value(metadata, "dc.description.abstract"), MAX_EXCERPT_CHARS) or None,
                    published_at=published_at,
                    published_precision=precision,
                    record_key=f"who_guidelines:{handle}",
                    source=self.spec.key,
                )
            )
        return findings


def _items(payload: Any) -> list[dict[str, Any]]:
    """The search's items, or a stated failure."""
    result = (
        ((payload.get("_embedded") or {}).get("searchResult") or {})
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(result, dict) or "page" not in result:
        raise RetrievalError("WHO Guidelines", "invalid_response", "no search result")
    objects = (result.get("_embedded") or {}).get("objects") or []
    return [
        item
        for entry in objects
        if isinstance(entry, dict)
        and isinstance(item := (entry.get("_embedded") or {}).get("indexableObject"), dict)
    ]


def _value(metadata: dict[str, Any], field: str) -> str:
    """The first value IRIS records for one metadata field."""
    values = metadata.get(field)
    first = values[0] if isinstance(values, list) and values else {}
    return text(first.get("value")) if isinstance(first, dict) else ""
