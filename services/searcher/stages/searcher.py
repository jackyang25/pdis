"""Single-stage web search: query -> list[Finding].

Uses Anthropic's native web_search tool via the injected LLM client.
The model invokes web_search internally, then produces a text response
where passages are annotated with `web_search_result_location`
citations. We extract one Finding per unique cited URL - the excerpt
is the actual cited text from the source page (NOT the model's prose).
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
    """Extract Findings from an Anthropic Messages API response.

    Walks `response.content` for text blocks, then iterates each text
    block's `citations` list for `web_search_result_location` citations.
    Each unique cited URL becomes one Finding. Dedup by URL, keep the
    first (typically most relevant) cited_text.

    The Anthropic SDK exposes citations as either object attributes or
    dict keys depending on version - use defensive `_get` access.
    """
    content_blocks = _get(response, "content", default=[]) or []
    findings_by_url: dict[str, Finding] = {}

    for block in content_blocks:
        if _get(block, "type") != "text":
            continue
        citations = _get(block, "citations", default=[]) or []
        for cite in citations:
            if _get(cite, "type") != "web_search_result_location":
                continue
            url = _get(cite, "url", default="") or ""
            if not url or url in findings_by_url:
                continue
            title = _get(cite, "title", default="") or url
            cited_text = _get(cite, "cited_text", default="") or ""
            excerpt = cited_text.strip()
            if not excerpt:
                continue
            findings_by_url[url] = Finding(
                url=url,
                title=title,
                excerpt=excerpt,
                query=query,
                retrieved_at=retrieved_at,
                published_at=None,
            )

    if not findings_by_url:
        logger.warning(
            "Web search returned no citations. The model may not have "
            "invoked the web_search tool, or the response shape has changed. "
            "Inspect `response.content` to diagnose."
        )
    return list(findings_by_url.values())


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Safe attribute/key access. Tries attr first, then dict key."""
    val = getattr(obj, name, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default
