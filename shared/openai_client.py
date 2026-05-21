"""Shared OpenAI client.

One provider (OpenAI), one default model (gpt-5.5). Used by
chunker/benchmarker/reviewer. Searcher uses sibling provider client
`shared/anthropic_client.py`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.5"


class OpenAIClient:
    """Thin OpenAI wrapper exposing one method: `call(system, user, max_tokens)`."""

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
