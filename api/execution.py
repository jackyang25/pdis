"""Process-wide admission control shared by every application transport."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from collections.abc import Callable, Iterator


# Sized against instance memory in the deployment jobspec, not just throughput.
# Shared by HTTP and MCP; a second worker would multiply this process-local cap.
# tests/test_streaming.py pins the single-worker image command.
MAX_CONCURRENT_RUNS = max(1, int(os.getenv("MAX_CONCURRENT_RUNS", "2")))
_run_slots = threading.Semaphore(MAX_CONCURRENT_RUNS)


class CapacityExceeded(RuntimeError):
    """No run slot is available to a caller that elected not to wait."""


@contextmanager
def run_slot(
    on_queued: Callable[[], None] | None = None,
    *,
    wait: bool = True,
) -> Iterator[None]:
    """Acquire one process-wide run slot and always return it on exit."""
    acquired = _run_slots.acquire(blocking=False)
    if not acquired:
        if not wait:
            raise CapacityExceeded("Run capacity is currently full.")
        if on_queued is not None:
            on_queued()
        _run_slots.acquire()
    try:
        yield
    finally:
        _run_slots.release()
