"""Ask route - read-only, grounded Q&A over a result the client already has.

Stateless: the client sends the result object + conversation history each turn
(consistent with the one-shot tools). The agent loop runs server-side. The
original JSON endpoint remains available; the UI uses the plain-text stream.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services.assistant import answer as assistant_answer
from services.assistant import answer_stream as assistant_answer_stream

from api.deps import get_openai_client
from api.schemas import AskRequest, AskResponse

router = APIRouter()


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
