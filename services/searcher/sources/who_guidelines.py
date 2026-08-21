"""WHO guidelines adapter executed through an injected ToolUniverse connector.

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
"""

from __future__ import annotations

import logging
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
from .literature import active_tracks
from .planning import facet_groups, request_lineage

TOOLUNIVERSE_INTEGRATION = "tooluniverse"
SEARCH_TOOL = "WHO_Guidelines_Search"
FULL_TEXT_TOOL = "WHO_Guideline_Full_Text"
#: Deliberately small. The search returns a title and a URL and no text at all, so every
#: result needs a second call to become a finding worth reasoning over, and each call is
#: its own request. WHO's guideline set for one condition is a curated handful rather than
#: a literature corpus, so the top few by relevance is the whole useful answer.
MAX_RESULTS = 5
MAX_EXCERPT_CHARS = 8_000

logger = logging.getLogger(__name__)


class WHOGuidelinesSource:
    spec = SourceSpec(
        key="who_guidelines",
        label="WHO Guidelines",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL, FULL_TEXT_TOOL),
        attribution=SourceAttribution(
            label="World Health Organization",
            url="https://www.who.int/publications/who-guidelines",
            prefix="Guidance provided by",
        ),
        evidence_class="guidance",
        jurisdiction="global",
        # The tool takes one topic and nothing else, so the condition is the whole
        # request. Declaring only what it can act on is the point of `reads`.
        reads=("text", "condition"),
        feeds=("insights",),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for scope, queries in facet_groups(
            intent,
            fields=("condition",),
            fallbacks={"condition": intent.indication or intent.topic},
            anchors=("condition",),
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            condition = scope["condition"]
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=f"condition:{condition}",
                    tracks=tuple(active_tracks(intent)),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TOOLUNIVERSE_INTEGRATION,
                    operation=SEARCH_TOOL,
                    options=(
                        ("condition", condition),
                        ("limit", str(MAX_RESULTS)),
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
                "query": request.option("condition"),
                "limit": int(request.option("limit", str(MAX_RESULTS))),
            },
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in _records(result):
            url = _text(record.get("url"))
            if not url:
                continue
            # The tool also returns non-guideline WHO pages. Only a record it marks as a
            # guideline is one, because the class is "an authority's position" and a
            # publication list is not a position.
            if record.get("is_guideline") is False:
                continue
            # The search returns no text - `content` and `description` come back null - so
            # a finding built from it alone would be a title. One further call per result
            # is what makes it a passage an insight can rest on, and a lane whose findings
            # carry no text is a lane that feeds nothing while declaring that it does.
            excerpt = (
                _text(record.get("content"))
                or _text(record.get("description"))
                or _full_text(connector, url)
            )
            if len(excerpt) > MAX_EXCERPT_CHARS:
                excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."
            findings.append(
                Finding(
                    url=url,
                    title=_text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=excerpt or None,
                    source=self.spec.key,
                )
            )
        return findings


def _full_text(connector: Any, url: str) -> str:
    """Fetch one guideline's page text, or return blank.

    A failure here degrades the finding to its title rather than failing the lane: the
    guideline exists and is citable either way, and losing the whole request because one
    page would not load would be a worse answer than a thin one.
    """
    try:
        page = connector.run(FULL_TEXT_TOOL, {"url": url})
    except Exception:  # noqa: BLE001 - a page that will not load is not a lane failure
        logger.warning("WHO guideline text unavailable: %s", url)
        return ""
    if not isinstance(page, dict):
        return ""
    return _text(page.get("main_content")) or _text(page.get("overview"))


def _records(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        if result.get("status") == "error" or result.get("error"):
            raise RuntimeError(str(result.get("error") or "WHO Guidelines failed"))
        for key in ("data", "results", "guidelines"):
            if isinstance(result.get(key), list):
                result = result[key]
                break
    if not isinstance(result, list):
        raise RuntimeError("WHO Guidelines returned an unexpected result shape")
    return [item for item in result if isinstance(item, dict)]


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""
