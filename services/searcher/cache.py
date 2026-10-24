"""A bounded, expiring, single-flight memo for provider fetches that recur within a run.

Several requests in one run often ask a provider the same thing - Scout plans one request
per field, and fields usually share a registry filter - so the first should reach the
provider and the rest should wait for its answer. That is all this is for.

Single-flight per key rather than one lock for the whole cache: concurrent requests for
different keys proceed in parallel, so the source's `worker_limit` and request interval,
not this cache, decide how fast a provider is called. Entries expire, because a process
lives for days and a registry record changes, and the cache is bounded, because a process
that runs many searches must not keep every answer it was ever given. A failure is
returned to every waiter and not stored, so the next request retries.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from typing import Callable, Generic, Hashable, TypeVar

_V = TypeVar("_V")


class SingleFlightCache(Generic[_V]):
    def __init__(self, *, max_entries: int, ttl_seconds: float) -> None:
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("cache bounds must be positive")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._entries: OrderedDict[Hashable, tuple[float, _V]] = OrderedDict()
        self._in_flight: dict[Hashable, Future[_V]] = {}

    def get(self, key: Hashable, load: Callable[[], _V]) -> _V:
        """Return the live value for `key`, loading it once however many callers ask."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > time.monotonic():
                self._entries.move_to_end(key)
                return entry[1]
            self._entries.pop(key, None)
            pending = self._in_flight.get(key)
            owner = pending is None
            if owner:
                pending = self._in_flight[key] = Future()
        if not owner:
            return pending.result()
        try:
            value = load()
        except BaseException as exc:
            with self._lock:
                del self._in_flight[key]
            pending.set_exception(exc)
            raise
        with self._lock:
            del self._in_flight[key]
            self._entries[key] = (time.monotonic() + self._ttl_seconds, value)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        pending.set_result(value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


#: What a run may reuse. Long enough for one run's retrieval, short enough that a runtime
#: kept longer than a run does not serve a registry record that has since changed.
RUN_CALL_TTL_SECONDS = 15 * 60
RUN_CALL_MAX_ENTRIES = 4096


class ProviderCalls:
    """A run's single-flight memo of provider answers.

    Values are shared between the requests that asked the same question, so a caller reads
    them and never alters them. A failure is not stored: the next request retries.
    """

    def __init__(self) -> None:
        self._cache: SingleFlightCache[object] = SingleFlightCache(
            max_entries=RUN_CALL_MAX_ENTRIES, ttl_seconds=RUN_CALL_TTL_SECONDS
        )

    def get(self, key: Hashable, load: Callable[[], _V]) -> _V:
        return self._cache.get(key, load)  # type: ignore[return-value]
