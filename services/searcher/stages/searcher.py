"""Single-stage web search: query -> list[Finding].

Uses OpenAI's Responses API web_search tool via the injected LLM client.
The model invokes web_search internally, then produces text content with
`url_citation` annotations. We extract one Finding per unique cited URL.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from ..models import Finding, SearcherLLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4000
DEFAULT_MAX_USES = 5


def search(
    query: str,
    llm_client: SearcherLLMClientProtocol,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_uses: int = DEFAULT_MAX_USES,
) -> list[Finding]:
    """Run one web search and return a list of Findings.

    Raises any exception from the underlying LLM client. Callers decide
    how to handle failure.
    """
    response = llm_client.search_web(query, max_tokens=max_tokens, max_uses=max_uses)
    retrieved_at = datetime.now(timezone.utc)
    return _parse_response_to_findings(response, query=query, retrieved_at=retrieved_at)


def _parse_response_to_findings(
    response: Any,
    *,
    query: str,
    retrieved_at: datetime,
) -> list[Finding]:
    """Extract Findings from an OpenAI Responses API response.

    Walks `response.output` for message items, then iterates each text
    content block's `annotations` for `url_citation` entries. Each
    unique URL becomes one Finding; the excerpt is the cited region
    of the model's output_text.

    Defensive `_get` access - SDK shape can vary slightly across
    versions.
    """
    output_items = _get(response, "output", default=[]) or []
    findings_by_url: dict[str, Finding] = {}

    for item in output_items:
        if _get(item, "type") != "message":
            continue
        blocks = _get(item, "content", default=[]) or []
        for block in blocks:
            text = _get(block, "text", default="") or ""
            annotations = _get(block, "annotations", default=[]) or []
            for ann in annotations:
                if _get(ann, "type") != "url_citation":
                    continue
                url = _get(ann, "url", default="") or ""
                if not url or url in findings_by_url:
                    continue
                title = _get(ann, "title", default="") or url
                start = _get(ann, "start_index", default=0) or 0
                end = _get(ann, "end_index", default=len(text)) or len(text)
                excerpt = _citation_context(text, start, end)
                findings_by_url[url] = Finding(
                    url=url,
                    title=title,
                    query=query,
                    retrieved_at=retrieved_at,
                    excerpt=excerpt,
                    published_at=None,
                    source="web",
                )

    if not findings_by_url:
        # Normal for niche/very-specific/non-English queries - the model searched
        # but found nothing citable. Not an error; just no web sources this query.
        logger.info("Web search: no citable sources for query %r", query)
    return list(findings_by_url.values())


def _citation_context(text: str, start: int, end: int) -> str | None:
    """Return the model-output claim surrounding one URL annotation.

    Responses annotations commonly span only the rendered citation link. That
    link is provenance, not evidence text. Preserve the bounded paragraph (or
    preceding sentence when the link occupies its own paragraph) so downstream
    qualitative reasoning sees the claim the citation was attached to. This is
    still model-output citation context—not a verbatim source passage—and
    strict quantitative extraction excludes web-owned excerpts accordingly.
    """
    if not text:
        return None
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    left = text.rfind("\n\n", 0, start)
    left = 0 if left < 0 else left + 2
    right = text.find("\n\n", end)
    right = len(text) if right < 0 else right
    paragraph = text[left:right]
    relative_start = start - left
    relative_end = end - left
    prior_boundaries = [
        match.end()
        for match in re.finditer(r"(?<=[.!?])\s+", paragraph[:relative_start])
    ]
    # Citation links are often a sentence of their own after the cited claim.
    # Keep that claim plus the citation, but not unrelated earlier sentences.
    sentence_left = prior_boundaries[-2] if len(prior_boundaries) >= 2 else 0
    following = re.search(r"(?<=[.!?])\s+", paragraph[relative_end:])
    sentence_right = (
        relative_end + following.end() if following is not None else len(paragraph)
    )
    context = paragraph[sentence_left:sentence_right].strip()
    citation = text[start:end].strip()
    if context and context != citation:
        return context[:2_000]

    # Some provider responses place the citation on a separate line. Attach it
    # to the immediately preceding bounded paragraph instead of storing a bare
    # markdown link as the excerpt.
    previous_end = max(0, left - 2)
    previous_left = text.rfind("\n\n", 0, previous_end)
    previous_left = 0 if previous_left < 0 else previous_left + 2
    previous = text[previous_left:previous_end].strip()
    combined = " ".join(part for part in (previous, citation) if part)
    return combined[:2_000] or None


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Safe attribute/key access. Tries attr first, then dict key."""
    val = getattr(obj, name, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default
