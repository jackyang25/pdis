"""NDJSON streaming helper.

Each route runs the pipeline in a worker thread while emitting stage
events to a queue. The HTTP response yields the queue contents as
newline-delimited JSON: one event per line, terminated by a `complete`
event carrying the result (or an `error` event with the message).

Every `/run` endpoint funnels through here, so this is also the one place
that decides how much work a single instance accepts at once.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import Any, Callable, Generator


END = object()
logger = logging.getLogger(__name__)

# Emit a keepalive this often when no real event has occurred, so the HTTP
# stream never goes idle long enough for a proxy/host to cut it during long
# silent stages (e.g. scout's multi-minute search). The frontend ignores
# unknown event types, so `ping` is a safe no-op there.
HEARTBEAT_SECONDS = 15

# How many pipeline runs one instance serves at once. A single run peaks near
# half a gigabyte -- the parsed document, its in-flight model requests and
# responses, and a LibreOffice process -- so a third simultaneous upload
# exceeds a 2 GB instance, and the resulting OOM kill takes every tool down
# rather than only the one that was overloaded. The ceiling is a fact about the
# deployed instance rather than about this code, so the deployment manifest
# declares it beside the memory limit it was sized against - see the `api` group
# in jobspec.nomad, where the two are set together and commented as one decision.
#
# This counter is process-local, which equals instance-local only because the
# image runs one uvicorn worker. A `--workers` flag would silently multiply the
# cap, so tests/test_streaming.py pins the single-worker command.
MAX_CONCURRENT_RUNS = max(1, int(os.getenv("MAX_CONCURRENT_RUNS", "2")))
_run_slots = threading.Semaphore(MAX_CONCURRENT_RUNS)

# Announced only when a run actually waits, so an uncontended run emits exactly
# the events it always did. The frontend resolves stage names against a tool's
# own step list and falls back to the first step, so an unrecognized name here
# would claim that parsing had begun; web/lib/api.ts mirrors this exact string.
QUEUED_STAGE = "queued"


def run_with_progress(work: Callable[..., Any]) -> Generator[str, None, None]:
    """Run `work(progress_callback)` in a background thread, yielding NDJSON.

    `work` is a callable that takes `progress_callback(stage, completed=None,
    total=None)` and returns a JSON-serializable result. `completed`/`total` are
    optional and let a stage report live per-item progress. Events emitted:
        {"event": "stage", "name": "<stage>"}
        {"event": "stage", "name": "<stage>", "completed": 12, "total": 54}
        {"event": "complete", "result": {...}}
        {"event": "error", "detail": "<msg>"}

    progress() is thread-safe: it is called from pipeline worker threads, and
    queue.Queue.put is safe for concurrent producers.
    """
    events: "queue.Queue[Any]" = queue.Queue()
    stage_lock = threading.Lock()
    current_stage = {"name": "startup"}

    def progress(stage: str, completed: int | None = None, total: int | None = None) -> None:
        with stage_lock:
            current_stage["name"] = stage
        event: dict[str, Any] = {"event": "stage", "name": stage}
        if completed is not None and total is not None:
            event["completed"] = completed
            event["total"] = total
        events.put(event)

    def runner() -> None:
        # Waiting for capacity is not a stage of the work, so the queued event is
        # published directly instead of through progress(): a later failure stays
        # attributed to the pipeline stage that failed. The slot is released on
        # every exit path, because a run that ended without releasing would
        # retire that capacity until the next restart.
        if not _run_slots.acquire(blocking=False):
            events.put({"event": "stage", "name": QUEUED_STAGE})
            _run_slots.acquire()
        try:
            result = work(progress)
            events.put({"event": "complete", "result": result})
        except Exception as exc:  # noqa: BLE001
            with stage_lock:
                failed_stage = current_stage["name"]
            logger.exception("Streaming work failed during stage %s", failed_stage)
            events.put(
                {
                    "event": "error",
                    "detail": f"{failed_stage}: {exc}",
                }
            )
        finally:
            _run_slots.release()
            events.put(END)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

    while True:
        try:
            item = events.get(timeout=HEARTBEAT_SECONDS)
        except queue.Empty:
            yield json.dumps({"event": "ping"}) + "\n"
            continue
        if item is END:
            break
        yield json.dumps(item) + "\n"
