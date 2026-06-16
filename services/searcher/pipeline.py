"""Stateless searcher pipeline.

Wires retrieval backends into one function. Searcher stays intentionally
blind: query in, Findings out.
"""

from __future__ import annotations

import logging

from .models import Finding, SearcherLLMClientProtocol
from .stages.pubmed import search_pubmed
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES, search

logger = logging.getLogger(__name__)


def run_pipeline(
    query: str,
    *,
    llm_client: SearcherLLMClientProtocol,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_uses: int = DEFAULT_MAX_USES,
    backends: tuple[str, ...] = ("web",),
    ncbi_api_key: str | None = None,
    progress_callback=None,
) -> list[Finding]:
    """Run retrieval backends for `query` and return deduped Findings.

    Args:
        query: Free-text question or topic to search for.
        llm_client: Anything implementing SearcherLLMClientProtocol.
        max_tokens: Token budget for the LLM's response.
        max_uses: Max number of web_search tool invocations the model
            may make per query.
        backends: Retrieval backends to union. Defaults to web-only for
            existing callers.
        ncbi_api_key: Optional NCBI API key for PubMed/PMC requests.
        progress_callback: Optional callable for streaming progress
            (matches the convention used by other services' pipelines).

    Returns:
        list[Finding] - empty list if no sources were returned.

    Raises any exception from the web LLM client. PubMed/PMC failures are
    handled inside that backend so web findings still flow.
    """
    if progress_callback:
        progress_callback("search")

    findings: list[Finding] = []
    for backend in backends:
        if backend == "web":
            findings.extend(
                search(query, llm_client, max_tokens=max_tokens, max_uses=max_uses)
            )
        elif backend == "pubmed":
            findings.extend(search_pubmed(query, api_key=ncbi_api_key))
        else:
            logger.warning("Unknown search backend %r; skipping", backend)

    seen: set[str] = set()
    out: list[Finding] = []
    for finding in findings:
        if finding.url in seen:
            continue
        seen.add(finding.url)
        out.append(finding)
    return out
