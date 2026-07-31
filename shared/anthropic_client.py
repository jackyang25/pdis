"""Shared Anthropic client for Scout's bounded quantitative mapping.

Anthropic is intentionally not a general pipeline provider. This client is
constructed only at the API composition boundary and injected into Scout's
schema-bound document-target and retrieved-evidence mappers. Browser
requests cannot select the provider or model.
"""

from __future__ import annotations

import base64
import os
from typing import Any


DEFAULT_QUANTITATIVE_MODEL = "claude-opus-5"


class AnthropicQuantitativeClient:
    """Minimal Claude Messages wrapper for schema-bound quantitative mapping."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
    ) -> None:
        from anthropic import Anthropic  # type: ignore[reportMissingImports]

        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = Anthropic(api_key=api_key)
        self.model = (
            model
            or os.environ.get("ANTHROPIC_QUANTITATIVE_MODEL")
            # Environment import boundary for existing local/deployed setups.
            or os.environ.get("ANTHROPIC_EXTRACTION_MODEL")
            or DEFAULT_QUANTITATIVE_MODEL
        )

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        images: list[dict[str, str]] | None = None,
        task: str = "reasoning",
    ) -> str:
        """Return plain text for protocol completeness.

        ``task`` is accepted only to satisfy the shared injected-client
        protocol. Anthropic is already scoped to one server-owned quantitative
        mapping responsibility.
        """
        del task
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": _user_content(user_message, images)}],
        )
        return "\n".join(
            str(getattr(block, "text", ""))
            for block in getattr(response, "content", [])
            if getattr(block, "type", "") == "text"
        ).strip()

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: str = "reasoning",
    ) -> dict[str, Any] | None:
        """Force one tool call whose input is the stage's existing JSON schema."""
        del task
        tool_name = schema_name[:64]
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            # No sampling parameters. Current model tiers reject `temperature`,
            # so run-to-run consistency comes from request scope and schema.
            system=system_prompt,
            messages=[{"role": "user", "content": _user_content(user_message, images)}],
            tools=[{
                "name": tool_name,
                "description": (
                    "Return the complete schema-bound extraction payload. Use this tool exactly "
                    "once and follow its input schema without adding prose."
                ),
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in getattr(response, "content", []):
            if (
                getattr(block, "type", "") == "tool_use"
                and getattr(block, "name", "") == tool_name
            ):
                payload = getattr(block, "input", None)
                return payload if isinstance(payload, dict) else None
        return None


def _user_content(
    message: str,
    images: list[dict[str, str]] | None,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": message}]
    for image in images or []:
        parsed = _parse_data_url(image.get("data_url", ""))
        if parsed is None:
            continue
        media_type, data = parsed
        content.extend([
            {
                "type": "text",
                "text": f"Document image block [{image.get('block_id', '')}]",
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            },
        ])
    return content


def _parse_data_url(value: str) -> tuple[str, str] | None:
    if not value.startswith("data:") or ";base64," not in value:
        return None
    metadata, encoded = value[5:].split(";base64,", 1)
    media_type = metadata.strip().lower()
    if media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        return None
    try:
        base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None
    return media_type, encoded
