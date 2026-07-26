"""Provider isolation and schema transport for the Scout target verifier."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shared.anthropic_client import AnthropicReviewClient, DEFAULT_REVIEW_MODEL


class _Messages:
    def __init__(self, response: object):
        self.response = response
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class AnthropicReviewClientTests(unittest.TestCase):
    def _client(self, response: object, *, model: str | None = None):
        messages = _Messages(response)
        sdk_client = SimpleNamespace(messages=messages)
        module = SimpleNamespace(Anthropic=lambda **_kwargs: sdk_client)
        environment = {"ANTHROPIC_API_KEY": "test-key"}
        if model is not None:
            environment["ANTHROPIC_REVIEW_MODEL"] = model
        with patch.dict(sys.modules, {"anthropic": module}), patch.dict(
            os.environ, environment, clear=False
        ):
            client = AnthropicReviewClient()
        return client, messages

    def test_default_model_is_the_server_owned_opus_tier(self) -> None:
        with patch.dict(sys.modules, {
            "anthropic": SimpleNamespace(Anthropic=lambda **_kwargs: object()),
        }), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            os.environ.pop("ANTHROPIC_REVIEW_MODEL", None)
            client = AnthropicReviewClient()

        self.assertEqual(client.model, DEFAULT_REVIEW_MODEL)

    def test_structured_review_forces_the_existing_stage_schema(self) -> None:
        payload = {"reviews": [{"target_id": "qt-one", "decision": "confirm"}]}
        response = SimpleNamespace(content=[SimpleNamespace(
            type="tool_use",
            name="scout_document_target_review",
            input=payload,
        )])
        client, messages = self._client(response, model="opus-test")
        schema = {
            "type": "object",
            "properties": {"reviews": {"type": "array"}},
            "required": ["reviews"],
            "additionalProperties": False,
        }

        result = client.call_structured(
            "system",
            "document and proposals",
            1000,
            schema_name="scout_document_target_review",
            schema=schema,
        )

        self.assertEqual(result, payload)
        self.assertEqual(messages.kwargs["model"], "opus-test")
        self.assertEqual(messages.kwargs["tools"][0]["input_schema"], schema)
        self.assertEqual(
            messages.kwargs["tool_choice"],
            {"type": "tool", "name": "scout_document_target_review"},
        )


if __name__ == "__main__":
    unittest.main()
