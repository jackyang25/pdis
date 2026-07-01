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
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as exc:  # noqa: BLE001 - degrade on content refusal, re-raise the rest
            if _is_content_refusal(exc):
                logger.warning("Prompt refused by content policy; returning empty text.")
                return ""
            raise
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
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - degrade on content refusal, re-raise the rest
            if _is_content_refusal(exc):
                logger.warning("Chat prompt refused by content policy; returning None.")
                return None
            raise
        choices = getattr(response, "choices", [])
        if not choices:
            logger.warning("OpenAI chat response had no choices")
            return None
        return choices[0].message

    def describe_image(
        self,
        image_bytes: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
        max_tokens: int = 12000,
        reasoning_effort: str = "low",
    ) -> str:
        """Describe a raster image in text (vision). Powers the chunker's
        image-describer stage, which turns an embedded figure into its textual
        record. The caller supplies the lens via `prompt`; this method is
        domain-agnostic. Returns "" on an empty response.

        Transcription is a low-reasoning task, so `reasoning_effort` defaults to
        "low" with a generous token ceiling: dense figures otherwise spend the
        whole budget reasoning and emit no text (a length-capped empty reply).
        """
        import base64

        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001 - degrade on content refusal, re-raise the rest
            if _is_content_refusal(exc):
                logger.warning("Image-description prompt refused by content policy; returning empty.")
                return ""
            raise
        return _response_text(response)

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

        def _create(tool: str):
            return self.client.responses.create(
                model=self.model,
                input=query,
                tools=[{"type": tool}],
                max_output_tokens=max_tokens,
            )

        try:
            return _create("web_search")
        except Exception as exc:  # noqa: BLE001
            if _is_content_refusal(exc):
                logger.warning("Web search prompt refused by content policy; skipping this query.")
                return None
            # A plain BadRequestError is usually the older tool name - retry once.
            if isinstance(exc, BadRequestError):
                try:
                    return _create("web_search_preview")
                except Exception as exc2:  # noqa: BLE001
                    if _is_content_refusal(exc2):
                        logger.warning("Web search prompt refused by content policy; skipping this query.")
                        return None
                    raise
            raise


def _is_content_refusal(exc: Exception) -> bool:
    """True if this is an OpenAI content-policy refusal (dual-use / biosecurity
    'invalid_prompt'). These cannot succeed on retry, so callers skip the prompt
    and degrade gracefully rather than failing the whole run. Any other error
    (network, auth, rate limit) returns False and is re-raised by the caller.
    """
    if getattr(exc, "code", None) == "invalid_prompt":
        return True
    text = str(exc)
    return "invalid_prompt" in text or "limited access to this content" in text


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
