"""Running the planned searches through Searcher and gathering findings per variable.

Searcher owns every source's grammar, credentials and limits; this only plans requests
from the intents, runs them, and files what came back under the variable that asked.
A source that failed, or that this deployment has not configured, is reported rather than
silently missing, because a draft read without a source looks the same as one read with it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from services.searcher import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_USES,
    Finding,
    RetrievalIntent,
    SearchRuntime,
    merge_findings,
    plan_requests,
    run_requests,
    unconfigured_source_keys,
)


@dataclass(frozen=True)
class RetrievalReport:
    #: Findings per variable, merged by URL.
    found: dict[str, list[Finding]]
    #: Sources every request to which failed: their evidence is missing from the whole run.
    failed_sources: tuple[str, ...]
    #: Sources this deployment has not configured, so they were never asked.
    unconfigured_sources: tuple[str, ...]
    #: Per variable, the sources whose request for it failed - even where others succeeded.
    failed_for: dict[str, tuple[str, ...]]
    #: The provider's own message for each source that failed at least once, so a saved
    #: result can be diagnosed later; an exception type alone could not be.
    source_errors: dict[str, str]


def retrieve(
    intents: Sequence[RetrievalIntent],
    *,
    sources: Iterable[str],
    runtime: SearchRuntime,
    progress: Callable[[int, int], None] | None = None,
) -> RetrievalReport:
    sources = tuple(sources)
    unconfigured = set(unconfigured_source_keys(sources, runtime))
    usable = [key for key in sources if key not in unconfigured]
    requests = plan_requests(list(intents), sources=usable) if usable else []
    outcomes = run_requests(
        requests, runtime=runtime, max_tokens=DEFAULT_MAX_TOKENS, max_uses=DEFAULT_MAX_USES, progress=progress,
    ) if requests else []
    statuses: dict[str, set[str]] = {}
    errors: dict[str, str] = {}
    failed_for: dict[str, list[str]] = {}
    by_scope: dict[str, dict[str, Finding]] = {}
    for outcome in outcomes:
        source, scope = outcome.request.source, outcome.request.scope_ref
        statuses.setdefault(source, set()).add(outcome.status)
        if outcome.status == "failed":
            errors.setdefault(source, " ".join(str(outcome.error or "").split()) or "The source returned an error.")
            if source not in failed_for.setdefault(scope, []):
                failed_for[scope].append(source)
            continue
        if outcome.status != "complete":
            continue
        held = by_scope.setdefault(scope, {})
        for finding in outcome.findings:
            if finding.url in held:
                merge_findings(held[finding.url], finding)
            else:
                held[finding.url] = finding
    return RetrievalReport(
        found={scope: list(findings.values()) for scope, findings in by_scope.items()},
        failed_sources=tuple(key for key in sources if statuses.get(key) == {"failed"}),
        unconfigured_sources=tuple(key for key in sources if key in unconfigured),
        failed_for={scope: tuple(keys) for scope, keys in failed_for.items()},
        source_errors=errors,
    )
