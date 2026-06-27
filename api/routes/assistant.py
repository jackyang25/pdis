"""Ask route - read-only, grounded Q&A over a result the client already has.

Stateless: the client sends the result object + conversation history each turn
(consistent with the one-shot tools). The agent loop runs server-side and
returns one answer.
"""

from __future__ import annotations

from fastapi import APIRouter

from services.assistant import answer as assistant_answer

from api.deps import get_openai_client
from api.schemas import AskRequest, AskResponse

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    client = get_openai_client()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    text = assistant_answer(client, request.result, request.result_type, messages)
    return AskResponse(answer=text)
