"""Provider-call mechanics shared by every adapter: pacing, per-run reuse, and notes.

Three things happen around every provider call, and none of them is an adapter's grammar:

* **Pacing** is per rate group, not per lane, and per provider call - retries included -
  not per adapter request. A quota belongs to a provider: `fda` and `fda_safety` both spend openFDA's. And
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

`provider_request` is the one way a direct lane calls its provider: those three, the shared
transport's retries and deadline, the deployment's contact in the User-Agent, and the lane's
key sent beside the question rather than as part of it - so a key is never in the memo and
is removed from any error message that echoes it.
"""

from __future__ import annotations

import contextvars
import json
import threading
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Iterator, Mapping

from .errors import RetrievalError
from .models import OutcomeWarning, SearchRuntime, SourceSpec
from .transport import (
    DEFAULT_DEADLINE_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    fetch,
    json_body,
    retry_pacing,
    user_agent,
)

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
        # A retry the transport makes inside `load` takes a slot of its own.
        with collecting_notes() as notes, retry_pacing(lambda: pace(rate_group, interval_seconds)):
            value = load()
        return value, notes

    value, notes = runtime.calls.get(call_key(rate_group, operation, arguments), paced)
    if notes.provider_query:
        note_provider_query(notes.provider_query)
    for warning in notes.warnings:
        note_warning(warning.code, warning.detail)
    return value


def provider_request(
    runtime: SearchRuntime,
    spec: SourceSpec,
    *,
    operation: str,
    url: str,
    query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    auth_query: Mapping[str, str] | None = None,
    auth_headers: Mapping[str, str] | None = None,
    interval_seconds: float | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    no_match_status: int | None = None,
    decode: Callable[[bytes], Any] | None = None,
) -> Any:
    """Make one provider call for a direct lane and return its decoded answer.

    `query` and `body` are the question: they form the memo key with `operation`, and a
    `body` is sent as a JSON POST. `auth_query` and `auth_headers` carry the lane's key and
    are sent but never memoized. Pacing is `spec`'s rate group at `interval_seconds`, which
    defaults to the spec's own; a lane whose provider allows more with a key passes the
    keyed interval. `no_match_status` is the status a provider answers "nothing matched"
    with (openFDA's 404): that answer is `None` rather than a failure. The body decodes as
    JSON unless `decode` says otherwise. The returned value may be shared with another
    request: read it, never alter it.
    """
    question = dict(query or {})
    secrets = tuple(
        value for value in (*(auth_query or {}).values(), *(auth_headers or {}).values()) if value
    )
    sent = {**question, **(auth_query or {})}
    address = f"{url}?{urllib.parse.urlencode(sent, doseq=True)}" if sent else url
    request_headers = {
        "User-Agent": user_agent(runtime.contact_email),
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if body is not None else {}),
        **(headers or {}),
        **(auth_headers or {}),
    }

    def load() -> Any:
        try:
            raw = fetch(
                address,
                provider=spec.label,
                data=None if body is None else json.dumps(body).encode("utf-8"),
                headers=request_headers,
                method=None if body is None else "POST",
                timeout=timeout,
                deadline_seconds=deadline_seconds,
                secrets=secrets,
            )
        except RetrievalError as exc:
            if no_match_status is not None and exc.status == no_match_status:
                return None
            raise
        return decode(raw) if decode else json_body(raw, spec.label)

    return provider_call(
        runtime,
        rate_group=spec.rate_group,
        interval_seconds=spec.request_interval_seconds if interval_seconds is None else interval_seconds,
        operation=operation,
        arguments={"url": url, "query": question, "body": dict(body or {})},
        load=load,
    )
