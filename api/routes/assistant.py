"""Ask route - read-only, grounded Q&A over context the client already has.

Stateless: the client sends a result or workspace bundle + conversation history each turn
(consistent with the one-shot tools). The agent loop runs server-side. The
original JSON endpoint remains available; the UI uses the plain-text stream.
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
    PriorityItemInput,
    PriorityRequest,
    answer_stream as assistant_answer_stream,
    read_priorities,
)
from services.chunker import parse_context_file

from api.deps import MissingCredentialError, get_openai_client
from api.schemas import (
    AskRequest,
    AssistantContextResponse,
    ContentBlockOut,
    PriorityDigestRequest,
    PriorityDigestResponse,
    PriorityNominationOut,
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
    for chunk in chunks:
        prefix = "" if chunk.kind == "text" else f"event: {chunk.kind}\n"
        yield f"{prefix}data: {json.dumps(chunk.text)}\n\n"


@router.post("/priority-digest", response_model=PriorityDigestResponse)
async def priority_digest(request: PriorityDigestRequest) -> PriorityDigestResponse:
    """Read one tool's selected priorities: what they amount to, and what they miss.

    Not part of any result. The digest describes a list the browser derives when a result
    is opened, so it is derived the same way and travels nowhere — no analysis version
    moves, and an exported result is unchanged.

    The route holds no tool table. Everything that differs between tools arrives in the
    request: the authority sentence, the ordering rule, the items as rendered.
    """
    try:
        llm_client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    read = PriorityRequest(
        authority=request.authority.strip(),
        order_note=request.order_note.strip(),
        items=tuple(
            PriorityItemInput(
                id=item.id,
                label=item.label,
                qualifier=item.qualifier,
                statement=item.statement,
                recommendation=item.recommendation,
            )
            for item in request.items
        ),
        analysis=request.analysis,
        block_ids=frozenset(request.block_ids),
        org=request.org,
        intervention_class=request.intervention_class,
        indication=request.indication,
    )
    try:
        result = await run_in_threadpool(read_priorities, read, llm_client=llm_client)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Everything, not just ValueError. A provider rejecting the request raises its own
        # SDK error, which slipped past a ValueError handler and became a 500 with the
        # reason only in the server log — so the panel showed a skeleton, then nothing,
        # and no surface said why. A digest is an addition to a panel that already works,
        # so this stays a 502 the client can degrade around, but the reason travels with it.
        logger.warning("Priority digest failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PriorityDigestResponse(
        digest=result.digest,
        nominations=[
            PriorityNominationOut(
                label=item.label,
                statement=item.statement,
                cited_block_ids=item.cited_block_ids,
            )
            for item in result.nominations
        ],
    )


@router.post("/ask/stream")
def ask_stream(request: AskRequest) -> StreamingResponse:
    """Stream a grounded answer as plain text for AI SDK UI consumers.

    The request contract intentionally matches /ask so saved results, source
    documents, and stateless conversation history keep the same semantics.
    """
    try:
        client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    document = (
        [block.model_dump() for block in request.document] if request.document else None
    )
    stream = assistant_answer_stream(
        client,
        request.result,
        request.result_type,
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
