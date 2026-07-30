"""One schema-bound model request for every service.

Each service declares its own ``LLMClientProtocol`` — that stays deliberate, so a
service's public contract does not depend on this module. What was duplicated is
the *call*: build the request, and treat anything that is not a payload object as
no answer. That is here, once.

Scout layers its ``AIContract`` unwrapping on top of this; chunker and inspector
use it directly.
"""

from __future__ import annotations

from typing import Any, Protocol

from shared.openai_client import ModelTask


class StructuredLLMClient(Protocol):
    """The client shape this helper needs.

    Structurally identical to each service's ``LLMClientProtocol``; declared here
    only so this function can type its own parameter without importing a service.
    """

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: ModelTask = "reasoning",
    ) -> dict[str, Any] | None:
        ...


def request_structured(
    llm_client: StructuredLLMClient,
    system_prompt: str,
    user_message: str,
    *,
    schema_name: str,
    schema: dict[str, Any],
    max_tokens: int,
    images: list[dict[str, str]] | None = None,
    task: ModelTask = "reasoning",
) -> dict[str, Any] | None:
    """Send one schema-bound request and return its payload object.

    Returns ``None`` when the provider returned no usable object, so callers
    handle absence explicitly rather than guarding a shape at every call site.
    """
    payload = llm_client.call_structured(
        system_prompt,
        user_message,
        max_tokens,
        schema_name=schema_name,
        schema=schema,
        images=images,
        task=task,
    )
    return payload if isinstance(payload, dict) else None
