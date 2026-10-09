"""Ask route - read-only, grounded Q&A over context the client already has.

Stateless: the client sends a result or workspace bundle + conversation history each turn
(consistent with the one-shot tools). The agent loop runs server-side. The UI
receives text, activity, offers, completion, and failure as separate SSE events.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Iterator
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from services.assistant import (
    Chunk,
    PriorityFinding,
    PriorityRequest,
    PriorityRequestTooLarge,
    answer_stream as assistant_answer_stream,
    limits,
    read_priorities,
)
from services.chunker import parse_context_file

from api import streaming
from api.deps import MissingCredentialError, get_openai_client
from api.schemas import (
    AskRequest,
    AssistantContextResponse,
    ContentBlockOut,
    PriorityPointOut,
    PriorityReadingRequest,
    PriorityReadingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()
MAX_CONTEXT_FILE_BYTES = 25 * 1024 * 1024


@router.post("/context", response_model=AssistantContextResponse)
async def add_context(file: UploadFile = File(...)) -> AssistantContextResponse:
    """Parse one transient conversation attachment without retaining server state."""
    filename = Path(file.filename or "attachment").name
    contents = await file.read(MAX_CONTEXT_FILE_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Attachment is empty")
    if len(contents) > MAX_CONTEXT_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Attachment exceeds the 25 MB limit")

    suffix = Path(filename).suffix.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "file"
    digest = hashlib.sha256(contents).hexdigest()[:10]
    doc_id = f"attachment-{stem}-{digest}"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        blocks = await run_in_threadpool(
            parse_context_file,
            temp_path,
            doc_id,
            source_media_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    return AssistantContextResponse(
        filename=filename,
        doc_id=doc_id,
        blocks=[ContentBlockOut.model_validate(asdict(block)) for block in blocks],
    )


def sse(chunks: Iterator[Chunk]) -> Iterator[str]:
    """Frame the answer as server-sent events, one event kind per chunk kind.

    Activity travels on its own event rather than inside the text with a marker
    to separate it: the format already distinguishes kinds, so doing it twice
    would be two mechanisms for one job.

    Each payload is JSON-encoded so a newline inside it cannot end the event.
    SSE is line-delimited and model prose contains newlines constantly.
    """
    try:
        for chunk in streaming.with_heartbeat(chunks):
            if chunk is streaming.PING:
                yield ": ping\n\n"
                continue
            prefix = "" if chunk.kind == "text" else f"event: {chunk.kind}\n"
            # An offer is data for the interface, framed as its JSON object; text and
            # activity are strings.
            payload = chunk.data if chunk.kind == "offer" else chunk.text
            yield f"{prefix}data: {json.dumps(payload)}\n\n"
    except Exception:
        # HTTP headers have already gone out. Send a failure event, not answer
        # text, and keep provider diagnostics (which may contain input) in logs.
        logger.exception("Assistant stream failed")
        error = {
            "code": "assistant_stream_failed",
            "message": "The assistant could not finish its response. Please try again.",
        }
        yield f"event: error\ndata: {json.dumps(error)}\n\n"
        return
    yield "event: done\ndata: {}\n\n"


@router.post("/priorities", response_model=PriorityReadingResponse)
async def priorities(request: PriorityReadingRequest) -> PriorityReadingResponse:
    """Read one result's findings: what it amounts to, and where to look first.

    Not part of any result. It is read when a result is opened and travels nowhere — no
    analysis version moves, and an exported result is unchanged.

    The route holds no tool table. Everything that differs between tools arrives in the
    request: the authority sentence, the focus, and the findings as the page names them.
    """
    try:
        llm_client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not request.findings:
        raise HTTPException(status_code=422, detail="a result with no findings has nothing to read")

    read = PriorityRequest(
        authority=request.authority.strip(),
        focus=request.focus.strip(),
        findings=tuple(
            PriorityFinding(
                id=item.id,
                subject=item.subject,
                group=item.group,
                verdicts=tuple(item.verdicts),
                statements=tuple(item.statements),
                notes=tuple(item.notes),
                quote=item.quote,
            )
            for item in request.findings
        ),
        org=request.org,
        intervention_class=request.intervention_class,
        indication=request.indication,
    )
    try:
        result = await run_in_threadpool(read_priorities, read, llm_client=llm_client)
    except PriorityRequestTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        # Everything, not just ValueError. A provider rejecting the request raises its own
        # SDK error, which slipped past a ValueError handler and became a 500 with the
        # reason only in the server log. The card is complete without a reading, so this
        # stays a 502 the client can degrade around, and the reason travels with it.
        logger.warning("Priority reading failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PriorityReadingResponse(
        summary=result.summary,
        points=[
            PriorityPointOut(
                title=point.title,
                statement=point.statement,
                finding_ids=point.finding_ids,
            )
            for point in result.points
        ],
    )


def _request_size_problem(request: AskRequest) -> str | None:
    """Why a request is too large to answer, or None. Checked before the stream opens."""
    blocks = request.document or []
    images = [block.image for block in blocks if block.image is not None]
    checks = (
        (len(request.messages), limits.MAX_REQUEST_MESSAGES, "too many messages"),
        (len(blocks), limits.MAX_REQUEST_BLOCKS, "too many document blocks"),
        (len(images), limits.MAX_REQUEST_IMAGES, "too many images"),
        (sum(len(image.data_base64) for image in images), limits.MAX_REQUEST_IMAGE_CHARS, "too much image data"),
    )
    for size, cap, what in checks:
        if size > cap:
            return f"This conversation carries {what} ({size} > {cap}). Start a new chat or remove results."
    return None


@router.post("/ask/stream")
def ask_stream(request: AskRequest) -> StreamingResponse:
    """Stream a grounded answer and explicit success/failure as SSE events.

    Each request carries the current workspace and the conversation; nothing is kept
    between requests.
    """
    try:
        client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    problem = _request_size_problem(request)
    if problem:
        raise HTTPException(status_code=413, detail=problem)
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    document = (
        [block.model_dump() for block in request.document] if request.document else None
    )
    stream = assistant_answer_stream(
        client,
        request.result,
        messages,
        document=document,
    )
    return StreamingResponse(
        sse(stream),
        # Server-sent events, not plain text: Cloudflare fronts this service and
        # buffers a text/plain response to completion, so a 30-second answer
        # arrived all at once in production while streaming perfectly in local
        # development. `text/event-stream` is the one media type a proxy must
        # pass through unbuffered. `X-Accel-Buffering` is an nginx directive
        # Cloudflare ignores, and it was being stripped from the response.
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Content-Type-Options": "nosniff",
            "Connection": "keep-alive",
        },
    )
