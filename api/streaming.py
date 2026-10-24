"""NDJSON streaming helper.

Each route runs the pipeline in a worker thread while emitting stage
events to a queue. The HTTP response yields the queue contents as
newline-delimited JSON: one event per line, terminated by a `complete`
event carrying the result (or an `error` event with the message).

HTTP `/run` endpoints funnel through here. Admission control lives in
api.execution so other transports share the same process-wide capacity.
"""

from __future__ import annotations

import contextvars
import json
import logging
import queue
import threading
import weakref
from typing import Any, Callable, Generator, Iterator

from fastapi import HTTPException

from api.execution import CapacityExceeded, RunCancelled, admit_run, run_slot
from api.error_recovery import recovery_guidance


END = object()
logger = logging.getLogger(__name__)

# Emit a keepalive this often when no real event has occurred, so the HTTP
# stream never goes idle long enough for a proxy/host to cut it during long
# silent stages (e.g. scout's multi-minute search). The frontend ignores
# unknown event types, so `ping` is a safe no-op there.
HEARTBEAT_SECONDS = 15

# Announced only when a run actually waits, so an uncontended run emits exactly
# the events it always did. The frontend resolves stage names against a tool's
# own step list and falls back to the first step, so an unrecognized name here
# would claim that parsing had begun; web/lib/api.ts mirrors this exact string.
QUEUED_STAGE = "queued"


def run_with_progress(work: Callable[..., Any]) -> Iterator[str]:
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

    Admission is decided here, in the handler, so a full queue is a 503 rather
    than an error event on a 200. The run starts at once. When the stream is
    closed before the run ends - the client went away - the run is cancelled:
    a queued run never takes a slot, and a running one raises `RunCancelled`
    from its next progress() call.

    Raises:
        HTTPException: 503 when running and waiting runs are both at their cap.
    """
    try:
        release_admission = admit_run()
    except CapacityExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    events: "queue.Queue[Any]" = queue.Queue()
    cancelled = threading.Event()
    stage_lock = threading.Lock()
    current_stage = {"name": "startup"}

    def progress(
        stage: str, completed: int | None = None, total: int | None = None
    ) -> None:
        if cancelled.is_set():
            raise RunCancelled("The client closed the stream.")
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
        # attributed to the pipeline stage that failed. The slot and the admission
        # are released on every exit path, because a run that ended without
        # releasing would retire that capacity until the next restart.
        try:
            with run_slot(
                on_queued=lambda: events.put({"event": "stage", "name": QUEUED_STAGE}),
                cancelled=cancelled,
            ):
                if cancelled.is_set():
                    raise RunCancelled("The client closed the stream.")
                result = work(progress)
                events.put({"event": "complete", "result": result})
        except RunCancelled:
            with stage_lock:
                stopped_stage = current_stage["name"]
            logger.info("Run abandoned by its client during stage %s", stopped_stage)
        except Exception as exc:  # noqa: BLE001
            with stage_lock:
                failed_stage = current_stage["name"]
            logger.exception("Streaming work failed during stage %s", failed_stage)
            detail = f"{failed_stage}: {exc}"
            guidance = recovery_guidance(exc)
            if guidance:
                detail = f"{detail} {guidance}"
            events.put({"event": "error", "detail": detail})
        finally:
            release_admission()
            events.put(END)

    def stream() -> Generator[str, None, None]:
        try:
            while True:
                try:
                    item = events.get(timeout=HEARTBEAT_SECONDS)
                except queue.Empty:
                    yield json.dumps({"event": "ping"}) + "\n"
                    continue
                if item is END:
                    break
                yield json.dumps(item) + "\n"
        finally:
            # Also reached by GeneratorExit when the server closes an abandoned
            # stream. After a finished run it changes nothing.
            cancelled.set()

    # A bare Thread starts with an empty context, so the request ID the logging
    # filter reads from a ContextVar would vanish from everything the run logs.
    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(runner,), daemon=True).start()
    events_stream = stream()
    # A stream the server never starts is never closed, so its `finally` cannot
    # run; collecting it cancels the run instead.
    weakref.finalize(events_stream, cancelled.set)
    return events_stream


PING = object()


def with_heartbeat(items: Iterator[Any]) -> Iterator[Any]:
    """Yield `items`, and `PING` whenever `HEARTBEAT_SECONDS` pass with nothing to send.

    The source runs in a worker thread so a silent step (model reasoning, a fetch) cannot
    starve the connection. An exception in the source is re-raised here. When the consumer
    stops early, the worker stops at the source's next item and closes it, so a provider
    stream is not left running.
    """
    events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
    stop = threading.Event()

    def pump() -> None:
        try:
            for item in items:
                if stop.is_set():
                    break
                events.put(("item", item))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", exc))
        except BaseException as exc:  # noqa: BLE001
            # Not only Exception: a source ended by anything else is still a truncated
            # answer, and ending it as "end" would let the caller report completion.
            failure = RuntimeError(f"stream source stopped: {type(exc).__name__}")
            failure.__cause__ = exc
            events.put(("error", failure))
        finally:
            try:
                close = getattr(items, "close", None)
                if close is not None:
                    close()
            finally:
                # Nested so a raising close() can never leave the consumer on pings.
                events.put(("end", None))

    # A bare Thread starts with an empty context, so the request ID the logging
    # filter reads from a ContextVar would vanish from everything the source logs.
    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(pump,), daemon=True).start()
    try:
        while True:
            try:
                kind, value = events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                yield PING
                continue
            if kind == "end":
                return
            if kind == "error":
                raise value
            yield value
    finally:
        stop.set()
