"""Source-agnostic retrieval planner and concurrent execution controller."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace
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

_RATE_RESERVATION_LOCK = threading.Lock()
_NEXT_SOURCE_START: dict[str, float] = {}


def source_specs() -> list[SourceSpec]:
    """Return registered source metadata in stable display/execution order."""
    return [adapter.spec for adapter in SOURCE_REGISTRY.values()]


def source_keys() -> tuple[str, ...]:
    return tuple(SOURCE_REGISTRY)


def integration_operations(integration_key: str) -> tuple[str, ...]:
    """Return the stable allowlist declared by adapters using an integration."""
    return tuple(
        dict.fromkeys(
            operation
            for adapter in SOURCE_REGISTRY.values()
            if adapter.spec.integration_key == integration_key
            for operation in adapter.spec.operations
        )
    )


def validate_source_keys(keys: Iterable[str]) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(key.strip() for key in keys if key.strip()))
    unknown = [key for key in selected if key not in SOURCE_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown retrieval source(s): {', '.join(unknown)}")
    return selected


def unconfigured_source_keys(
    keys: Iterable[str],
    runtime: SearchRuntime,
) -> tuple[str, ...]:
    """Return enabled adapters whose required injected integration is absent."""
    selected = validate_source_keys(keys)
    return tuple(
        key
        for key in selected
        if (integration := SOURCE_REGISTRY[key].spec.integration_key)
        and integration not in runtime.integrations
    )


def plan_requests(
    intents: list[RetrievalIntent],
    *,
    sources: Iterable[str],
) -> list[SearchRequest]:
    """Delegate native query planning to each enabled source adapter."""
    selected = validate_source_keys(sources)
    requests: list[SearchRequest] = []
    for intent in intents:
        for source in selected:
            adapter = SOURCE_REGISTRY[source]
            reason = _inapplicability_reason(intent, adapter.spec)
            if reason:
                requests.append(_skipped_request(intent, adapter.spec, reason))
                continue
            planned = adapter.plan(intent)
            planned = [_attach_target_refs(intent, request) for request in planned]
            _validate_plan(intent, source, planned)
            requests.extend(planned)
    # An adapter may intentionally collapse several semantic tracks into one
    # native request. Never execute an identical immutable request twice.
    return list(dict.fromkeys(requests))


def _inapplicability_reason(
    intent: RetrievalIntent,
    spec: SourceSpec,
) -> str:
    """Return a deterministic skip reason, or empty when the lane applies."""
    if not intent.evidence_domain:
        return ""  # free-query callers explicitly selected their source
    if spec.evidence_domains and intent.evidence_domain not in spec.evidence_domains:
        return (
            f"evidence domain {intent.evidence_domain!r} is outside "
            f"{spec.key}'s supported domains"
        )
    if spec.required_entity_types and not any(
        entity.entity_type in spec.required_entity_types for entity in intent.entities
    ):
        return (
            f"no document-stated entity of type "
            f"{', '.join(spec.required_entity_types)}"
        )
    return ""


def _skipped_request(
    intent: RetrievalIntent,
    spec: SourceSpec,
    reason: str,
) -> SearchRequest:
    queries = list(dict.fromkeys(intent.queries))
    return SearchRequest(
        scope_ref=intent.scope_ref,
        source=spec.key,
        query="",
        tracks=tuple(
            dict.fromkeys(track for query in queries for track in query.tracks)
        ),
        document_refs=tuple(
            dict.fromkeys(ref for query in queries for ref in query.document_refs)
        ),
        target_refs=tuple(
            dict.fromkeys(ref for query in queries for ref in query.target_refs)
        ),
        intent_ids=tuple(query.intent_id for query in queries),
        input_queries=tuple(query.text for query in queries),
        applicability="not_applicable",
        applicability_reason=reason,
    )


def _validate_plan(
    intent: RetrievalIntent,
    source: str,
    requests: list[SearchRequest],
) -> None:
    """Require an adapter to account for every neutral input intent exactly.

    Compaction is source-native and may be many-to-one, but positional
    truncation is never valid. The aligned IDs/texts make the coverage claim
    mechanically checkable rather than trusting adapter comments.
    """
    expected = {query.intent_id: query.text for query in intent.queries}
    target_refs_by_intent = {
        query.intent_id: query.target_refs for query in intent.queries
    }
    covered: set[str] = set()
    for request in requests:
        if request.source != source or request.scope_ref != intent.scope_ref:
            raise ValueError(
                f"{source} planner emitted a request outside its source/scope"
            )
        if not request.query.strip():
            raise ValueError(f"{source} planner emitted an empty native query")
        if len(request.intent_ids) != len(request.input_queries):
            raise ValueError(
                f"{source} planner emitted unaligned intent IDs and input queries"
            )
        for intent_id, input_query in zip(
            request.intent_ids,
            request.input_queries,
        ):
            if expected.get(intent_id) != input_query:
                raise ValueError(
                    f"{source} planner claimed unknown or altered intent {intent_id}"
                )
            covered.add(intent_id)
        expected_target_refs = tuple(
            dict.fromkeys(
                target_ref
                for intent_id in request.intent_ids
                for target_ref in target_refs_by_intent[intent_id]
            )
        )
        if request.target_refs != expected_target_refs:
            raise ValueError(
                f"{source} planner emitted inconsistent quantitative target lineage"
            )
    missing = set(expected) - covered
    if missing:
        raise ValueError(
            f"{source} planner omitted {len(missing)} query intent(s) for "
            f"{intent.scope_ref}"
        )


def _attach_target_refs(
    intent: RetrievalIntent,
    request: SearchRequest,
) -> SearchRequest:
    """Add neutral target lineage centrally so adapters remain grammar-only."""
    refs_by_intent = {
        query.intent_id: query.target_refs for query in intent.queries
    }
    target_refs = tuple(
        dict.fromkeys(
            target_ref
            for intent_id in request.intent_ids
            for target_ref in refs_by_intent.get(intent_id, ())
        )
    )
    return replace(request, target_refs=target_refs)


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
    completed_count = 0

    def report() -> None:
        nonlocal completed_count
        if not progress:
            return
        with lock:
            completed_count += 1
            progress(completed_count, total)

    def execute(request: SearchRequest) -> SearchOutcome:
        adapter = SOURCE_REGISTRY[request.source]
        try:
            if request.applicability == "not_applicable":
                return SearchOutcome(request=request, status="skipped")
            _wait_for_source_start(
                request.source,
                adapter.spec.request_interval_seconds,
            )
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
                path = RetrievalPath(
                    query=finding.query,
                    lane=request.source,
                    connector=request.connector,
                    operation=request.operation,
                )
                finding.retrieval_paths = [
                    existing
                    for existing in finding.retrieval_paths
                    if not (
                        existing.query == path.query
                        and existing.lane == path.lane
                        and not existing.connector
                        and not existing.operation
                        and (path.connector or path.operation)
                    )
                ]
                if path not in finding.retrieval_paths:
                    finding.retrieval_paths.append(path)
                finding.source_labels[request.source] = adapter.spec.label
                if adapter.spec.attribution:
                    finding.source_attributions[request.source] = (
                        adapter.spec.attribution
                    )
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

    global_limit = max(1, min(runtime.global_worker_limit, total))
    source_order = list(dict.fromkeys(request.source for request in requests))
    pending = {
        source: deque(
            (index, request)
            for index, request in enumerate(requests)
            if request.source == source
        )
        for source in source_order
    }
    source_limits = {
        source: max(1, SOURCE_REGISTRY[source].spec.worker_limit)
        for source in source_order
    }
    active = {source: 0 for source in source_order}
    results: list[SearchOutcome | None] = [None] * total
    cursor = 0

    # Submit only runnable work. Threads never block on a source semaphore, so
    # a slow, low-rate lane cannot occupy workers reserved for faster lanes.
    with ThreadPoolExecutor(max_workers=global_limit) as executor:
        in_flight: dict[Future[SearchOutcome], tuple[int, str]] = {}

        def fill() -> None:
            nonlocal cursor
            while len(in_flight) < global_limit:
                selected_source = ""
                for offset in range(len(source_order)):
                    source = source_order[(cursor + offset) % len(source_order)]
                    if pending[source] and active[source] < source_limits[source]:
                        selected_source = source
                        cursor = (cursor + offset + 1) % len(source_order)
                        break
                if not selected_source:
                    return
                index, request = pending[selected_source].popleft()
                active[selected_source] += 1
                in_flight[executor.submit(execute, request)] = (
                    index,
                    selected_source,
                )

        fill()
        while in_flight:
            done_futures, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done_futures:
                index, source = in_flight.pop(future)
                active[source] -= 1
                results[index] = future.result()
            fill()

    if any(result is None for result in results):
        raise RuntimeError("retrieval scheduler failed to complete every request")
    return [result for result in results if result is not None]


def _wait_for_source_start(source: str, interval_seconds: float) -> None:
    """Reserve a process-wide start slot for one rate-constrained adapter."""
    if interval_seconds <= 0:
        return
    with _RATE_RESERVATION_LOCK:
        now = time.monotonic()
        start_at = max(now, _NEXT_SOURCE_START.get(source, now))
        _NEXT_SOURCE_START[source] = start_at + interval_seconds
    wait_seconds = start_at - now
    if wait_seconds > 0:
        time.sleep(wait_seconds)
