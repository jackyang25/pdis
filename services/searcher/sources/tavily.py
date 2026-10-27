"""Tavily web search, executed through an injected connector.

The second web lane, and deliberately a second one rather than a replacement. `web` asks a
model a question and harvests the URLs it cites; this asks a search API a query and reads what
it returns. They behave differently enough that the choice should be made on measured results
from one document, not on argument, so both can run at once and be compared in the Searches
panel a field already offers.

What the comparison is about, measured on a real run of `web`:

    findings per search        1.4      (PubMed, for scale: 18.9)
    searches returning nothing 162/322
    excerpt                    the model's sentence about the page

The third line is the one that matters. A `web` excerpt is a paraphrase, sometimes in the
query's language rather than the source's, and downstream an insight quotes it. So a passage
presented as the source's words is the model's. Tavily returns content extracted from the
page, which is what the rest of the lanes already return.

`plan` is `web`'s, unchanged: one request per query, query text untouched. The queries are
already keyword-shaped - eight words at the median, none over twelve - so nothing needed
rewriting for a search API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..calls import provider_call
from ..errors import RetrievalError
from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .planning import request_lineage

TAVILY_INTEGRATION = "tavily"

#: Results per query. `web` yielded 1.4 findings per search, so ten is generous rather than
#: tight; the cap exists so one query cannot dominate an attribute's finding budget.
MAX_RESULTS = 10

#: Tavily allows 1,000 requests a minute on a production key (100 on a development key, which
#: answers 429 here and is retried in paced slots). Ten calls a second stays well inside the
#: production limit; unpaced, a Drafter run's burst of 32 concurrent searches drew 429s.
MIN_REQUEST_INTERVAL_SECONDS = 0.1

#: Long enough for the passage a number or a claim sits in, short enough that a page of
#: boilerplate cannot crowd out the rest of a batch. The same bound the literature lanes use.
MAX_EXCERPT_CHARS = 1200


class TavilySource:
    spec = SourceSpec(
        key="tavily",
        label="Tavily",
        # `web` allows 32. The same, so a comparison run is not also a comparison of
        # concurrency: a lane that is throttled differently will look slower for a reason that
        # has nothing to do with what it returns.
        worker_limit=32,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        # Declared, so the source disables itself when no key is configured rather than
        # failing every request. `unconfigured_source_keys` reads this.
        integration_key=TAVILY_INTEGRATION,
        attribution=SourceAttribution(label="Tavily", url="https://tavily.com"),
        # No `evidence_domains`, like `web`: a general web search serves every field. Gating
        # it would make this lane answer a different question from the one it is compared
        # against.
        evidence_class="general",
        jurisdiction="global",
        reads=("text",),
        feeds=("insights",),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for query in intent.queries:
            intent_ids, input_queries, document_refs = request_lineage([query])
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=query.text,
                    tracks=query.tracks,
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TAVILY_INTEGRATION,
                    operation="search",
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
        # `max_tokens` bounds a model's generation and means nothing to a search API.
        # Accepted because the adapter contract passes it to every lane, ignored here
        # rather than reinterpreted into a result limit that would silently differ from the
        # cap the spec declares.
        connector = runtime.integrations.get(TAVILY_INTEGRATION)
        if connector is None or not callable(getattr(connector, "search", None)):
            raise RetrievalError("Tavily", "not_configured", "Tavily connector is not configured")
        limit = self.spec.max_results
        result = provider_call(
            runtime,
            rate_group=self.spec.rate_group,
            interval_seconds=self.spec.request_interval_seconds,
            operation="search",
            arguments={"query": request.query, "max_results": limit},
            load=lambda: connector.search(request.query, max_results=limit),
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in _records(result):
            url = _text(record.get("url"))
            if not url:
                continue
            findings.append(
                Finding(
                    url=url,
                    # The page's own title, falling back to its URL. Never a generated one.
                    title=_text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=_excerpt(record),
                    source=self.spec.key,
                )
            )
        return findings


def _records(result: Any) -> list[dict[str, Any]]:
    """The results list, or a stated failure.

    Tavily reports an error in the body rather than only by status, so a 200 carrying an
    error is a failure. Returning an empty list for one would record the search as having run
    and found nothing, which is a different fact.
    """
    if not isinstance(result, dict):
        raise RetrievalError("Tavily", "invalid_response", "unexpected result shape")
    if error := result.get("error"):
        raise RetrievalError("Tavily", "rejected", f"Tavily failed: {error}")
    records = result.get("results")
    if not isinstance(records, list):
        raise RetrievalError("Tavily", "invalid_response", "no results list")
    return [record for record in records if isinstance(record, dict)]


def _excerpt(record: dict[str, Any]) -> str | None:
    """The page's own words: `content`, Tavily's extract of the passage the query matched.

    `None` rather than an empty string when there is nothing: `Finding.excerpt` is documented
    as absent-or-a-passage, and an empty passage downstream reads as a source that stated
    nothing rather than as one whose text could not be extracted.
    """
    text = _text(record.get("content"))
    if not text:
        return None
    if len(text) > MAX_EXCERPT_CHARS:
        return text[:MAX_EXCERPT_CHARS].rstrip() + "..."
    return text


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""
