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
import time
from typing import Any, Iterable, Iterator, Literal

from shared.ai import (
    Effort,
    ModelTask,
    ResponseRefusedError,
    ResponseTruncatedError,
    Verbosity,
    log_model_call,
)
from shared.chat import ChatDelta, ChatTurn, ToolCall, Usage
from shared.transport import MAX_RETRIES, http_client, structured_timeout
from shared.visuals import labelled_image_parts

logger = logging.getLogger(__name__)

__all__ = ["ModelTask", "OpenAIClient"]

DEFAULT_FAST_MODEL = "gpt-5.6-luna"
DEFAULT_REASONING_MODEL = "gpt-6-astra"

#: Kong's OpenAI-compatible unified endpoint. Overridable for local/dev use
#: against OpenAI directly, validated like any other base URL.
DEFAULT_BASE_URL = "https://ai-kong-gateway.bmgf.io/ai/v2"

#: How images returned by a tool reach the model. "native" puts them inside the
#: function_call_output; "follow_up" sends the text there and the images in one user
#: message after the turn's outputs. Set by verification against the live endpoint.
TOOL_IMAGES: Literal["native", "follow_up"] = "native"

TRUNCATED_MESSAGE = (
    "The model reached the response limit before completing its answer. "
    "No complete result was returned."
)


class OpenAIClient:
    """OpenAI wrapper: structured calls, streamed tool chat, and web search."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        fast_model: str | None = None,
        reasoning_model: str | None = None,
        max_retries: int = MAX_RETRIES,
    ):
        from openai import APITimeoutError, OpenAI  # type: ignore[reportMissingImports]

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
        # The SDK retries connection errors, 429s and 5xx; a read timeout reaches it as
        # its own timeout error, which it propagates without retrying (`shared.transport`).
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client(lambda request: APITimeoutError(request=request)),
            max_retries=max_retries,
        )
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
        return self.models[task]

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        trailing_text: str = "",
        task: ModelTask = "reasoning",
        effort: Effort | None = None,
        verbosity: Verbosity | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Return one strict JSON-Schema response.

        Provider syntax and refusal/incomplete handling live here so services
        define only their stage contract and domain validation.  A normal
        response is guaranteed by OpenAI to match ``schema``; deterministic
        service code still validates provenance and cross-record invariants.
        A reply cut off at ``max_tokens`` raises ``ResponseTruncatedError``; a
        refusal or content filter raises ``ResponseRefusedError``. Every call
        writes one usage line, whatever its outcome.
        """
        model = self.model_for(task)
        policy: dict[str, Any] = {}
        if effort is not None:
            policy["reasoning_effort"] = effort
        if verbosity is not None:
            policy["verbosity"] = verbosity
        if cache_key:
            policy["prompt_cache_key"] = cache_key
        usage_line: dict[str, Any] = {
            "provider": "openai", "schema_name": schema_name, "task": task, "model": model,
            "effort": effort, "max_tokens": max_tokens,
        }
        started = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _user_content(user_message, images, trailing_text)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                },
                timeout=structured_timeout(max_tokens, task),
                **policy,
            )
        except Exception as exc:  # noqa: BLE001
            log_model_call(**usage_line, error=type(exc).__name__,
                           elapsed_ms=_elapsed_ms(started))
            if _is_content_refusal(exc):
                raise ResponseRefusedError(
                    "The model provider declined this request under its content policy."
                ) from exc
            raise
        choices = getattr(response, "choices", None) or []
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        log_model_call(**usage_line, **_completion_usage(getattr(response, "usage", None)),
                       finish_reason=finish_reason, elapsed_ms=_elapsed_ms(started))
        if not choices:
            logger.warning("OpenAI structured response had no choices")
            return None
        if finish_reason == "length":
            raise ResponseTruncatedError(TRUNCATED_MESSAGE)
        if finish_reason == "content_filter":
            raise ResponseRefusedError("The model provider's content filter stopped this answer.")
        message = getattr(choices[0], "message", None)
        refusal = getattr(message, "refusal", None) if message is not None else None
        if refusal:
            raise ResponseRefusedError(f"The model declined to answer: {refusal}")
        content = getattr(message, "content", "") if message is not None else ""
        if not content:
            logger.warning("OpenAI structured response had no content. finish_reason=%s", finish_reason)
            return None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("OpenAI structured response was not valid JSON")
            return None
        return parsed if isinstance(parsed, dict) else None

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
        task: ModelTask = "reasoning",
        effort: Effort | None = None,
    ) -> Iterator[ChatDelta]:
        """Stream text; publish tool calls only after the full turn succeeds.

        The SDK assembles completed output items, including encrypted reasoning.
        Services never parse provider deltas or reconstruct partial tool calls.
        The context manager closes the provider stream on failure or cancellation.
        """
        with self.client.responses.stream(
            **self._chat_request(messages, tools, max_tokens, task, effort),
        ) as stream:
            for event in stream:
                if event.type in ("response.output_text.delta", "response.refusal.delta"):
                    yield ChatDelta(text=event.delta)
                elif event.type == "error":
                    # The provider's own words, so a failed answer can be diagnosed
                    # from the log rather than from the fact that it failed.
                    raise RuntimeError(
                        "OpenAI chat stream failed: "
                        + " ".join(str(part) for part in (
                            getattr(event, "code", None), getattr(event, "message", None),
                        ) if part)
                    )
            yield ChatDelta(turn=_chat_turn(stream.get_final_response()))

    def _chat_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        task: ModelTask,
        effort: Effort | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
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
        if effort is not None:
            request["reasoning"] = {"effort": effort}
        return request

    def search_web(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        task: ModelTask = "fast",
    ) -> Any:
        """Run an LLM-driven web search via OpenAI's Responses API.

        Uses the built-in `web_search` tool. Returns the raw Responses API
        response object; callers extract URLs and cited text from the
        output's annotations.
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
    pending: list[Any] = []  # follow-up images for the current run of tool outputs

    def flush() -> None:
        if pending:
            items.append({"role": "user", "content": [
                {"type": "input_text", "text": "Visuals returned by the tool calls above:"},
                *(_chat_content(part) for part in _image_parts(pending)),
            ]})
            pending.clear()

    for message in messages:
        if message["role"] == "tool" and message.get("continuation") is None:
            images = tuple(message.get("images") or ())
            output: Any = message["content"]
            if images and TOOL_IMAGES == "native":
                output = [{"type": "input_text", "text": message["content"]},
                          *(_chat_content(part) for part in _image_parts(images))]
            elif images:
                pending.extend(images)
            items.append({"type": "function_call_output",
                          "call_id": message["tool_call_id"], "output": output})
            continue
        flush()
        if message.get("continuation") is not None:
            items.extend(message["continuation"])
        else:
            content = message["content"]
            if isinstance(content, list):
                content = [_chat_content(part) for part in content]
            items.append({"role": message["role"], "content": content})
    flush()
    return items


def _image_parts(images: Iterable[Any]) -> list[dict[str, Any]]:
    return labelled_image_parts((image.block_id, image.data_url) for image in images)


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
        reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        if reason == "max_output_tokens":
            raise ResponseTruncatedError(TRUNCATED_MESSAGE)
        if reason == "content_filter":
            raise ResponseRefusedError("The model provider's content filter stopped this answer.")
        raise RuntimeError(
            f"OpenAI chat response did not complete: {response.status}"
            + (f" ({reason})" if reason else "")
        )
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
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    return ChatTurn(
        text=text, tool_calls=calls, continuation=output,
        usage=Usage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            cached_input_tokens=int(getattr(details, "cached_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        ),
    )


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _completion_usage(usage: Any) -> dict[str, int | None]:
    """The token counts a usage line reports, read off a Chat Completions usage object."""
    def count(source: Any, name: str) -> int | None:
        value = getattr(source, name, None) if source is not None else None
        return value if isinstance(value, int) else None

    prompt = getattr(usage, "prompt_tokens_details", None)
    completion = getattr(usage, "completion_tokens_details", None)
    return {
        "prompt_tokens": count(usage, "prompt_tokens"),
        "cached_tokens": count(prompt, "cached_tokens"),
        # Reported by the gateway beside OpenAI's own fields: tokens written to its cache.
        "cache_write_tokens": count(prompt, "cache_write_tokens"),
        "completion_tokens": count(usage, "completion_tokens"),
        "reasoning_tokens": count(completion, "reasoning_tokens"),
    }


def _is_content_refusal(exc: Exception) -> bool:
    """True if this is an OpenAI content-policy refusal (dual-use / biosecurity
    'invalid_prompt'). These cannot succeed on retry: a structured call raises
    ``ResponseRefusedError`` for it, and a web search skips the query. Any other
    error (network, auth, rate limit) returns False and is re-raised by the caller.
    """
    if getattr(exc, "code", None) == "invalid_prompt":
        return True
    text = str(exc)
    return "invalid_prompt" in text or "limited access to this content" in text


def _user_content(
    user_message: str,
    images: list[dict[str, str]] | None,
    trailing_text: str = "",
) -> Any:
    """Build the shared text/multimodal user payload without losing block IDs.

    Order is text, labelled images, then ``trailing_text``: what stays the same
    across a stage's requests comes first so the provider can reuse its prefix.
    """
    if not images:
        return "\n\n".join(part for part in (user_message, trailing_text) if part)
    return [
        {"type": "text", "text": user_message},
        *labelled_image_parts(
            (image["block_id"], image["data_url"], image.get("detail", "high"))  # type: ignore[misc]
            for image in images
        ),
        *([{"type": "text", "text": trailing_text}] if trailing_text else []),
    ]
