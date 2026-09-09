"""Failures must cross an already-open SSE response without becoming answer text."""

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.assistant import router, sse
from services.assistant import Chunk, answer_stream
from shared.chat import ChatDelta, ChatTurn, ToolCall


class AssistantStreamTests(unittest.TestCase):
    def test_agent_executes_completed_calls_and_carries_continuation_only_within_a_request(self):
        continuation = object()  # The agent must not interpret provider state.
        requests = []

        class Client:
            def chat_stream(self, messages, **kwargs):
                requests.append([dict(message) for message in messages])
                if len(requests) % 2:
                    yield ChatDelta(turn=ChatTurn("", (
                        ToolCall("call-1", "read_result", '{"path":"title"}'),
                    ), continuation))
                else:
                    yield ChatDelta(text="Trial plan")
                    yield ChatDelta(turn=ChatTurn("Trial plan", (), object()))

        client = Client()
        for _ in range(2):
            chunks = list(answer_stream(client, {"title": "Trial plan"}, "workspace", [
                {"role": "user", "content": "What is the title?"},
            ]))
            self.assertEqual([chunk.text for chunk in chunks if chunk.kind == "text"], ["Trial plan"])
            self.assertTrue(any(chunk.kind == "activity" for chunk in chunks))
        for index in (0, 2):
            self.assertFalse(any("continuation" in message for message in requests[index]))
            self.assertIs(requests[index + 1][-2]["continuation"], continuation)
            self.assertEqual(requests[index + 1][-1]["tool_call_id"], "call-1")
            self.assertIn("Trial plan", requests[index + 1][-1]["content"])

    def test_success_frames_text_activity_and_explicit_completion(self):
        events = list(sse(iter([Chunk("activity", "Reading"), Chunk("text", "Hello\nthere") ])))
        self.assertEqual(events, [
            'event: activity\ndata: "Reading"\n\n',
            'data: "Hello\\nthere"\n\n',
            'event: done\ndata: {}\n\n',
        ])

    def test_route_reports_failure_after_partial_text_without_leaking_provider_details(self):
        def failing(*args, **kwargs):
            yield Chunk("text", "Partial answer")
            raise RuntimeError("private provider credentials or prompt detail")

        app = FastAPI()
        app.include_router(router)
        with patch("api.routes.assistant.get_openai_client", return_value=object()), \
             patch("api.routes.assistant.assistant_answer_stream", side_effect=failing), \
             self.assertLogs("api.routes.assistant", level="ERROR"):
            result = TestClient(app).post("/ask/stream", json={
                "result_type": "workspace", "result": {},
                "messages": [{"role": "user", "content": "Hi"}],
            })
        self.assertEqual(result.status_code, 200)  # Headers were already sent.
        self.assertIn("text/event-stream", result.headers["content-type"])
        self.assertIn('data: "Partial answer"', result.text)
        self.assertNotIn("private provider", result.text)
        self.assertNotIn("event: done", result.text)
        payload = result.text.split("event: error\ndata: ")[1].strip()
        self.assertEqual(json.loads(payload)["code"], "assistant_stream_failed")
