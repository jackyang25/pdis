"""One structured model boundary for every Scout stage."""

from __future__ import annotations

import json
import logging
from typing import Any

from .ai_contracts import AIContract
from .models import LLMClientProtocol

logger = logging.getLogger(__name__)


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
    """Request one schema-bound decision and expose its stage payload.

    Production clients implement ``call_structured``. The text fallback exists
    only for small injected test doubles and parses JSON in this one location;
    no Scout stage owns provider formatting or fence recovery anymore.
    """
    method = getattr(llm_client, "call_structured", None)
    if callable(method):
        try:
            payload = method(
                system_prompt,
                user_message,
                max_tokens,
                schema_name=contract.name,
                schema=contract.schema,
                images=images,
                task=task,
            )
        except TypeError as exc:
            # Test doubles predating task routing remain usable; production's
            # OpenAIClient always accepts the closed task class.
            if "task" not in str(exc):
                raise
            payload = method(
                system_prompt,
                user_message,
                max_tokens,
                schema_name=contract.name,
                schema=contract.schema,
                images=images,
            )
    else:
        try:
            raw = llm_client.call(
                system_prompt,
                user_message,
                max_tokens,
                images=images,
                task=task,
            )
        except TypeError as exc:
            if "task" not in str(exc):
                raise
            raw = llm_client.call(
                system_prompt,
                user_message,
                max_tokens,
                images=images,
            )
        payload = _legacy_test_payload(raw, contract.payload_key)
    if not isinstance(payload, dict):
        return None
    if contract.payload_key is None:
        return payload
    return payload.get(contract.payload_key)


def _legacy_test_payload(raw: str, payload_key: str | None) -> dict[str, Any] | None:
    """Decode fixtures from pre-Structured-Outputs test clients."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and payload_key:
        return {payload_key: parsed}
    logger.debug("Legacy Scout fixture did not match the expected root shape")
    return None
