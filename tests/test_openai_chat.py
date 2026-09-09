"""The chat adapter preserves tool lineage without exposing provider events to Ask."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from shared.openai_client import OpenAIClient


class OutputItem(dict):
    def model_dump(self, **kwargs):
        return dict(self)


def response(*items, status="completed"):
    return SimpleNamespace(status=status, output=[OutputItem(item) for item in items])


def text_item(text):
    return {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


class ProviderStream:
    def __init__(self, final, events=()):
        self.final = final
        self.events = events
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def __iter__(self):
        return iter(self.events)

    def get_final_response(self):
        return self.final


class OpenAIChatTests(unittest.TestCase):
    def client(self, final, events=()):
        client = OpenAIClient.__new__(OpenAIClient)
        client.models = {"reasoning": "gpt-6-astra", "fast": "fast-test"}
        stream = ProviderStream(final, events)
        provider = Mock()
        provider.chat.completions.create.side_effect = AssertionError("Tool chat must use Responses, not Chat Completions")
        provider.responses.stream.return_value = stream
        provider.responses.create.return_value = final
        client.client = provider
        return client, provider, stream

    def test_stream_uses_responses_and_emits_text_once(self):
        client, provider, stream = self.client(response(text_item("Hello")), [
            SimpleNamespace(type="response.output_text.delta", delta="Hel"),
            SimpleNamespace(type="response.output_text.delta", delta="lo"),
        ])
        events = list(client.chat_stream([{"role": "user", "content": "Hi"}]))
        self.assertEqual("".join(event.text for event in events), "Hello")
        self.assertEqual(events[-1].turn.text, "Hello")
        request = provider.responses.stream.call_args.kwargs
        self.assertEqual(request["model"], "gpt-6-astra")
        self.assertFalse(request["store"])
        self.assertEqual(request["include"], ["reasoning.encrypted_content"])
        self.assertNotIn("previous_response_id", request)
        provider.chat.completions.create.assert_not_called()
        self.assertTrue(stream.closed)

    def test_tool_roundtrip_preserves_reasoning_call_ids_and_optional_schema(self):
        reasoning = {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "opaque"}
        call = {"id": "fc_1", "type": "function_call", "call_id": "call_1",
                "name": "read_result", "arguments": '{"path":"title"}', "status": "completed"}
        client, provider, _ = self.client(response(reasoning, call))
        tools = [{"type": "function", "function": {"name": "read_result", "description": "Read",
                  "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
        messages = [{"role": "user", "content": "Read the title"}]
        turn = list(client.chat_stream(messages, tools=tools))[-1].turn
        self.assertEqual(turn.tool_calls[0].id, "call_1")
        self.assertEqual(turn.tool_calls[0].name, "read_result")
        self.assertEqual(turn.tool_calls[0].arguments, '{"path":"title"}')
        offered = provider.responses.stream.call_args.kwargs["tools"][0]
        self.assertEqual(offered["parameters"], tools[0]["function"]["parameters"])
        self.assertFalse(offered["strict"])  # Preserve optional tool arguments.
        provider.responses.create.return_value = response(text_item("The title"))
        reply = client.chat(messages + [
            {"role": "assistant", "content": "", "continuation": turn.continuation},
            {"role": "tool", "tool_call_id": "call_1", "content": "The title"},
        ])
        self.assertEqual(reply.text, "The title")
        self.assertEqual(provider.responses.create.call_args.kwargs["input"], [
            messages[0], reasoning, call,
            {"type": "function_call_output", "call_id": "call_1", "output": "The title"},
        ])

    def test_images_keep_their_exact_block_label_and_bytes(self):
        client, provider, _ = self.client(response(text_item("A plot")))
        client.chat([{"role": "user", "content": [
            {"type": "text", "text": "Visual for [doc:block:3]"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}},
        ]}])
        self.assertEqual(provider.responses.create.call_args.kwargs["input"][0]["content"], [
            {"type": "input_text", "text": "Visual for [doc:block:3]"},
            {"type": "input_image", "image_url": "data:image/png;base64,AAAA", "detail": "high"},
        ])

    def test_failed_incomplete_and_empty_turns_raise_instead_of_silently_finishing(self):
        for status in ("failed", "incomplete", "completed"):
            with self.subTest(status=status):
                client, _, stream = self.client(response(status=status))
                with self.assertRaises(RuntimeError):
                    list(client.chat_stream([{"role": "user", "content": "Hi"}]))
                self.assertTrue(stream.closed)

    def test_cancelling_the_iterator_closes_the_provider_stream(self):
        client, _, stream = self.client(response(text_item("Hello")), [
            SimpleNamespace(type="response.output_text.delta", delta="Hello"),
        ])
        iterator = client.chat_stream([{"role": "user", "content": "Hi"}])
        next(iterator)
        iterator.close()
        self.assertTrue(stream.closed)
