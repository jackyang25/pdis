"""Provider-call mechanics shared by every adapter: pacing, per-run reuse, and notes.

Three things happen around every provider call, and none of them is an adapter's grammar:

* **Pacing** is per rate group, not per lane, and per provider call, not per adapter
  request. A quota belongs to a provider: `fda` and `fda_safety` both spend openFDA's. And
  one adapter request can be several calls - WHO reads a page per result, PubMed fetches
  records after searching - so spacing only the start of `search()` let those calls burst.

* **Reuse** is per run. Scout builds one intent per attribute and every attribute carries
  the run's indication, so a registry filtered by condition is asked the same question once
  per attribute. The first call reaches the provider and the rest wait for its answer.
  Every request still yields its own outcome and findings, so each contributing intent stays
  in lineage; only the duplicate network call is removed.

* **Notes** let a call report what the provider said beside its records - the query it
  actually ran, a warning, a part of the answer it could not return - without changing the
  adapter contract. The controller collects them onto the request's outcome.
"""

from __future__ import annotations

import contextvars
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Hashable, Iterator, Mapping

from .models import OutcomeWarning

_PACE_LOCK = threading.Lock()
_NEXT_START: dict[str, float] = {}


def pace(group: str, interval_seconds: float) -> None:
    """Reserve a process-wide start slot for one call to a rate-limited provider.

    Process-wide because a quota is the provider's, shared by every run in the process.
    """
    if interval_seconds <= 0:
        return
    with _PACE_LOCK:
        now = time.monotonic()
        start_at = max(now, _NEXT_START.get(group, now))
        _NEXT_START[group] = start_at + interval_seconds
    wait_seconds = start_at - now
    if wait_seconds > 0:
        time.sleep(wait_seconds)


def call_key(source: str, operation: str, arguments: Mapping[str, Any]) -> Hashable:
    """The identity of one native call: who is asked, what, with which exact arguments."""
    return (
        source,
        operation,
        json.dumps(dict(arguments), sort_keys=True, default=str),
    )


@dataclass
class RequestNotes:
    provider_query: str = ""
    warnings: list[OutcomeWarning] = field(default_factory=list)


_NOTES: contextvars.ContextVar[RequestNotes | None] = contextvars.ContextVar(
    "searcher_request_notes", default=None
)


@contextmanager
def collecting_notes() -> Iterator[RequestNotes]:
    notes = RequestNotes()
    token = _NOTES.set(notes)
    try:
        yield notes
    finally:
        _NOTES.reset(token)


def note_warning(code: str, detail: str) -> None:
    """Record a provider warning on the current request's outcome, if one is collecting."""
    warning = OutcomeWarning(code=code, detail=" ".join(detail.split()))
    notes = _NOTES.get()
    if notes is not None and warning not in notes.warnings:
        notes.warnings.append(warning)


def note_provider_query(text: str) -> None:
    """Record the query the provider reports it actually ran for the current request."""
    notes = _NOTES.get()
    if notes is not None:
        notes.provider_query = " ".join(text.split())


def provider_call(
    runtime: Any,
    *,
    rate_group: str,
    interval_seconds: float,
    operation: str,
    arguments: Mapping[str, Any],
    load: Any,
) -> Any:
    """Make one provider call at most once per run, paced against its provider's quota.

    Pacing happens only on a miss, so a reused answer spends nothing. `load` takes no
    arguments and performs exactly the call `operation` and `arguments` describe. What the
    provider reported while answering is kept with the answer and recorded on every
    request that reuses it, so a reused answer carries the same warnings as the first.
    """

    def paced() -> tuple[Any, RequestNotes]:
        pace(rate_group, interval_seconds)
        with collecting_notes() as notes:
            value = load()
        return value, notes

    value, notes = runtime.calls.get(call_key(rate_group, operation, arguments), paced)
    if notes.provider_query:
        note_provider_query(notes.provider_query)
    for warning in notes.warnings:
        note_warning(warning.code, warning.detail)
    return value
