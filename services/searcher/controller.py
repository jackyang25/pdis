"""Source-agnostic retrieval planner and concurrent execution controller."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from .models import (
    RetrievalIntent,
    RetrievalPath,
    SearchOutcome,
    SearchRequest,
    SearchRuntime,
    SourceSpec,
)
from .sources import SOURCE_REGISTRY

logger = logging.getLogger(__name__)


def source_specs() -> list[SourceSpec]:
    """Return registered source metadata in stable display/execution order."""
    return [adapter.spec for adapter in SOURCE_REGISTRY.values()]


def source_keys() -> tuple[str, ...]:
    return tuple(SOURCE_REGISTRY)


def validate_source_keys(keys: Iterable[str]) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(key.strip() for key in keys if key.strip()))
    unknown = [key for key in selected if key not in SOURCE_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown retrieval source(s): {', '.join(unknown)}")
    return selected


def plan_requests(
    intents: list[RetrievalIntent],
    *,
    sources: Iterable[str],
) -> list[SearchRequest]:
    """Delegate native query planning to each enabled source adapter."""
    selected = validate_source_keys(sources)
    requests = [
        request
        for intent in intents
        for source in selected
        for request in SOURCE_REGISTRY[source].plan(intent)
    ]
    # An adapter may intentionally collapse several semantic tracks into one
    # native request. Never execute an identical immutable request twice.
    return list(dict.fromkeys(requests))


def run_requests(
    requests: list[SearchRequest],
    *,
    runtime: SearchRuntime,
    max_tokens: int,
    max_uses: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[SearchOutcome]:
    """Execute requests by source with adapter-owned concurrency limits.

    Results preserve request order. A failing adapter request becomes a failed
    outcome and cannot abort or relabel successful requests from another source.
    """
    if not requests:
        return []
    validate_source_keys(request.source for request in requests)
    total = len(requests)
    if progress:
        progress(0, total)
    lock = threading.Lock()
    completed = 0

    def report() -> None:
        nonlocal completed
        if not progress:
            return
        with lock:
            completed += 1
            progress(completed, total)

    def execute(request: SearchRequest) -> SearchOutcome:
        adapter = SOURCE_REGISTRY[request.source]
        try:
            findings = adapter.search(
                request,
                runtime,
                max_tokens=max_tokens,
                max_uses=max_uses,
            )
            for finding in findings:
                # The adapter key is authoritative. Stage parsers do not own
                # catalog metadata, and future adapters need no UI changes.
                finding.source = request.source
                finding.source_lanes = [
                    lane for lane in finding.source_lanes if lane != "unknown"
                ]
                finding.retrieval_paths = [
                    path for path in finding.retrieval_paths if path.lane != "unknown"
                ]
                if request.source not in finding.source_lanes:
                    finding.source_lanes.append(request.source)
                path = RetrievalPath(query=finding.query, lane=request.source)
                if path not in finding.retrieval_paths:
                    finding.retrieval_paths.append(path)
                finding.source_labels[request.source] = adapter.spec.label
                if finding.title_source_lane in {"", "unknown"}:
                    finding.title_source_lane = request.source
                if finding.excerpt and finding.excerpt_source_lane in {"", "unknown"}:
                    finding.excerpt_source_lane = request.source
                if finding.published_at and finding.published_source_lane in {"", "unknown"}:
                    finding.published_source_lane = request.source
            return SearchOutcome(request=request, findings=findings)
        except Exception as exc:  # noqa: BLE001 - sources degrade independently
            logger.warning(
                "%s retrieval failed for %r (%s)",
                request.source,
                request.query,
                exc,
            )
            return SearchOutcome(
                request=request,
                status="failed",
                error=type(exc).__name__,
            )
        finally:
            report()

    by_source = {
        source: [request for request in requests if request.source == source]
        for source in dict.fromkeys(request.source for request in requests)
    }

    def execute_source(source: str) -> list[SearchOutcome]:
        source_requests = by_source[source]
        workers = max(
            1,
            min(SOURCE_REGISTRY[source].spec.worker_limit, len(source_requests)),
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(execute, source_requests))

    with ThreadPoolExecutor(max_workers=len(by_source)) as executor:
        grouped = dict(zip(by_source, executor.map(execute_source, by_source)))

    source_results = {
        source: iter(outcomes) for source, outcomes in grouped.items()
    }
    return [next(source_results[request.source]) for request in requests]
