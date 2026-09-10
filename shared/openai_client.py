"""Shared OpenAI client and server-owned model policy.

OpenAI remains the primary provider for document interpretation, retrieval,
evidence reasoning, Ask, and the other product tools. Services select only a
stable task class; model names stay centralized here and in environment
configuration. Browser requests can never choose a model. Within Scout's two
quantitative checkpoints, Anthropic performs schema-bound mapping and OpenAI
independently reviews the resulting immutable proposals.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterator, Literal

from shared.chat import ChatDelta, ChatTurn, ToolCall

logger = logging.getLogger(__name__)

ModelTask = Literal["fast", "reasoning"]

DEFAULT_FAST_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_MODEL = "gpt-6-astra"

#: Kong's OpenAI-compatible unified endpoint. Overridable for local/dev use
#: against OpenAI directly, validated like any other base URL.
DEFAULT_BASE_URL = "https://ai-kong-gateway.bmgf.io/ai/v2"


class OpenAIClient:
    """Thin OpenAI wrapper exposing text generation and web search."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        fast_model: str | None = None,
        reasoning_model: str | None = None,
    ):
        from openai import OpenAI  # type: ignore[reportMissingImports]

        # KONG_KEY, when present, routes through Kong's unified endpoint with
        # Kong's own credential. Otherwise fall back to calling OpenAI directly
        # with OPENAI_API_KEY, as before Kong existed.
        kong_key = os.environ.get("KONG_KEY", "").strip()
        if api_key is None and kong_key:
            api_key = kong_key
            base_url = base_url or os.environ.get("OPENAI_BASE_URL", "").strip() or DEFAULT_BASE_URL
        else:
            api_key = api_key or os.environ.get("OPENAI_API_KEY")
            base_url = base_url or os.environ.get("OPENAI_BASE_URL", "").strip() or None
        if not api_key:
            raise ValueError("KONG_KEY or OPENAI_API_KEY is required")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.models: dict[ModelTask, str] = {
            "fast": fast_model
            or os.environ.get("OPENAI_MODEL_FAST")
            or DEFAULT_FAST_MODEL,
            "reasoning": reasoning_model
            or os.environ.get("OPENAI_MODEL_REASONING")
            or DEFAULT_REASONING_MODEL,
        }
        # Diagnostics expose the load-bearing tier used by Inspector metadata.
        self.model = self.models["reasoning"]

    def model_for(self, task: ModelTask) -> str:
        """Resolve one closed task class to a server-configured model."""
        models = getattr(self, "models", None)
        if models is None:  # supports lightweight __new__ test construction
            return self.model
        return models[task]

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        images: list[dict[str, str]] | None = None,
        task: ModelTask = "reasoning",
    ) -> str:
        user_content = _user_content(user_message, images)
        try:
            response = self.client.chat.completions.create(
                model=self.model_for(task),
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        except Exception as exc:  # noqa: BLE001 - degrade on content refusal, re-raise the rest
            if _is_content_refusal(exc):
                logger.warning("Prompt refused by content policy; returning empty text.")
                return ""
            raise
        return _response_text(response)

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
        """Return one strict JSON-Schema response.

        Provider syntax and refusal/incomplete handling live here so services
        define only their stage contract and domain validation.  A normal
        response is guaranteed by OpenAI to match ``schema``; deterministic
        service code still validates provenance and cross-record invariants.
        """
        user_content = _user_content(user_message, images)
        try:
            response = self.client.chat.completions.create(
                model=self.model_for(task),
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001
            if _is_content_refusal(exc):
                logger.warning("Structured prompt refused by content policy.")
                return None
            raise
        choices = getattr(response, "choices", [])
        if not choices:
            logger.warning("OpenAI structured response had no choices")
            return None
        choice = choices[0]
        message = getattr(choice, "message", None)
        refusal = getattr(message, "refusal", None) if message is not None else None
        if refusal:
            logger.warning("OpenAI structured response was refused: %s", refusal)
            return None
        content = getattr(message, "content", "") if message is not None else ""
        if not content:
            logger.warning(
                "OpenAI structured response had no content. finish_reason=%s usage=%s",
                getattr(choice, "finish_reason", None),
                getattr(response, "usage", None),
            )
            return None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("OpenAI structured response was not valid JSON")
            return None
        return parsed if isinstance(parsed, dict) else None

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
        task: ModelTask = "reasoning",
    ) -> ChatTurn:
        """One tool-capable turn, independent of the provider's wire format."""
        response = self.client.responses.create(
            **self._chat_request(messages, tools, max_tokens, task),
        )
        return _chat_turn(response)

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
        task: ModelTask = "reasoning",
    ) -> Iterator[ChatDelta]:
        """Stream text; publish tool calls only after the full turn succeeds.

        The SDK assembles completed output items, including encrypted reasoning.
        Services never parse provider deltas or reconstruct partial tool calls.
        The context manager closes the provider stream on failure or cancellation.
        """
        with self.client.responses.stream(
            **self._chat_request(messages, tools, max_tokens, task),
        ) as stream:
            for event in stream:
                if event.type in ("response.output_text.delta", "response.refusal.delta"):
                    yield ChatDelta(text=event.delta)
                elif event.type == "error":
                    raise RuntimeError("OpenAI chat stream failed")
            yield ChatDelta(turn=_chat_turn(stream.get_final_response()))

    def _chat_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        task: ModelTask,
    ) -> dict[str, Any]:
        return {
            "model": self.model_for(task),
            "input": _chat_input(messages),
            "max_output_tokens": max_tokens,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            # Responses otherwise normalizes function schemas to strict mode,
            # making previously optional navigation arguments required.
            "tools": [
                {"type": "function", **tool["function"],
                 "strict": tool["function"].get("strict", False)}
                for tool in tools or []
            ],
        }

    def search_web(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        max_uses: int = 5,
        task: ModelTask = "fast",
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
                model=self.model_for(task),
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


def _chat_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate application messages once; replay completed provider items intact."""
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.get("continuation") is not None:
            items.extend(message["continuation"])
        elif message["role"] == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": message["tool_call_id"],
                "output": message["content"],
            })
        else:
            content = message["content"]
            if isinstance(content, list):
                content = [_chat_content(part) for part in content]
            items.append({"role": message["role"], "content": content})
    return items


def _chat_content(part: dict[str, Any]) -> dict[str, Any]:
    if part["type"] == "text":
        return {"type": "input_text", "text": part["text"]}
    if part["type"] == "image_url":
        image = part["image_url"]
        return {"type": "input_image", "image_url": image["url"],
                "detail": image.get("detail", "auto")}
    raise ValueError(f"Unsupported chat content type: {part['type']}")


def _chat_turn(response: Any) -> ChatTurn:
    if response.status != "completed":
        raise RuntimeError(f"OpenAI chat response did not complete: {response.status}")
    output = tuple(item.model_dump(exclude_none=True) for item in response.output)
    calls = tuple(
        ToolCall(id=item["call_id"], name=item["name"], arguments=item["arguments"])
        for item in output if item["type"] == "function_call"
    )
    text = "".join(
        part["text"] if part["type"] == "output_text" else part["refusal"]
        for item in output if item["type"] == "message"
        for part in item["content"] if part["type"] in ("output_text", "refusal")
    )
    if not text.strip() and not calls:
        raise RuntimeError("OpenAI chat response contained no answer or tool calls")
    return ChatTurn(text=text, tool_calls=calls, continuation=output)


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


def _user_content(
    user_message: str,
    images: list[dict[str, str]] | None,
) -> Any:
    """Build the shared text/multimodal user payload without losing block IDs."""
    if not images:
        return user_message
    return [
        {"type": "text", "text": user_message},
        *[
            item
            for image in images
            for item in (
                {
                    "type": "text",
                    "text": f"Visual for document block [{image['block_id']}]:",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image["data_url"],
                        "detail": "high",
                    },
                },
            )
        ],
    ]


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
