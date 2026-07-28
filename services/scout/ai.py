"""One structured model boundary for every Scout stage."""

from __future__ import annotations

from .ai_contracts import AIContract
from .models import LLMClientProtocol


def request_structured(
    llm_client: LLMClientProtocol,
    contract: AIContract,
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int,
    images: list[dict[str, str]] | None = None,
    task: str = "reasoning",
) -> object | None:
    """Request one schema-bound decision and expose its stage payload."""
    payload = llm_client.call_structured(
        system_prompt,
        user_message,
        max_tokens,
        schema_name=contract.name,
        schema=contract.schema,
        images=images,
        task=task,
    )
    if not isinstance(payload, dict):
        return None
    if contract.payload_key is None:
        return payload
    return payload.get(contract.payload_key)
