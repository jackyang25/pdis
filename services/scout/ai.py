"""One structured model boundary for every Scout stage.

The request and its retry are shared with the other services. What is
Scout-specific is the ``AIContract`` indirection: it names the schema and the
payload key a stage expects to read back. Everything else - the trailing
per-item text, the tier, the effort, the cache key - passes through unchanged.

Every stage lays its request out the same way, so requests that share a prefix
share it in the same place: stable instructions in the system prompt, then the
document or bindings the stage's requests have in common, then their images, then
the one item this request is about as ``trailing_text``.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from shared.ai import Effort, ModelTask, Verbosity
from shared.ai import request_structured as send_structured
from shared.ai import request_validated as send_validated

from .ai_contracts import AIContract
from .models import LLMClientProtocol

_T = TypeVar("_T")


def _stage_payload(contract: AIContract, payload: dict[str, Any] | None) -> object | None:
    if payload is None or contract.payload_key is None:
        return payload
    return payload.get(contract.payload_key)


def request_structured(
    llm_client: LLMClientProtocol,
    contract: AIContract,
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int,
    images: list[dict[str, str]] | None = None,
    trailing_text: str = "",
    task: ModelTask = "reasoning",
    effort: Effort | None = None,
    verbosity: Verbosity | None = None,
    cache_key: str | None = None,
) -> object | None:
    """Request one schema-bound decision and expose its stage payload."""
    return _stage_payload(contract, send_structured(
        llm_client,
        system_prompt,
        user_message,
        schema_name=contract.name,
        schema=contract.schema,
        max_tokens=max_tokens,
        images=images,
        trailing_text=trailing_text,
        task=task,
        effort=effort,
        verbosity=verbosity,
        cache_key=cache_key,
    ))


def request_validated(
    llm_client: LLMClientProtocol,
    contract: AIContract,
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int,
    parse: Callable[[object | None], _T],
    failure: str,
    repair: Callable[[str], str] | None = None,
    images: list[dict[str, str]] | None = None,
    trailing_text: str = "",
    task: ModelTask = "reasoning",
    effort: Effort | None = None,
    verbosity: Verbosity | None = None,
    cache_key: str | None = None,
    attempts: int = 2,
) -> _T:
    """:func:`shared.ai.request_validated` over a contract's stage payload.

    ``repair=None`` uses the shared repair note, which names what failed validation
    so the retry can correct it rather than resend the same answer.
    """
    options: dict[str, Any] = {"repair": repair} if repair is not None else {}
    return send_validated(
        llm_client,
        system_prompt,
        user_message,
        schema_name=contract.name,
        schema=contract.schema,
        max_tokens=max_tokens,
        parse=lambda payload: parse(_stage_payload(contract, payload)),
        failure=failure,
        images=images,
        trailing_text=trailing_text,
        task=task,
        effort=effort,
        verbosity=verbosity,
        cache_key=cache_key,
        attempts=attempts,
        **options,
    )
