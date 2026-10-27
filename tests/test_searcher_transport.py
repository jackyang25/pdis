"""One transport, one pacing rule, one per-run memo, and failures that say what happened."""

from __future__ import annotations

import io
import json
import socket
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

import services.searcher.transport as transport
from services.searcher import (
    RetrievalError,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceQueryIntent,
    outcomes_to_dicts,
    plan_requests,
    run_requests,
    source_specs,
)
from services.searcher.calls import note_warning, provider_call
from services.searcher.sources.literature import build_europepmc_query, build_pubmed_query
import services.searcher.calls as search_calls
from services.searcher.sources.open_targets import OpenTargetsSource


class _Body:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.body


def _http_error(code: int, body: bytes = b"", headers: dict | None = None):
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError("https://x.test", code, "reason", message, io.BytesIO(body))


class RetryTests(unittest.TestCase):
    def _fetch(self, *outcomes, **kwargs):
        sequence = list(outcomes)

        def fake_open(request, *, timeout):
            item = sequence.pop(0)
            if isinstance(item, BaseException):
                raise item
            return _Body(item)

        with (
            patch.object(transport, "_open", fake_open),
            patch.object(transport, "pause") as sleep,
        ):
            try:
                return transport.fetch("https://x.test", provider="P", **kwargs), sleep
            except RetrievalError as exc:
                return exc, sleep

    def test_a_transient_status_is_retried(self) -> None:
        for status in (429, 502, 503, 504):
            with self.subTest(status=status):
                body, sleep = self._fetch(_http_error(status), b"ok")
                self.assertEqual(body, b"ok")
                sleep.assert_called_once()

    def test_a_reset_connection_and_a_timeout_are_retried(self) -> None:
        for failure in (ConnectionResetError("reset"), urllib.error.URLError(TimeoutError("t"))):
            with self.subTest(failure=failure):
                body, _ = self._fetch(failure, b"ok")
                self.assertEqual(body, b"ok")

    def test_a_refused_connection_and_a_client_error_are_not(self) -> None:
        for failure, code in (
            (urllib.error.URLError(ConnectionRefusedError("refused")), "unavailable"),
            (_http_error(400, b'{"error": "bad field"}', {"Content-Type": "application/json"}), "http_error"),
        ):
            with self.subTest(code=code):
                error, sleep = self._fetch(failure, b"never")
                self.assertIsInstance(error, RetrievalError)
                self.assertEqual(error.code, code)
                sleep.assert_not_called()

    def test_retry_after_is_honoured(self) -> None:
        _, sleep = self._fetch(_http_error(429, headers={"Retry-After": "7"}), b"ok")
        sleep.assert_called_once_with(7.0)

    def test_a_wait_past_the_deadline_fails_now(self) -> None:
        error, sleep = self._fetch(
            _http_error(429, headers={"Retry-After": "120"}), b"ok", deadline_seconds=10
        )
        self.assertEqual(error.code, "rate_limited")
        sleep.assert_not_called()

    def test_attempts_are_bounded(self) -> None:
        error, sleep = self._fetch(*[_http_error(503)] * 5, max_attempts=3)
        self.assertEqual(error.status, 503)
        self.assertEqual(sleep.call_count, 2)

    def test_a_rate_limited_call_retries_once(self) -> None:
        """A second 429 after a paced wait means the quota is spent; more attempts would
        only queue behind every other call to that provider."""
        error, sleep = self._fetch(*[_http_error(429)] * 4, b"ok")
        self.assertEqual(error.code, "rate_limited")
        self.assertEqual(sleep.call_count, 1)

    def test_a_retry_waits_for_its_providers_pacing_slot(self) -> None:
        """A retry spends the provider's quota like any call. Retried on the transport's own
        timer, a 429 from a one-call-a-second provider drew a second call inside that second."""
        sequence = [_http_error(429), b"ok"]

        def fake_open(request, *, timeout):
            item = sequence.pop(0)
            if isinstance(item, BaseException):
                raise item
            return _Body(item)

        with (
            patch.object(transport, "_open", fake_open),
            patch.object(transport, "pause"),
            patch("services.searcher.calls.pace") as pace,
        ):
            body = provider_call(
                SearchRuntime(llm_client=None), rate_group="g", interval_seconds=1.1,
                operation="op", arguments={}, load=lambda: transport.fetch("https://x.test", provider="P"),
            )
        self.assertEqual(body, b"ok")
        self.assertEqual([call.args for call in pace.call_args_list], [("g", 1.1), ("g", 1.1)])

    def test_the_providers_message_is_kept_and_its_secret_removed(self) -> None:
        body = json.dumps({"error": "API rate limit exceeded", "api-key": "k-123"}).encode()
        error, _ = self._fetch(
            _http_error(400, body, {"Content-Type": "application/json"}), secrets=("k-123",)
        )
        self.assertIn("API rate limit exceeded", str(error))
        self.assertNotIn("k-123", str(error))

    def test_an_html_error_page_is_not_a_message(self) -> None:
        error, _ = self._fetch(
            _http_error(404, b"<html><body>Not here</body></html>", {"Content-Type": "text/html"})
        )
        self.assertNotIn("<html>", str(error))

    def test_the_product_identifies_itself_without_an_invented_contact(self) -> None:
        self.assertEqual(transport.user_agent(), "PDIS-Searcher/1.0")
        self.assertEqual(
            transport.user_agent("ops@example.org"), "PDIS-Searcher/1.0 (mailto:ops@example.org)"
        )


class AddressSelectionTests(unittest.TestCase):
    def test_importing_searcher_leaves_name_resolution_alone(self) -> None:
        import services.searcher  # noqa: F401

        self.assertEqual(socket.getaddrinfo.__module__, "socket")

    def test_an_ipv4_address_is_tried_first(self) -> None:
        with (
            patch.object(
                transport.socket,
                "getaddrinfo",
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))],
            ) as lookup,
            patch.object(transport.socket, "create_connection", return_value="sock") as connect,
        ):
            self.assertEqual(transport._ipv4_first_connection(("host.test", 443), 5), "sock")
        self.assertEqual(lookup.call_args.args[2], socket.AF_INET)
        self.assertEqual(connect.call_args.args[0], ("192.0.2.1", 443))

    def test_a_host_with_no_ipv4_address_uses_normal_resolution(self) -> None:
        with (
            patch.object(transport.socket, "getaddrinfo", side_effect=socket.gaierror()),
            patch.object(transport.socket, "create_connection", return_value="sock") as connect,
        ):
            transport._ipv4_first_connection(("v6.test", 443), 5)
        self.assertEqual(connect.call_args.args[0], ("v6.test", 443))

    def test_searchers_connections_use_it(self) -> None:
        connection = transport._HTTPSConnection("host.test")
        self.assertIs(connection._create_connection, transport._ipv4_first_connection)


class RateGroupTests(unittest.TestCase):
    def test_lanes_spending_one_providers_quota_share_a_group(self) -> None:
        groups = {spec.key: spec.rate_group for spec in source_specs()}
        self.assertEqual(groups["fda"], groups["fda_safety"])
        self.assertEqual(groups["web"], "web")

    def test_a_group_declares_one_interval(self) -> None:
        intervals: dict[str, set[float]] = {}
        for spec in source_specs():
            intervals.setdefault(spec.rate_group, set()).add(spec.request_interval_seconds)
        self.assertEqual({group: len(values) for group, values in intervals.items() if len(values) > 1}, {})

    def test_every_provider_call_is_paced_not_only_the_first(self) -> None:
        """Open Targets makes three calls for one request, and each spends its quota."""
        answers = iter([
            {"data": {"search": {"hits": [{"id": "MONDO_1", "name": "malaria"}]}}},
            {"data": {"search": {"hits": [{"id": "ENSG1", "name": "CSP"}]}}},
            {"data": {"disease": {"id": "MONDO_1", "name": "malaria", "evidences": {"rows": []}}}},
        ])
        request = SearchRequest(scope_ref="q", source="open_targets", query="x", options=(
            ("target_name", "CSP"), ("target_identifier", ""), ("disease_name", "malaria"),
        ))
        with (
            patch.object(search_calls, "fetch", lambda *a, **k: json.dumps(next(answers)).encode()),
            patch("services.searcher.calls.pace") as pace,
        ):
            OpenTargetsSource().search(request, SearchRuntime(llm_client=None), max_tokens=1)
        self.assertEqual(pace.call_count, 3)


class PerRunReuseTests(unittest.TestCase):
    def _intent(self, scope_ref: str) -> RetrievalIntent:
        return RetrievalIntent(
            scope_ref=scope_ref,
            topic=scope_ref,
            description="",
            indication="malaria",
            intervention_class="vaccine",
            queries=(SourceQueryIntent(text=f"{scope_ref} query"),),
        )

    def test_identical_native_calls_reach_the_provider_once_and_keep_their_lineage(self) -> None:
        calls: list[str] = []

        def fetch(url, **kwargs):
            calls.append(url)
            return json.dumps({"data": [{"ctNumber": "2024-500001-11-00", "ctTitle": "T"}]}).encode()

        requests = plan_requests(
            [self._intent("efficacy"), self._intent("safety")], sources=("ctis",)
        )
        with patch.object(search_calls, "fetch", fetch), patch("services.searcher.calls.pace"):
            outcomes = run_requests(requests, runtime=SearchRuntime(llm_client=None), max_tokens=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [outcome.request.input_queries for outcome in outcomes],
            [("efficacy query",), ("safety query",)],
        )
        self.assertTrue(all(len(outcome.findings) == 1 for outcome in outcomes))

    def test_a_reused_answer_carries_the_providers_notes(self) -> None:
        runtime = SearchRuntime(llm_client=None)

        def load():
            note_warning("provider_warning", "phrase not found")
            return 1

        from services.searcher.calls import collecting_notes

        for _ in range(2):
            with collecting_notes() as notes:
                provider_call(runtime, rate_group="g", interval_seconds=0,
                              operation="op", arguments={"a": 1}, load=load)
            self.assertEqual([w.detail for w in notes.warnings], ["phrase not found"])


class OutcomeReportingTests(unittest.TestCase):
    def test_a_failure_carries_a_code_beside_the_providers_message(self) -> None:
        def fetch(url, **kwargs):
            raise RetrievalError("EU CTIS", "rate_limited", "slow down", status=429)

        request = SearchRequest(scope_ref="q", source="ctis", query="x",
                                options=(("medical_condition", "malaria"),))
        with patch.object(search_calls, "fetch", fetch), patch("services.searcher.calls.pace"):
            (outcome,) = run_requests([request], runtime=SearchRuntime(llm_client=None), max_tokens=1)
        (row,) = outcomes_to_dicts([outcome])
        self.assertEqual((row["status"], row["error_code"]), ("failed", "rate_limited"))
        self.assertIn("slow down", row["detail"])

    def test_pubmeds_own_reading_of_the_query_is_recorded(self) -> None:
        esearch = (
            b"<eSearchResult><Count>0</Count><IdList/>"
            b"<QueryTranslation>\"rsv\"[All Fields]</QueryTranslation>"
            b"<WarningList><QuotedPhraseNotFound>\"rsv x\"</QuotedPhraseNotFound></WarningList>"
            b"</eSearchResult>"
        )
        request = SearchRequest(scope_ref="q", source="pubmed", query='rsv AND "rsv x"')
        with (
            patch.object(transport, "_open", lambda *a, **k: _Body(esearch)),
            patch("services.searcher.calls.pace"),
        ):
            (outcome,) = run_requests([request], runtime=SearchRuntime(llm_client=None), max_tokens=1)
        self.assertEqual(outcome.provider_query, '"rsv"[All Fields]')
        self.assertEqual(
            [(w.code, w.detail) for w in outcome.warnings],
            [("provider_warning", 'QuotedPhraseNotFound: "rsv x"')],
        )


class QueryCompilationTests(unittest.TestCase):
    def _intent(self, indication: str, *queries: SourceQueryIntent) -> RetrievalIntent:
        return RetrievalIntent(
            scope_ref="q", topic=queries[0].text, description="", indication=indication,
            intervention_class="", queries=queries,
        )

    def test_a_free_text_question_is_asked_once(self) -> None:
        intent = self._intent("", SourceQueryIntent(text="RSV maternal vaccine efficacy"))
        self.assertEqual(
            build_pubmed_query(intent, "general", list(intent.queries)),
            "(RSV maternal vaccine efficacy)",
        )

    def test_europe_pmc_widens_with_each_query_instead_of_narrowing(self) -> None:
        from services.searcher import QueryFacets

        intent = self._intent(
            "malaria",
            SourceQueryIntent(text="a", facets=QueryFacets(outcome="protective efficacy")),
            SourceQueryIntent(text="b", facets=QueryFacets(outcome="efficacy waning")),
        )
        self.assertEqual(
            build_europepmc_query(intent, "general", list(intent.queries)),
            "malaria AND ((protective efficacy) OR (efficacy waning))",
        )

    def test_europe_pmc_grammar_characters_are_not_passed_as_content(self) -> None:
        from services.searcher import QueryFacets

        intent = self._intent(
            "malaria", SourceQueryIntent(text="a", facets=QueryFacets(outcome='titre: "high" -x'))
        )
        self.assertEqual(
            build_europepmc_query(intent, "general", list(intent.queries)),
            "malaria AND (titre high x)",
        )


if __name__ == "__main__":
    unittest.main()
