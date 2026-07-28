"""Ask route - read-only, grounded Q&A over context the client already has.

Stateless: the client sends a result or workspace bundle + conversation history each turn
(consistent with the one-shot tools). The agent loop runs server-side. The
original JSON endpoint remains available; the UI uses the plain-text stream.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import re
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from services.assistant import answer as assistant_answer
from services.assistant import answer_stream as assistant_answer_stream
from services.chunker import parse_context_file

from api.deps import get_openai_client
from api.schemas import AssistantContextResponse, AskRequest, AskResponse, ContentBlockOut

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


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    client = get_openai_client()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    document = (
        [block.model_dump() for block in request.document] if request.document else None
    )
    text = assistant_answer(
        client,
        request.result,
        request.result_type,
        messages,
        document=document,
    )
    return AskResponse(answer=text)


@router.post("/ask/stream")
def ask_stream(request: AskRequest) -> StreamingResponse:
    """Stream a grounded answer as plain text for AI SDK UI consumers.

    The request contract intentionally matches /ask so saved results, source
    documents, and stateless conversation history keep the same semantics.
    """
    client = get_openai_client()
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
        stream,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Content-Type-Options": "nosniff",
            "X-Accel-Buffering": "no",
        },
    )
