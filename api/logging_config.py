"""One logging configuration for the gateway, and the request ID threaded through it.

Without this the 31 `logging.getLogger` call sites across `services/` reach
Python's last-resort handler: uvicorn configures its own loggers and leaves the
root logger alone, so INFO is discarded and WARNING and above print bare, with
no timestamp, no logger name, and nothing tying a line to the request that
produced it. Every degraded-source warning the retrieval lanes emit was arriving
that way, which is to say arriving unusable.

JSON because the destination is an aggregator reading allocation stdout, and a
line that has to be regex-parsed to answer "which run was this" is a line nobody
queries twice.

The request ID is generated here rather than trusted from the caller: this
gateway is reached through an ingress, and an ID a browser can set is an ID a
browser can collide. An upstream `X-Request-ID` is recorded when present, under
its own key, so a proxy's correlation survives without becoming ours.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"

# A ContextVar rather than a thread local: the streaming routes hand work to
# worker threads and back, and a ContextVar is the one carrier that follows both
# an `async def` handler and the sync code it awaits into.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Attributes LogRecord always carries. Anything else on a record was put there
# by a caller passing `extra=`, and is worth emitting.
_STANDARD_RECORD_FIELDS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS:
                payload[key] = value

        # `default=str` so a caller passing a non-serializable object through
        # `extra=` degrades to its repr instead of losing the whole line.
        return json.dumps(payload, default=str)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign every request an ID, and return it on the response."""

    async def dispatch(self, request, call_next):
        upstream = request.headers.get(REQUEST_ID_HEADER)
        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        if upstream:
            response.headers["X-Upstream-Request-ID"] = upstream
        return response


def configure_logging() -> None:
    """Install the JSON handler on the root logger.

    Replaces existing root handlers rather than adding to them, so importing
    this twice, or importing it after something else called `basicConfig`, does
    not emit every line more than once.

    LOG_FORMAT=text keeps human-readable output for local development, where a
    JSON line per request is harder to read than the thing it replaced.
    """
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()

    if os.environ.get("LOG_FORMAT", "json").strip().lower() == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its own handlers and does not propagate. Clearing them
    # lets its access and error lines reach the same formatter as everything
    # else; otherwise half the output is JSON and half is not.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
