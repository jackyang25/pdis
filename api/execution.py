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

# Runs allowed to wait for a slot. A waiting run already holds its uploaded bytes,
# so an unbounded queue is the same memory ceiling the slot cap exists to hold,
# reached more slowly. Beyond it a run is refused before its stream opens.
MAX_WAITING_RUNS = 8
_admissions = threading.Semaphore(MAX_CONCURRENT_RUNS + MAX_WAITING_RUNS)

# Short requests outside a run that still parse a document or call a model: an
# Ask attachment and a priority reading. Held apart from run slots so a reading
# never queues behind an hour-long Scout run, and bounded so a burst of them
# cannot take the memory the run cap reserves. They fail fast rather than wait.
MAX_CONCURRENT_AUXILIARY = 4
_auxiliary_slots = threading.Semaphore(MAX_CONCURRENT_AUXILIARY)

# How often a waiting run checks whether its caller has gone. A wait that cannot
# notice an abandoned caller starts work nobody will read once a slot frees.
QUEUE_POLL_SECONDS = 0.5


class CapacityExceeded(RuntimeError):
    """No run slot is available to a caller that elected not to wait."""


class RunCancelled(Exception):
    """The caller abandoned the run, so the work stops at its next checkpoint."""


def admit_run() -> Callable[[], None]:
    """Reserve one place among running and waiting runs, or refuse.

    Returns the release, which is idempotent so every exit path may call it.
    """
    if not _admissions.acquire(blocking=False):
        raise CapacityExceeded("PDIS is at capacity. Retry after another run finishes.")
    lock = threading.Lock()
    released = False

    def release() -> None:
        nonlocal released
        with lock:
            if released:
                return
            released = True
        _admissions.release()

    return release


@contextmanager
def run_slot(
    on_queued: Callable[[], None] | None = None,
    *,
    wait: bool = True,
    cancelled: threading.Event | None = None,
) -> Iterator[None]:
    """Acquire one process-wide run slot and always return it on exit.

    A waiting caller whose `cancelled` event is set leaves the queue with
    `RunCancelled` instead of taking the slot.
    """
    acquired = _run_slots.acquire(blocking=False)
    if not acquired:
        if not wait:
            raise CapacityExceeded("Run capacity is currently full.")
        if on_queued is not None:
            on_queued()
        while not _run_slots.acquire(timeout=QUEUE_POLL_SECONDS):
            if cancelled is not None and cancelled.is_set():
                raise RunCancelled("The run was abandoned while waiting for capacity.")
    try:
        yield
    finally:
        _run_slots.release()


@contextmanager
def auxiliary_slot() -> Iterator[None]:
    """Hold one auxiliary slot, refusing with `CapacityExceeded` when none is free."""
    if not _auxiliary_slots.acquire(blocking=False):
        raise CapacityExceeded("PDIS is busy. Retry in a moment.")
    try:
        yield
    finally:
        _auxiliary_slots.release()
