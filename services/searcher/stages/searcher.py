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
    """Extract Findings from an Anthropic Messages API response (hybrid).

    Two passes:

    1. Walk `response.content` for `web_search_tool_result` blocks.
       Each inner `web_search_result` (url + title) becomes one Finding
       with `excerpt=None`. This is the raw search hit list.

    2. Walk text blocks' `citations` for `web_search_result_location`
       items. If a citation's url matches a Finding from pass 1, fill
       in that Finding's `excerpt` with the citation's `cited_text`.

    Net effect: Findings reflect what the search returned (not what the
    model chose to mention), but get useful excerpts when available.

    Dedup by URL across both passes - first occurrence wins.
    """
    content_blocks = _get(response, "content", default=[]) or []
    findings_by_url: dict[str, Finding] = {}

    # Pass 1: raw search hits
    for block in content_blocks:
        if _get(block, "type") != "web_search_tool_result":
            continue
        results = _get(block, "content", default=[]) or []
        for result in results:
            if _get(result, "type") != "web_search_result":
                continue
            url = _get(result, "url", default="") or ""
            if not url or url in findings_by_url:
                continue
            title = _get(result, "title", default="") or url
            findings_by_url[url] = Finding(
                url=url,
                title=title,
                query=query,
                retrieved_at=retrieved_at,
                excerpt=None,
                published_at=None,
            )

    # Pass 2: overlay cited excerpts where the model attributed text to a source
    for block in content_blocks:
        if _get(block, "type") != "text":
            continue
        citations = _get(block, "citations", default=[]) or []
        for cite in citations:
            if _get(cite, "type") != "web_search_result_location":
                continue
            url = _get(cite, "url", default="") or ""
            if not url:
                continue
            cited_text = _get(cite, "cited_text", default="") or ""
            cited_text = cited_text.strip()
            if not cited_text:
                continue
            finding = findings_by_url.get(url)
            if finding is None:
                # The model cited a URL that didn't appear in tool_result blocks
                # (rare - usually means the SDK didn't expose the tool_result).
                # Create a Finding for it anyway so we don't lose information.
                title = _get(cite, "title", default="") or url
                findings_by_url[url] = Finding(
                    url=url,
                    title=title,
                    query=query,
                    retrieved_at=retrieved_at,
                    excerpt=cited_text,
                    published_at=None,
                )
            elif finding.excerpt is None:
                finding.excerpt = cited_text

    if not findings_by_url:
        logger.warning(
            "Web search returned no results. The model may not have invoked "
            "the web_search tool, or the response shape has changed. Inspect "
            "`response.content` to diagnose (try running probe_search.py)."
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
