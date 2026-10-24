"""Server-owned task-tier selection for the shared OpenAI client."""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import openai

from shared.ai import ResponseRefusedError, ResponseTruncatedError
from shared.openai_client import (
    DEFAULT_FAST_MODEL,
    DEFAULT_REASONING_MODEL,
    OpenAIClient,
)
from shared.transport import MAX_RETRIES, StallTransport


class OpenAIClientConfigurationTests(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_environment_selects_models_for_closed_task_tiers(self, _client: object) -> None:
        with patch.dict(os.environ, {
            "OPENAI_MODEL_FAST": "fast-test",
            "OPENAI_MODEL_REASONING": "reasoning-test",
        }):
            client = OpenAIClient(api_key="test-key")

        self.assertEqual(client.model_for("fast"), "fast-test")
        self.assertEqual(client.model_for("reasoning"), "reasoning-test")
        self.assertEqual(client.model, "reasoning-test")

    @patch("openai.OpenAI")
    def test_defaults_apply_when_tier_overrides_are_absent(self, _client: object) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_MODEL_FAST", None)
            os.environ.pop("OPENAI_MODEL_REASONING", None)
            default_client = OpenAIClient(api_key="test-key")

        self.assertEqual(default_client.model_for("fast"), DEFAULT_FAST_MODEL)
        self.assertEqual(default_client.model_for("fast"), "gpt-5.6-luna")
        self.assertEqual(default_client.model_for("reasoning"), DEFAULT_REASONING_MODEL)


class StructuredContentOrderTests(unittest.TestCase):
    def _client(self, finish_reason="stop", refusal=None, usage=None):
        with patch("openai.OpenAI"):
            client = OpenAIClient(api_key="test-key")
        client.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(
                content="{}", refusal=refusal))], usage=usage,
        )
        return client

    def test_the_call_policy_is_sent_only_when_stated(self) -> None:
        client = self._client()
        client.call_structured("system", "document", 10, schema_name="s", schema={})
        sent = client.client.chat.completions.create.call_args.kwargs
        for name in ("reasoning_effort", "verbosity", "prompt_cache_key"):
            self.assertNotIn(name, sent)
        client.call_structured("system", "document", 10, schema_name="s", schema={},
                               effort="low", verbosity="low", cache_key="s:abc")
        sent = client.client.chat.completions.create.call_args.kwargs
        self.assertEqual((sent["reasoning_effort"], sent["verbosity"], sent["prompt_cache_key"]),
                         ("low", "low", "s:abc"))

    def test_a_refusal_and_a_content_filter_are_typed_refusals(self) -> None:
        for client in (self._client(refusal="I can't help with that."),
                       self._client(finish_reason="content_filter")):
            with self.assertRaises(ResponseRefusedError):
                client.call_structured("system", "document", 10, schema_name="s", schema={})

    def test_a_policy_rejected_prompt_is_a_refusal_not_an_empty_answer(self) -> None:
        client = self._client()
        client.client.chat.completions.create.side_effect = RuntimeError("invalid_prompt: limited access")
        with self.assertRaises(ResponseRefusedError):
            client.call_structured("system", "document", 10, schema_name="s", schema={})

    def test_a_cut_off_answer_is_a_typed_truncation(self) -> None:
        with self.assertRaises(ResponseTruncatedError):
            self._client(finish_reason="length").call_structured(
                "system", "document", 10, schema_name="s", schema={})

    def test_every_call_writes_one_usage_line_without_content(self) -> None:
        usage = SimpleNamespace(
            prompt_tokens=1200, completion_tokens=300,
            prompt_tokens_details=SimpleNamespace(cached_tokens=1024),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=250),
        )
        client = self._client(usage=usage)
        with self.assertLogs("shared.ai", "INFO") as logs:
            client.call_structured("secret system", "secret document", 10, schema_name="s",
                                   schema={}, task="fast", effort="low")
        (line,) = logs.output
        self.assertNotIn("secret", line)
        fields = json.loads(line.split("model_call ", 1)[1])
        self.assertEqual(
            {key: fields[key] for key in ("schema_name", "task", "effort", "prompt_tokens",
                                          "cached_tokens", "completion_tokens", "reasoning_tokens",
                                          "finish_reason", "attempt")},
            {"schema_name": "s", "task": "fast", "effort": "low", "prompt_tokens": 1200,
             "cached_tokens": 1024, "completion_tokens": 300, "reasoning_tokens": 250,
             "finish_reason": "stop", "attempt": 1},
        )
        self.assertIn("elapsed_ms", fields)

    def _sent_user_content(self, client):
        messages = client.client.chat.completions.create.call_args.kwargs["messages"]
        return messages[1]["content"]

    def test_trailing_text_follows_the_images_so_the_shared_prefix_comes_first(self) -> None:
        client = self._client()
        client.call_structured(
            "system", "document", 10, schema_name="s", schema={},
            images=[{"block_id": "doc/b-1", "data_url": "data:image/png;base64,AA=="}],
            trailing_text="question",
        )
        content = self._sent_user_content(client)
        self.assertEqual([part["type"] for part in content], ["text", "text", "image_url", "text"])
        self.assertEqual(content[0]["text"], "document")
        self.assertEqual(content[-1]["text"], "question")

    def test_without_images_trailing_text_is_one_message(self) -> None:
        client = self._client()
        client.call_structured("system", "document", 10, schema_name="s", schema={},
                               trailing_text="question")
        self.assertEqual(self._sent_user_content(client), "document\n\nquestion")

    @patch("openai.OpenAI")
    def test_timeout_and_retries_are_stated_not_inherited(self, sdk) -> None:
        OpenAIClient(api_key="test-key")
        kwargs = sdk.call_args.kwargs
        self.assertLess(kwargs["http_client"].timeout.read, 600)
        self.assertEqual(kwargs["max_retries"], MAX_RETRIES)

    def test_a_structured_call_is_given_a_window_sized_to_its_budget(self) -> None:
        client = self._client()
        client.call_structured("system", "document", 4000, schema_name="s", schema={})
        small = client.client.chat.completions.create.call_args.kwargs["timeout"].read
        client.call_structured("system", "document", 16000, schema_name="s", schema={})
        large = client.client.chat.completions.create.call_args.kwargs["timeout"].read
        self.assertLess(small, large)
        self.assertLessEqual(large, 720)


if __name__ == "__main__":
    unittest.main()


class StallRetryTests(unittest.TestCase):
    """The SDK retries a refused or dropped request, never a call that ran out its window."""

    def _sdk(self, handler):
        attempts = []

        def counted(request):
            attempts.append(request)
            return handler(request)

        transport = StallTransport(lambda request: openai.APITimeoutError(request=request),
                                   inner=httpx.MockTransport(counted))
        sdk = openai.OpenAI(api_key="k", base_url="http://test", max_retries=2,
                            http_client=httpx.Client(transport=transport))
        return sdk, attempts

    def _create(self, sdk):
        return sdk.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])

    def test_a_read_timeout_is_not_retried(self) -> None:
        def stall(request):
            raise httpx.ReadTimeout("no answer", request=request)

        sdk, attempts = self._sdk(stall)
        with self.assertRaises(openai.APITimeoutError):
            self._create(sdk)
        self.assertEqual(len(attempts), 1)

    def test_a_stalled_send_or_a_full_pool_is_not_retried_either(self) -> None:
        # A dead connection can stall while the request is still being written. That
        # surfaced as a write timeout, which the SDK retried as a connection error: one
        # live call hung through three full windows, 41 minutes, before failing its run.
        for timeout in (httpx.WriteTimeout, httpx.PoolTimeout):
            def stall(request, timeout=timeout):
                raise timeout("stalled", request=request)

            sdk, attempts = self._sdk(stall)
            with self.assertRaises(openai.APITimeoutError):
                self._create(sdk)
            self.assertEqual(len(attempts), 1, timeout.__name__)

    def test_sending_has_its_own_short_window_and_the_answer_keeps_its_budget(self) -> None:
        from shared.transport import SEND_TIMEOUT_SECONDS, structured_timeout

        window = structured_timeout(16000)
        self.assertEqual(window.write, SEND_TIMEOUT_SECONDS)
        self.assertEqual(window.pool, SEND_TIMEOUT_SECONDS)
        self.assertGreater(window.read, SEND_TIMEOUT_SECONDS)

    def test_a_server_error_is_still_retried(self) -> None:
        def busy(request):
            return httpx.Response(503, headers={"retry-after-ms": "1"}, json={"error": {}})

        sdk, attempts = self._sdk(busy)
        with self.assertRaises(openai.APIStatusError):
            self._create(sdk)
        self.assertEqual(len(attempts), 3)
