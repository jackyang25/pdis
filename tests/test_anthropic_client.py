"""Provider isolation and schema transport for Scout quantitative mapping."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shared.ai import ResponseRefusedError, ResponseTruncatedError
from shared.anthropic_client import (
    AnthropicQuantitativeClient,
    DEFAULT_QUANTITATIVE_MODEL,
)

_PNG = "data:image/png;base64,iVBORw0KGgo="


class _Messages:
    def __init__(self, response: object):
        self.response = response
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class AnthropicQuantitativeClientTests(unittest.TestCase):
    def _client(self, response: object, *, model: str | None = None):
        messages = _Messages(response)
        sdk_client = SimpleNamespace(messages=messages)
        module = SimpleNamespace(Anthropic=lambda **_kwargs: sdk_client)
        environment = {"ANTHROPIC_API_KEY": "test-key"}
        if model is not None:
            environment["ANTHROPIC_QUANTITATIVE_MODEL"] = model
        with patch.dict(sys.modules, {"anthropic": module}), patch.dict(
            os.environ, environment, clear=False
        ):
            client = AnthropicQuantitativeClient()
        return client, messages

    def test_default_model_is_the_server_owned_opus_tier(self) -> None:
        with patch.dict(sys.modules, {
            "anthropic": SimpleNamespace(Anthropic=lambda **_kwargs: object()),
        }), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            os.environ.pop("ANTHROPIC_QUANTITATIVE_MODEL", None)
            os.environ.pop("ANTHROPIC_EXTRACTION_MODEL", None)
            client = AnthropicQuantitativeClient()

        self.assertEqual(client.model, DEFAULT_QUANTITATIVE_MODEL)

    def test_structured_mapping_sends_no_sampling_parameters(self) -> None:
        """Current model tiers reject sampling knobs; the request must omit them."""
        response = SimpleNamespace(content=[SimpleNamespace(
            type="tool_use",
            name="scout_source_measurement_batch",
            input={"decisions": []},
        )])
        client, messages = self._client(response)

        client.call_structured(
            "system",
            "source passages",
            1000,
            schema_name="scout_source_measurement_batch",
            schema={"type": "object"},
        )

        self.assertNotIn("temperature", messages.kwargs)
        self.assertNotIn("top_p", messages.kwargs)

    def test_structured_extraction_forces_the_existing_stage_schema(self) -> None:
        payload = {"reviews": [{"unit_id": "unit-one", "classification": "target"}]}
        response = SimpleNamespace(content=[SimpleNamespace(
            type="tool_use",
            name="scout_document_quantitative_ledger_batch",
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
            schema_name="scout_document_quantitative_ledger_batch",
            schema=schema,
        )

        self.assertEqual(result, payload)
        self.assertEqual(messages.kwargs["model"], "opus-test")
        self.assertEqual(messages.kwargs["tools"][0]["input_schema"], schema)
        self.assertEqual(
            messages.kwargs["tool_choice"],
            {"type": "tool", "name": "scout_document_quantitative_ledger_batch"},
        )

    def _tool_response(self, **extra):
        return SimpleNamespace(content=[SimpleNamespace(
            type="tool_use", name="stage", input={"decisions": []},
        )], **extra)

    def test_a_reply_stopped_at_its_budget_is_a_typed_truncation(self) -> None:
        client, _ = self._client(self._tool_response(stop_reason="max_tokens"))

        with self.assertRaises(ResponseTruncatedError) as raised:
            client.call_structured("system", "text", 10, schema_name="stage", schema={})

        self.assertEqual(raised.exception.code, "response_truncated")

    def test_a_refusal_is_typed_and_carries_its_code(self) -> None:
        client, _ = self._client(self._tool_response(stop_reason="refusal"))

        with self.assertRaises(ResponseRefusedError) as raised:
            client.call_structured("system", "text", 10, schema_name="stage", schema={})

        self.assertEqual(raised.exception.code, "response_refused")

    def test_effort_is_sent_when_stated_and_the_prefix_is_always_cacheable(self) -> None:
        client, messages = self._client(self._tool_response(stop_reason="tool_use"))

        client.call_structured("system", "text", 10, schema_name="stage", schema={})
        self.assertNotIn("output_config", messages.kwargs)
        self.assertEqual(messages.kwargs["cache_control"], {"type": "ephemeral"})

        client.call_structured("system", "text", 10, schema_name="stage", schema={}, effort="low")
        self.assertEqual(messages.kwargs["output_config"], {"effort": "low"})

    def test_images_use_the_shared_label_and_trailing_text_follows_them(self) -> None:
        client, messages = self._client(self._tool_response(stop_reason="tool_use"))

        client.call_structured(
            "system", "document", 10, schema_name="stage", schema={},
            images=[{"block_id": "doc/b-0001", "data_url": _PNG}],
            trailing_text="the item",
        )

        content = messages.kwargs["messages"][0]["content"]
        self.assertEqual([part["type"] for part in content], ["text", "text", "image", "text"])
        # The shared prefix ends at the last image, which carries its own cache breakpoint.
        self.assertEqual(content[2]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", content[3])
        self.assertEqual(content[1]["text"], "Visual for document block [doc/b-0001]:")
        self.assertEqual(content[2]["source"]["media_type"], "image/png")
        self.assertEqual(content[3]["text"], "the item")

    def test_an_unreadable_image_is_refused_rather_than_dropped(self) -> None:
        client, _ = self._client(self._tool_response(stop_reason="tool_use"))

        for data_url in ("not-a-data-url", "data:image/tiff;base64,AAAA", "data:image/png;base64,***"):
            with self.subTest(data_url=data_url), self.assertRaises(ValueError):
                client.call_structured(
                    "system", "document", 10, schema_name="stage", schema={},
                    images=[{"block_id": "doc/b-0001", "data_url": data_url}],
                )


if __name__ == "__main__":
    unittest.main()


class AnthropicStallRetryTests(unittest.TestCase):
    def test_a_read_timeout_is_not_retried_but_a_server_error_is(self) -> None:
        import anthropic
        import httpx

        from shared.anthropic_client import RequestStalledError
        from shared.transport import StallTransport

        def sdk(handler):
            attempts = []

            def counted(request):
                attempts.append(request)
                return handler(request)

            client = anthropic.Anthropic(
                api_key="k", base_url="http://test", max_retries=2,
                http_client=httpx.Client(transport=StallTransport(
                    RequestStalledError, inner=httpx.MockTransport(counted))),
            )
            return client, attempts

        def create(client):
            return client.messages.create(model="m", max_tokens=10,
                                          messages=[{"role": "user", "content": "x"}])

        def stall(request):
            raise httpx.ReadTimeout("no answer", request=request)

        client, attempts = sdk(stall)
        with self.assertRaises(RequestStalledError):
            create(client)
        self.assertEqual(len(attempts), 1)

        client, attempts = sdk(lambda request: httpx.Response(
            503, headers={"retry-after-ms": "1"}, json={"type": "error", "error": {}}))
        with self.assertRaises(anthropic.APIStatusError):
            create(client)
        self.assertEqual(len(attempts), 3)
