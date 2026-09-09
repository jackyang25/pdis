"""Translate application work, progress and failures into MCP protocol results."""

import asyncio
from collections.abc import Callable
import itertools
import logging
import threading

import anyio
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from api.execution import CapacityExceeded, run_slot
from api.operations.errors import OperationError

logger = logging.getLogger(__name__)


def _result(data: dict, *, error: bool = False) -> CallToolResult:
    import json

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        structured_content=data,
        is_error=error,
    )


async def call_operation(
    work: Callable[..., BaseModel],
    ctx: Context,
    *,
    uses_capacity: bool,
) -> CallToolResult:
    """Keep synchronous pipelines off the event loop and hold capacity until done.

    Cancellation does not release the slot while a worker is still using memory
    or provider calls. Progress is advisory; a disconnected client must not turn
    an otherwise valid service result into a provider failure.
    """
    loop = asyncio.get_running_loop()
    sequence = itertools.count(1)
    progress_lock = threading.Lock()

    def progress(stage: str, completed=None, total=None):
        message = (
            stage
            if completed is None or total is None
            else f"{stage}: {completed}/{total}"
        )
        with progress_lock:
            future = asyncio.run_coroutine_threadsafe(
                ctx.report_progress(next(sequence), message=message),
                loop,
            )
        try:
            future.result(timeout=5)
        except Exception:
            future.cancel()

    def run():
        if uses_capacity:
            with run_slot(wait=False):
                return work(progress)
        return work(progress)

    try:
        value = await anyio.to_thread.run_sync(run, abandon_on_cancel=False)
        return _result(value.model_dump(mode="json"))
    except CapacityExceeded:
        code, message = (
            "server_busy",
            "PDIS is at capacity. Retry after another run finishes.",
        )
    except OperationError as exc:
        code = exc.code
        message = (
            "Searcher is not configured on this server."
            if code == "missing_configuration"
            else exc.message
        )
    except Exception:
        logger.exception("MCP application operation failed")
        code, message = (
            "operation_failed",
            "The operation could not be completed. Contact your PDIS administrator.",
        )
    return _result({"error": {"code": code, "message": message}}, error=True)
