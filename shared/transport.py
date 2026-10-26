"""How long one provider call may take, and which of its failures are worth retrying.

Both SDKs retry connection errors, 429s and 5xx, which is right: those are the
service refusing or dropping a request, and the next attempt usually succeeds. They
retry a read timeout the same way, which is not. A schema-bound call returns nothing
until its answer is complete, so a read timeout is a call that ran for its whole
window without finishing; repeating it holds a worker for the same window again, and
with two retries one stalled call held a run for three windows - fifteen minutes at
the five-minute ceiling.

So a stall is reported once and not repeated, and the window is sized to the call. A
read, write or pool timeout becomes an error the SDK does not retry (each client supplies its own
SDK's type), connection and status failures keep the SDK's retries, and a structured
call's read window follows its token budget instead of one ceiling for every call.
"""

from __future__ import annotations

from typing import Callable, Iterator

import httpx

from shared.ai import ModelTask

#: Connection establishment is cheap and its failures transient, so it keeps a short
#: limit and the SDK's retries.
CONNECT_TIMEOUT_SECONDS = 10.0

#: Sending a request and waiting for a pooled connection. Their own limit, because the
#: read window below is sized to an answer's budget - up to twelve minutes - and was the
#: limit on writing too. On a dead connection the write stalled instead, the SDK retried
#: it as a connection error, and one live call hung through three windows, 41 minutes.
#: Two minutes covers the largest request a budget allows (30 MB of images).
SEND_TIMEOUT_SECONDS = 120.0

#: Retries of connection errors, 429s and 5xx. Never of a stall. Four, because the SDK's
#: backoff doubles from half a second: two retries spanned about a second, so a network
#: blip of a few seconds failed a stage that a run of half an hour depended on. Four span
#: about eight.
MAX_RETRIES = 4

#: The window for calls that are not budgeted - streamed chat turns, where bytes keep
#: arriving and the limit is between chunks, and web searches.
DEFAULT_READ_SECONDS = 300.0

#: A budgeted call's window: a fixed allowance for queueing and the prompt, plus the
#: time its whole budget takes at a floor under its tier's generation rate measured
#: through the gateway, clamped. Measured on a 3.6k-token structured answer at low effort:
#: about 93 tokens a second on the fast tier and 32 on the reasoning tier. Each floor sits
#: below its tier's rate, so a call that is merely slow is never cut off; one past its
#: window has stalled. A 12k-token reasoning budget gets nine minutes, once - where a
#: fixed five-minute window cut such a call off and the SDK then ran it twice more.
#: One floor for both tiers, at the reasoning tier's rate, gave a fast call that answers
#: in under a minute twelve minutes to stall in: a stuck Scout insight batch held its run
#: that long before failing.
READ_ALLOWANCE_SECONDS = 60.0
MIN_TOKENS_PER_SECOND: dict[ModelTask, float] = {"fast": 60.0, "reasoning": 25.0}
MIN_READ_SECONDS = 90.0
MAX_READ_SECONDS = 720.0


def structured_timeout(max_tokens: int, task: ModelTask) -> httpx.Timeout:
    """The window for one schema-bound call with this output budget on this tier."""
    read = READ_ALLOWANCE_SECONDS + max_tokens / MIN_TOKENS_PER_SECOND[task]
    read = min(max(read, MIN_READ_SECONDS), MAX_READ_SECONDS)
    return _timeout(read)


def default_timeout() -> httpx.Timeout:
    return _timeout(DEFAULT_READ_SECONDS)


def _timeout(read: float) -> httpx.Timeout:
    return httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS, read=read, write=SEND_TIMEOUT_SECONDS, pool=SEND_TIMEOUT_SECONDS,
    )


#: Every way a call can run out its window. Connection failures are not here: they are the
#: service dropping a request, which the SDK's retries exist for.
_STALLS = (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)


class StallTransport(httpx.BaseTransport):
    """An HTTP transport that reports a read timeout as ``stalled(request)``.

    Everything else passes through untouched, so connection errors and status codes
    still reach the SDK's retry policy. The read can time out while the headers are
    awaited or while the body is read, so both are covered.
    """

    def __init__(
        self,
        stalled: Callable[[httpx.Request], Exception],
        inner: httpx.BaseTransport | None = None,
    ) -> None:
        self._stalled = stalled
        self._inner = inner or httpx.HTTPTransport(
            limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            response = self._inner.handle_request(request)
        except _STALLS as exc:
            raise self._stalled(request) from exc
        response.stream = _StallStream(response.stream, request, self._stalled)  # type: ignore[arg-type]
        return response

    def close(self) -> None:
        self._inner.close()


class _StallStream(httpx.SyncByteStream):
    def __init__(self, inner, request: httpx.Request, stalled) -> None:
        self._inner, self._request, self._stalled = inner, request, stalled

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._inner
        except _STALLS as exc:
            raise self._stalled(self._request) from exc

    def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if close is not None:
            close()


def http_client(stalled: Callable[[httpx.Request], Exception]) -> httpx.Client:
    """The HTTP client a provider SDK is given: the stall rule, the default window."""
    return httpx.Client(
        transport=StallTransport(stalled), timeout=default_timeout(), follow_redirects=True,
    )
