"""Shared Anthropic client for Scout's bounded quantitative mapping.

Anthropic is intentionally not a general pipeline provider. This client is
constructed only at the API composition boundary and injected into Scout's
schema-bound document-target and retrieved-evidence mappers. Browser
requests cannot select the provider or model.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import anthropic

from shared.ai import (
    Effort,
    ModelTask,
    ResponseRefusedError,
    ResponseTruncatedError,
    Verbosity,
    log_model_call,
)
from shared.transport import MAX_RETRIES, http_client, structured_timeout
from shared.visuals import labelled_image_parts

DEFAULT_QUANTITATIVE_MODEL = "claude-opus-5"

#: Kong's native-Anthropic endpoint. Overridable for local/dev use against
#: Anthropic directly, validated like any other base URL.
DEFAULT_BASE_URL = "https://ai-kong-gateway.bmgf.io/v2/anthropic"

_IMAGE_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


class RequestStalledError(anthropic.APIError):
    """A call that ran for its whole read window without an answer.

    Its own type because the SDK retries ``APITimeoutError``, and a stall repeated is
    the same window spent again (`shared.transport`). An ``APIError``, so a stage that
    records provider failures records this one.
    """

    def __init__(self, request) -> None:
        super().__init__("The model did not answer within its time window.", request, body=None)


class AnthropicQuantitativeClient:
    """Minimal Claude Messages wrapper for schema-bound quantitative mapping."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        from anthropic import Anthropic  # type: ignore[reportMissingImports]

        # KONG_KEY, when present, routes through Kong's native-Anthropic
        # endpoint with Kong's own credential. Otherwise fall back to calling
        # Anthropic directly with ANTHROPIC_API_KEY, as before Kong existed.
        kong_key = os.environ.get("KONG_KEY", "").strip()
        if api_key is None and kong_key:
            api_key = kong_key
            base_url = (
                base_url or os.environ.get("ANTHROPIC_BASE_URL", "").strip() or DEFAULT_BASE_URL
            )
        else:
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
        if not api_key:
            raise ValueError("KONG_KEY or ANTHROPIC_API_KEY is required")
        self.client = Anthropic(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client(RequestStalledError),
            max_retries=max_retries,
        )
        self.model = (
            model
            or os.environ.get("ANTHROPIC_QUANTITATIVE_MODEL")
            or DEFAULT_QUANTITATIVE_MODEL
        )

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
        """Force one tool call whose input is the stage's existing JSON schema.

        ``task``, ``verbosity`` and ``cache_key`` satisfy the shared client protocol:
        Anthropic serves one server-owned model, has no verbosity control, and caches
        by prefix through the top-level ``cache_control`` sent on every call. A stated
        ``effort`` is sent as ``output_config.effort``.

        A forced tool, not ``output_config.format``: structured outputs refuse the
        schemas Scout maps with (``maxItems`` on arrays, and more than sixteen union-
        typed parameters), which tool input schemas accept. A reply stopped at
        ``max_tokens`` raises ``ResponseTruncatedError``, since its tool input would be
        an unfinished object; a refusal raises ``ResponseRefusedError``.
        """
        del verbosity, cache_key
        tool_name = schema_name[:64]
        usage_line: dict[str, Any] = {
            "provider": "anthropic", "schema_name": schema_name, "task": task,
            "model": self.model, "effort": effort, "max_tokens": max_tokens,
        }
        started = time.monotonic()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                # No sampling parameters. Current model tiers reject `temperature`,
                # so run-to-run consistency comes from request scope and schema.
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": _user_content(user_message, images, trailing_text),
                }],
                tools=[{
                    "name": tool_name,
                    "description": (
                        "Return the complete schema-bound extraction payload. Use this tool exactly "
                        "once and follow its input schema without adding prose."
                    ),
                    "input_schema": schema,
                }],
                tool_choice={"type": "tool", "name": tool_name},
                cache_control={"type": "ephemeral"},
                timeout=structured_timeout(max_tokens),
                **({"output_config": {"effort": effort}} if effort is not None else {}),
            )
        except Exception as exc:
            log_model_call(**usage_line, error=type(exc).__name__,
                           elapsed_ms=round((time.monotonic() - started) * 1000))
            raise
        stop_reason = getattr(response, "stop_reason", None)
        usage = getattr(response, "usage", None)
        log_model_call(
            **usage_line,
            prompt_tokens=_count(usage, "input_tokens"),
            cached_tokens=_count(usage, "cache_read_input_tokens"),
            cache_write_tokens=_count(usage, "cache_creation_input_tokens"),
            completion_tokens=_count(usage, "output_tokens"),
            reasoning_tokens=None,
            finish_reason=stop_reason,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        if stop_reason == "max_tokens":
            raise ResponseTruncatedError(
                "The model reached the response limit before completing its answer. "
                "No complete result was returned."
            )
        if stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise ResponseRefusedError(
                "The model declined to answer this request"
                + (f" ({category})." if category else ".")
            )
        for block in getattr(response, "content", []):
            if (
                getattr(block, "type", "") == "tool_use"
                and getattr(block, "name", "") == tool_name
            ):
                payload = getattr(block, "input", None)
                return payload if isinstance(payload, dict) else None
        return None


def _count(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None) if usage is not None else None
    return value if isinstance(value, int) else None


def _user_content(
    message: str,
    images: list[dict[str, str]] | None,
    trailing_text: str = "",
) -> list[dict[str, Any]]:
    """Text, then each image under the shared block-ID label, then trailing text.

    Everything before ``trailing_text`` is the prefix a stage's requests share, and it
    is marked as a cache breakpoint.

    An image that is not a supported base64 data URL is refused rather than
    dropped: the prompt names the block, so a missing image would leave the model
    reasoning about a visual it was told it had.
    """
    content: list[dict[str, Any]] = [{"type": "text", "text": message}]
    # Anthropic has no detail control; every image is read at its own resolution.
    for part in labelled_image_parts(
        (image.get("block_id", ""), image.get("data_url", "")) for image in images or []
    ):
        if part["type"] == "text":
            content.append({"type": "text", "text": part["text"]})
            continue
        media_type, data = _parse_data_url(part["image_url"]["url"])
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        })
    if trailing_text:
        # The shared prefix ends here, so it carries its own cache breakpoint: the
        # request-level one sits on the last block, which differs per item and so is
        # never read back by the next request.
        content[-1]["cache_control"] = {"type": "ephemeral"}
        content.append({"type": "text", "text": trailing_text})
    return content


def _parse_data_url(value: str) -> tuple[str, str]:
    if not value.startswith("data:") or ";base64," not in value:
        raise ValueError("Image input is not a base64 data URL")
    metadata, encoded = value[5:].split(";base64,", 1)
    media_type = metadata.strip().lower()
    if media_type not in _IMAGE_MEDIA_TYPES:
        raise ValueError(f"Image media type {media_type!r} is not supported")
    try:
        base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Image input is not valid base64") from exc
    return media_type, encoded
