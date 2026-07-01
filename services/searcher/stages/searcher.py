"""Single-stage web search: query -> list[Finding].

Uses OpenAI's Responses API web_search tool via the injected LLM client.
The model invokes web_search internally, then produces text content with
`url_citation` annotations. We extract one Finding per unique cited URL.
"""

from __future__ import annotations

import logging
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
                excerpt = text[start:end].strip() or None
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


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Safe attribute/key access. Tries attr first, then dict key."""
    val = getattr(obj, name, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default
