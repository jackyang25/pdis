"""Searcher's one HTTP transport.

Every provider call Searcher makes - the direct lanes and the injected connectors - goes
through `fetch`, so retry policy, identification and address selection are decided once.
Before this each adapter carried its own copy: two retried only a 429, with a backoff
shorter than any provider's window, ignored `Retry-After`, and never retried a 502 or a
reset connection; the rest did not retry at all.

What is retried is what a provider says is transient: 429, 502, 503, 504, a reset or
dropped connection, and a timeout. `Retry-After` is honoured when the provider states it,
otherwise the wait is a jittered exponential backoff, and every attempt shares one total
deadline so a retry can never make a request slower than the caller allowed. A refused
connection is not retried: nothing is listening, and waiting will not change that.

Address selection is scoped here too. Some containers resolve a provider to IPv4 and IPv6
addresses but can only route IPv4, and urllib does not fall back, so a lookup yielding IPv6
first fails with "Network is unreachable". The connections this module opens try IPv4
addresses first and fall back to the platform's own resolution only when a host has none.
That used to be done by replacing `socket.getaddrinfo` for the whole process on import,
which changed name resolution for every library in the API, not only for Searcher.
"""

from __future__ import annotations

import http.client
import json
import random
import socket
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .errors import RetrievalError

#: Identifies the product, not a person. A contact is appended only when the deployment
#: configured one (`SearchRuntime.contact_email`); inventing an address would give a
#: provider someone to write to who does not exist.
PRODUCT_USER_AGENT = "PDIS-Searcher/1.0"
RETRY_STATUSES = frozenset({429, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 35.0
#: Total time one call may take across every attempt and wait.
DEFAULT_DEADLINE_SECONDS = 90.0
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 8.0
MAX_MESSAGE_CHARS = 300
_MESSAGE_KEYS = ("error", "message", "detail", "errors", "description")


def user_agent(contact: str = "") -> str:
    contact = contact.strip()
    return f"{PRODUCT_USER_AGENT} (mailto:{contact})" if contact else PRODUCT_USER_AGENT


def fetch(
    url: str,
    *,
    provider: str,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    method: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
    secrets: Sequence[str] = (),
) -> bytes:
    """Return one response body, retrying transient failures within one deadline.

    Raises `RetrievalError` carrying the provider's own message. `secrets` are removed
    from that message, because an error body can echo the credential it was sent.
    """
    deadline = time.monotonic() + deadline_seconds
    request_headers = {"User-Agent": PRODUCT_USER_AGENT, **(headers or {})}
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        remaining = max(deadline - time.monotonic(), 1.0)
        retry_after: float | None = None
        try:
            with _open(request, timeout=min(timeout, remaining)) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            cause: BaseException = exc
            error = RetrievalError(
                provider,
                "rate_limited" if exc.code == 429 else "http_error",
                _redact(_error_message(exc), secrets) or str(exc.reason or ""),
                status=exc.code,
            )
            retryable = exc.code in RETRY_STATUSES
            retry_after = _retry_after(exc.headers)
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            cause = exc
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            timed_out = isinstance(reason, TimeoutError)
            error = RetrievalError(
                provider,
                "timeout" if timed_out else "unavailable",
                _redact(str(reason) or type(reason).__name__, secrets),
            )
            retryable = timed_out or isinstance(
                reason,
                (
                    ConnectionResetError,
                    ConnectionAbortedError,
                    http.client.RemoteDisconnected,
                    http.client.IncompleteRead,
                ),
            )
        if not retryable or attempt == max_attempts:
            raise error from cause
        delay = retry_after if retry_after is not None else backoff_delay(attempt)
        if time.monotonic() + delay >= deadline:
            raise error from cause
        pause(delay)
    raise AssertionError("unreachable")


def fetch_json(url: str, *, provider: str, **kwargs: Any) -> Any:
    body = fetch(url, provider=provider, **kwargs)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetrievalError(provider, "invalid_response", "returned invalid JSON") from exc


def backoff_delay(attempt: int) -> float:
    ceiling = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
    return ceiling * random.uniform(0.5, 1.0)


def _retry_after(headers: Any) -> float | None:
    value = (headers.get("Retry-After") if headers is not None else None) or ""
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _error_message(exc: urllib.error.HTTPError) -> str:
    """The provider's own explanation, from a JSON or plain-text error body.

    Read from structured keys rather than echoed whole: an HTML error page is markup, not
    a message, and a reader of a saved result needs the sentence, not the page.
    """
    try:
        body = exc.read(16_384) or b""
    except Exception:  # noqa: BLE001 - the status alone is still a usable failure
        return ""
    text = body.decode("utf-8", "replace").strip()
    if not text:
        return ""
    content_type = (exc.headers.get("Content-Type", "") if exc.headers else "").lower()
    try:
        message = _message_from(json.loads(text))
    except json.JSONDecodeError:
        message = "" if "html" in content_type or text.startswith("<") else text
    return " ".join(message.split())[:MAX_MESSAGE_CHARS]


def _message_from(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in _MESSAGE_KEYS:
            if key in value and (message := _message_from(value[key])):
                return message
        return ""
    if isinstance(value, list):
        return "; ".join(message for item in value if (message := _message_from(item)))
    return ""


def _redact(message: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    return message


def _ipv4_first_connection(
    address: tuple[str, int],
    timeout: Any = socket._GLOBAL_DEFAULT_TIMEOUT,  # type: ignore[attr-defined]
    source_address: Any = None,
    **kwargs: Any,
) -> socket.socket:
    host, port = address
    try:
        candidates = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        candidates = []
    if not candidates:
        # No IPv4 address at all: the platform's own resolution, IPv6 included.
        return socket.create_connection(address, timeout, source_address)
    last_error: OSError | None = None
    for *_, sockaddr in candidates:
        try:
            return socket.create_connection(
                (sockaddr[0], port), timeout, source_address
            )
        except OSError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


class _HTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _ipv4_first_connection


class _HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _ipv4_first_connection


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):  # type: ignore[no-untyped-def]
        return self.do_open(_HTTPConnection, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):  # type: ignore[no-untyped-def]
        return self.do_open(_HTTPSConnection, req, context=self._context)


_OPENER = urllib.request.build_opener(_HTTPHandler, _HTTPSHandler)


def _open(request: urllib.request.Request, *, timeout: float):
    return _OPENER.open(request, timeout=timeout)


def pause(seconds: float) -> None:
    time.sleep(seconds)
