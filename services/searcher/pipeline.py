"""Stateless free-query facade over the source controller."""

from __future__ import annotations

from .controller import run_requests, validate_source_keys
from .models import (
    Finding,
    SearchRequest,
    SearchRuntime,
    merge_findings,
)
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES


def run_pipeline(
    query: str,
    *,
    runtime: SearchRuntime,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_uses: int = DEFAULT_MAX_USES,
    sources: tuple[str, ...] = ("web",),
    condition: str | None = None,
    intervention: str | None = None,
    raise_source_errors: bool = False,
    progress_callback=None,
) -> list[Finding]:
    """Run registered retrieval sources for `query` and return deduped Findings.

    Args:
        query: Free-text question or topic to search for.
        runtime: Injected capabilities available to registered source adapters.
        max_tokens: Token budget for the LLM's response.
        max_uses: Max number of web_search tool invocations the model
            may make per query.
        sources: Registered source adapter keys to union. Defaults to web.
        condition: Optional condition/disease for the ClinicalTrials.gov
            structured search. Ignored by other sources.
        intervention: Optional intervention term for the ClinicalTrials.gov
            structured search. Ignored by other sources.
        raise_source_errors: Re-raise any adapter failures. Defaults to the
            standalone Searcher's graceful partial-result behavior.
        progress_callback: Optional callable for streaming progress
            (matches the convention used by other services' pipelines).

    Returns:
        list[Finding] - empty list if no sources were returned.

    Adapter failures are isolated as outcomes. They raise only when
    `raise_source_errors` is true.
    """
    selected = validate_source_keys(sources)
    options = tuple(
        (key, value)
        for key, value in (("condition", condition), ("intervention", intervention))
        if value
    )
    requests = [
        SearchRequest(
            scope_ref="query",
            source=source,
            query=query,
            options=options,
        )
        for source in selected
    ]
    outcomes = run_requests(
        requests,
        runtime=runtime,
        max_tokens=max_tokens,
        max_uses=max_uses,
        progress=(
            lambda completed, total: progress_callback(
                "search", completed=completed, total=total
            )
        )
        if progress_callback
        else None,
    )
    failures = [outcome for outcome in outcomes if outcome.status == "failed"]
    if failures and raise_source_errors:
        failed = ", ".join(outcome.request.source for outcome in failures)
        raise RuntimeError(f"Retrieval source failure(s): {failed}")
    findings = [
        finding
        for outcome in outcomes
        if outcome.status == "complete"
        for finding in outcome.findings
    ]

    by_url: dict[str, Finding] = {}
    out: list[Finding] = []
    for finding in findings:
        if finding.url in by_url:
            merge_findings(by_url[finding.url], finding)
            continue
        by_url[finding.url] = finding
        out.append(finding)
    return out
