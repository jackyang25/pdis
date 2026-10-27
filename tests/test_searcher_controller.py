"""The retrieval scheduler's worker threads behave like the request that started them."""

from __future__ import annotations

import contextvars
import threading
import unittest
from unittest.mock import patch

from services.searcher import SearchRequest, SearchRuntime, SourceSpec, run_requests
from services.searcher.sources import SOURCE_REGISTRY

MARKER = contextvars.ContextVar("marker", default="")


class _RecordingSource:
    spec = SourceSpec(
        key="fake",
        label="Fake",
        worker_limit=4,
        evidence_class="general",
        jurisdiction="global",
        reads=("text",),
        feeds=("insights",),
    )

    def __init__(self) -> None:
        self.seen: list[str] = []

    def plan(self, intent):
        return []

    def search(self, request, runtime, **_):
        self.seen.append(MARKER.get())
        return []


def _requests(count: int) -> list[SearchRequest]:
    return [
        SearchRequest(scope_ref="scope", source="fake", query=f"query {index}")
        for index in range(count)
    ]


class SchedulerContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _RecordingSource()
        patcher = patch.dict(SOURCE_REGISTRY, {"fake": self.source})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_requests(self, requests, progress=None):
        return run_requests(
            requests, runtime=SearchRuntime(llm_client=None), max_tokens=1,
            progress=progress,
        )

    def test_each_request_runs_in_the_callers_context(self) -> None:
        """The request ID lives in a ContextVar; a bare pool worker logs without it."""
        MARKER.set("request-1")
        self.run_requests(_requests(3))
        self.assertEqual(self.source.seen, ["request-1"] * 3)

    def test_a_slow_progress_callback_does_not_hold_other_workers(self) -> None:
        """MCP's callback waits on its client; the count lock must not be held through it."""
        second_reported = threading.Event()
        first_saw_second: list[bool] = []

        def progress(completed: int, total: int) -> None:
            if completed == 1:
                first_saw_second.append(second_reported.wait(timeout=2))
            elif completed == 2:
                second_reported.set()

        self.run_requests(_requests(2), progress=progress)
        self.assertEqual(first_saw_second, [True])


class PublicShapeTests(unittest.TestCase):
    def test_the_model_client_protocol_has_the_name_every_service_exports(self) -> None:
        import services.searcher as searcher

        self.assertIn("LLMClientProtocol", searcher.__all__)
        self.assertFalse(hasattr(searcher, "SearcherLLMClientProtocol"))

    def test_credentials_never_appear_in_a_repr(self) -> None:
        """A connector or runtime in a log line or a traceback must not print its key."""
        from services.searcher import TavilyHTTPConnector

        for holder in (
            TavilyHTTPConnector(api_key="secret-value"),
            SearchRuntime(llm_client=None, credentials={"ncbi": "secret-value"}),
        ):
            with self.subTest(holder=type(holder).__name__):
                self.assertNotIn("secret-value", repr(holder))


if __name__ == "__main__":
    unittest.main()
