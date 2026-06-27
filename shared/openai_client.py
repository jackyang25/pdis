"""Shared OpenAI client.

One provider (OpenAI), one default model (gpt-5.5). Used by all
services for text generation and web search.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.5"


class OpenAIClient:
    """Thin OpenAI wrapper exposing text generation and web search."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from openai import OpenAI  # type: ignore[reportMissingImports]

        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return _response_text(response)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
    ) -> Any:
        """Chat-completions call with optional tool (function) calling.

        Returns the first choice's `message` object; callers read `.content`
        and `.tool_calls`. Powers the Ask assistant's hand-rolled agent loop.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        response = self.client.chat.completions.create(**kwargs)
        choices = getattr(response, "choices", [])
        if not choices:
            logger.warning("OpenAI chat response had no choices")
            return None
        return choices[0].message

    def search_web(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        max_uses: int = 5,
    ) -> Any:
        """Run an LLM-driven web search via OpenAI's Responses API.

        Uses the built-in `web_search` tool. Returns the raw Responses API
        response object; callers extract URLs and cited text from the
        output's annotations.

        `max_uses` is accepted for protocol compatibility. The current OpenAI
        SDK does not expose a per-tool max_uses setting for this call.
        """
        from openai import BadRequestError  # type: ignore[reportMissingImports]

        try:
            return self.client.responses.create(
                model=self.model,
                input=query,
                tools=[{"type": "web_search"}],
                max_output_tokens=max_tokens,
            )
        except BadRequestError:
            return self.client.responses.create(
                model=self.model,
                input=query,
                tools=[{"type": "web_search_preview"}],
                max_output_tokens=max_tokens,
            )


def _response_text(response: Any) -> str:
    choices = getattr(response, "choices", [])
    if not choices:
        logger.warning("OpenAI response had no choices")
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    if not content:
        logger.warning(
            "OpenAI response had no text. finish_reason=%s usage=%s",
            getattr(choices[0], "finish_reason", None),
            getattr(response, "usage", None),
        )
    return content or ""
