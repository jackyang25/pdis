"""Provider-neutral LLM adapter for the evidence layer.

Mirrors chunker/llm_client.py. Kept independent (rather than importing from
chunker) so evidence can evolve its prompting/clients without coupling to
the chunker package.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = "claude-opus-4-7"
OPENAI_MODEL = "gpt-5.5"
DEFAULT_MAX_OUTPUT_TOKENS = 16000
DEFAULT_PROVIDER_MODELS = {
    "anthropic": ANTHROPIC_MODEL,
    "openai": OPENAI_MODEL,
}


class LLMClient(ABC):
    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> str:
        ...


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str | None = None):
        import anthropic  # type: ignore[reportMissingImports]

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or ANTHROPIC_MODEL

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> str:
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

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> str:
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
    if not api_key:
        raise ValueError("api_key is required")

    normalized_provider = provider.lower()
    if normalized_provider == "anthropic":
        return AnthropicClient(api_key=api_key, model=model)
    if normalized_provider == "openai":
        return OpenAIClient(api_key=api_key, model=model)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def default_model_for_provider(provider: str) -> str:
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
    return "\n".join(parts)


def _openai_response_text(response: Any) -> str:
    choices = getattr(response, "choices", [])
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return content or ""


def _content_block_text(block: Any) -> str | None:
    if isinstance(block, dict):
        return block.get("text")
    return getattr(block, "text", None)
