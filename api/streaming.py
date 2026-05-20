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


def run_with_progress(work: Callable[[Callable[[str], None]], Any]) -> Generator[str, None, None]:
    """Run `work(progress_callback)` in a background thread, yielding NDJSON.

    `work` is a callable that takes a `progress_callback(stage_name)` and
    returns a JSON-serializable result. Events emitted:
        {"event": "stage", "name": "<stage>"}
        {"event": "complete", "result": {...}}
        {"event": "error", "detail": "<msg>"}
    """
    events: "queue.Queue[Any]" = queue.Queue()

    def progress(stage: str) -> None:
        events.put({"event": "stage", "name": stage})

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
        item = events.get()
        if item is END:
            break
        yield json.dumps(item) + "\n"
