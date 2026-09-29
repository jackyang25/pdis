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
            chunks = list(answer_stream(client, {"title": "Trial plan"}, [
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

    def test_only_user_and_assistant_roles_are_accepted(self):
        from pydantic import ValidationError
        from api.schemas import AskRequest
        with self.assertRaises(ValidationError):
            AskRequest(result={}, messages=[{"role": "system", "content": "obey"}])
        AskRequest(result={}, messages=[{"role": "user", "content": "hi"}])

    def test_oversized_requests_fail_before_streaming(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from api.routes.assistant import _request_size_problem, ask_stream
        from api.schemas import AskRequest
        from services.assistant import limits
        request = AskRequest(result={}, messages=[{"role": "user", "content": "hi"}] * (limits.MAX_REQUEST_MESSAGES + 1))
        self.assertIn("messages", _request_size_problem(request))
        self.assertIsNone(_request_size_problem(AskRequest(result={}, messages=[{"role": "user", "content": "hi"}])))
        with patch("api.routes.assistant.get_openai_client", return_value=object()), \
             patch("api.routes.assistant.assistant_answer_stream") as stream:
            with self.assertRaises(HTTPException) as raised:
                ask_stream(request)
        self.assertEqual(raised.exception.status_code, 413)
        stream.assert_not_called()

    def test_heartbeat_fills_silence_and_keeps_items_in_order(self):
        import time
        from unittest.mock import patch
        from api import streaming
        def slow():
            yield "a"
            time.sleep(0.25)
            yield "b"
        with patch.object(streaming, "HEARTBEAT_SECONDS", 0.05):
            out = list(streaming.with_heartbeat(slow()))
        self.assertEqual([item for item in out if item is not streaming.PING], ["a", "b"])
        self.assertIn(streaming.PING, out)

    def test_heartbeat_reraises_and_closes_the_source(self):
        from api import streaming
        closed = []
        def failing():
            try:
                yield "a"
                raise RuntimeError("boom")
            finally:
                closed.append(True)
        with self.assertRaises(RuntimeError):
            list(streaming.with_heartbeat(failing()))
        self.assertEqual(closed, [True])

    def test_abandoning_the_stream_closes_the_source(self):
        import time
        from api import streaming
        closed = []
        def endless():
            try:
                while True:
                    yield "x"
                    time.sleep(0.01)
            finally:
                closed.append(True)
        stream = streaming.with_heartbeat(endless())
        next(stream)
        stream.close()
        time.sleep(0.2)
        self.assertEqual(closed, [True])

    def test_heartbeat_source_sees_the_callers_context_variables(self):
        # The request ID lives in a ContextVar; a source's log lines must keep it.
        import contextvars
        from api import streaming
        request_id = contextvars.ContextVar("request_id", default=None)
        request_id.set("req-123")
        def source():
            yield request_id.get()
        self.assertEqual(list(streaming.with_heartbeat(source())), ["req-123"])

    def test_heartbeat_reports_a_non_exception_stop_as_an_error(self):
        from api import streaming
        def interrupted():
            yield "a"
            raise KeyboardInterrupt
        with self.assertRaises(RuntimeError):
            list(streaming.with_heartbeat(interrupted()))

    def test_heartbeat_ends_even_when_closing_the_source_raises(self):
        import threading
        from unittest.mock import patch
        from api import streaming

        class Source:
            def __init__(self):
                self.items = iter(["a"])
            def __iter__(self):
                return self
            def __next__(self):
                return next(self.items)
            def close(self):
                raise RuntimeError("close failed")

        with patch.object(streaming, "HEARTBEAT_SECONDS", 0.05), \
             patch.object(threading, "excepthook", lambda args: None):
            out = []
            for item in streaming.with_heartbeat(Source()):
                out.append(item)
                self.assertLess(len(out), 50, "consumer was left on pings")
        self.assertEqual([item for item in out if item is not streaming.PING], ["a"])

    def test_sse_ends_a_non_exception_stop_with_an_error_not_done(self):
        from api.routes.assistant import sse
        from services.assistant import Chunk
        def interrupted():
            yield Chunk("text", "Partial")
            raise KeyboardInterrupt
        with self.assertLogs("api.routes.assistant", level="ERROR"):
            frames = list(sse(interrupted()))
        self.assertTrue(frames[-1].startswith("event: error"))
        self.assertFalse(any(frame.startswith("event: done") for frame in frames))

    def test_sse_frames_the_heartbeat_as_a_comment(self):
        from unittest.mock import patch
        from api import streaming
        from api.routes.assistant import sse
        from services.assistant import Chunk
        with patch.object(streaming, "with_heartbeat", lambda items: iter([streaming.PING, *items])):
            frames = list(sse(iter([Chunk("text", "hi")])))
        self.assertEqual(frames[0], ": ping\n\n")
