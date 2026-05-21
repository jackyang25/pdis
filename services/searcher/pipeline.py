"""Stateless searcher pipeline.

Wires the single stage (search) into one function. Mirrors the shape
of other services' pipelines so orchestration lives in exactly one
place, even though there's only one stage today.
"""

from __future__ import annotations

from .models import Finding, SearcherLLMClientProtocol
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES, search


def run_pipeline(
    query: str,
    *,
    llm_client: SearcherLLMClientProtocol,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_uses: int = DEFAULT_MAX_USES,
    progress_callback=None,
) -> list[Finding]:
    """Run a web search for `query` and return Findings.

    Args:
        query: Free-text question or topic to search for.
        llm_client: Anything implementing SearcherLLMClientProtocol.
        max_tokens: Token budget for the LLM's response.
        max_uses: Max number of web_search tool invocations the model
            may make per query.
        progress_callback: Optional callable for streaming progress
            (matches the convention used by other services' pipelines).

    Returns:
        list[Finding] - empty list if no sources were returned.

    Raises any exception from the underlying LLM client.
    """
    if progress_callback:
        progress_callback("search")
    return search(query, llm_client, max_tokens=max_tokens, max_uses=max_uses)
