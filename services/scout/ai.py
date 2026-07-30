"""One structured model boundary for every Scout stage.

The request itself is shared with the other services. What is Scout-specific is
the ``AIContract`` indirection: it names the schema and the payload key a stage
expects to read back.
"""

from __future__ import annotations

from shared.ai import request_structured as send_structured
from shared.openai_client import ModelTask

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
    task: ModelTask = "reasoning",
) -> object | None:
    """Request one schema-bound decision and expose its stage payload."""
    payload = send_structured(
        llm_client,
        system_prompt,
        user_message,
        schema_name=contract.name,
        schema=contract.schema,
        max_tokens=max_tokens,
        images=images,
        task=task,
    )
    if payload is None:
        return None
    if contract.payload_key is None:
        return payload
    return payload.get(contract.payload_key)
