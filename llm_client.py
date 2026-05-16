"""Shared LLM provider abstraction for all PDIS tools.

One LLMClient interface, two concrete implementations (Anthropic, OpenAI).
Every tool's pipeline imports from here so prompting/error-handling stays
consistent across the suite.

Per-tool token budgets (`DEFAULT_MAX_OUTPUT_TOKENS`) live in each tool's
`pipeline.py` since they're defaults for that tool's `max_tokens` kwarg,
not properties of the LLM client itself.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = "claude-opus-4-7"
OPENAI_MODEL = "gpt-5.5"
DEFAULT_PROVIDER_MODELS = {
    "anthropic": ANTHROPIC_MODEL,
    "openai": OPENAI_MODEL,
}
PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class LLMClient(ABC):
    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> str:
        """Send a system+user prompt to the LLM and return the response text."""


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None):
        import anthropic  # type: ignore[reportMissingImports]

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or ANTHROPIC_MODEL

    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return _anthropic_message_text(message)


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None):
        from openai import OpenAI  # type: ignore[reportMissingImports]

        self.client = OpenAI(api_key=api_key)
        self.model = model or OPENAI_MODEL

    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return _openai_response_text(response)


def create_llm_client(provider: str, api_key: str, model: str | None = None) -> LLMClient:
    """Create an LLM client for a supported provider."""
    if not api_key:
        raise ValueError("api_key is required")

    normalized_provider = provider.lower()
    if normalized_provider == "anthropic":
        return AnthropicClient(api_key=api_key, model=model)
    if normalized_provider == "openai":
        return OpenAIClient(api_key=api_key, model=model)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def default_model_for_provider(provider: str) -> str:
    """Return the default model name for a supported LLM provider."""
    normalized_provider = provider.lower()
    try:
        return DEFAULT_PROVIDER_MODELS[normalized_provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported LLM provider: {provider}") from exc


def _anthropic_message_text(message: Any) -> str:
    parts = []
    for block in getattr(message, "content", []):
        text = _content_block_text(block)
        if text:
            parts.append(text)

    message_text = "\n".join(parts)
    if not message_text.strip():
        logger.warning(
            "Anthropic response had no text content. stop_reason=%s content_types=%s usage=%s",
            getattr(message, "stop_reason", None),
            _content_block_types(getattr(message, "content", [])),
            getattr(message, "usage", None),
        )
    return message_text


def _openai_response_text(response: Any) -> str:
    choices = getattr(response, "choices", [])
    if not choices:
        logger.warning("OpenAI response had no choices")
        return ""

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    if not content:
        logger.warning(
            "OpenAI response had no text content. finish_reason=%s usage=%s",
            getattr(choices[0], "finish_reason", None),
            getattr(response, "usage", None),
        )
    return content or ""


def _content_block_text(block: Any) -> str | None:
    if isinstance(block, dict):
        return block.get("text")
    return getattr(block, "text", None)


def _content_block_types(content_blocks: list[Any]) -> list[str]:
    content_types = []
    for block in content_blocks:
        if isinstance(block, dict):
            content_types.append(str(block.get("type", "unknown")))
        else:
            content_types.append(str(getattr(block, "type", type(block).__name__)))
    return content_types
