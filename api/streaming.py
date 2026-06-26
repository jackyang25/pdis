"""NDJSON streaming helper.

Each route runs the pipeline in a worker thread while emitting stage
events to a queue. The HTTP response yields the queue contents as
newline-delimited JSON: one event per line, terminated by a `complete`
event carrying the result (or an `error` event with the message).
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any, Callable, Generator


END = object()

# Emit a keepalive this often when no real event has occurred, so the HTTP
# stream never goes idle long enough for a proxy/host to cut it during long
# silent stages (e.g. scout's multi-minute search). The frontend ignores
# unknown event types, so `ping` is a safe no-op there.
HEARTBEAT_SECONDS = 15


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

    def progress(stage: str, completed: int | None = None, total: int | None = None) -> None:
        event: dict[str, Any] = {"event": "stage", "name": stage}
        if completed is not None and total is not None:
            event["completed"] = completed
            event["total"] = total
        events.put(event)

    def runner() -> None:
        try:
            result = work(progress)
            events.put({"event": "complete", "result": result})
        except Exception as exc:  # noqa: BLE001
            events.put({"event": "error", "detail": str(exc)})
        finally:
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
