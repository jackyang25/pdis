"""Repeated provider fetches share one call without serialising unrelated ones."""

from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

from services.searcher import SearchRequest, SearchRuntime
from services.searcher.cache import SingleFlightCache
from services.searcher.sources.clinicaltrials import ClinicalTrialsSource
from services.searcher.stages import clinicaltrials as ctgov
from services.searcher.stages import pubmed


class SingleFlightCacheTests(unittest.TestCase):
    def test_concurrent_callers_for_one_key_share_one_load(self) -> None:
        cache: SingleFlightCache[int] = SingleFlightCache(max_entries=4, ttl_seconds=60)
        calls: list[int] = []
        release = threading.Event()

        def load() -> int:
            calls.append(1)
            release.wait(timeout=5)
            return 7

        results: list[int] = []
        threads = [
            threading.Thread(target=lambda: results.append(cache.get("k", load)))
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        time.sleep(0.1)
        release.set()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(calls, [1])
        self.assertEqual(results, [7] * 4)

    def test_a_slow_key_does_not_hold_another(self) -> None:
        """One lock for every fetch made CT.gov a single lane, process-wide."""
        cache: SingleFlightCache[str] = SingleFlightCache(max_entries=4, ttl_seconds=60)
        release = threading.Event()
        slow = threading.Thread(
            target=lambda: cache.get("slow", lambda: release.wait(timeout=5) and "slow")
        )
        slow.start()
        time.sleep(0.05)
        started = time.monotonic()
        self.assertEqual(cache.get("fast", lambda: "fast"), "fast")
        self.assertLess(time.monotonic() - started, 1)
        release.set()
        slow.join(timeout=5)

    def test_entries_expire_and_the_oldest_is_evicted(self) -> None:
        cache: SingleFlightCache[int] = SingleFlightCache(max_entries=2, ttl_seconds=0.05)
        loads: list[str] = []

        def load(key: str):
            return lambda: loads.append(key) or len(loads)

        cache.get("a", load("a"))
        cache.get("a", load("a"))
        time.sleep(0.1)
        cache.get("a", load("a"))
        self.assertEqual(loads, ["a", "a"])

        bounded: SingleFlightCache[int] = SingleFlightCache(max_entries=2, ttl_seconds=60)
        loads.clear()
        for key in ("a", "b", "c", "a"):
            bounded.get(key, load(key))
        self.assertEqual(loads, ["a", "b", "c", "a"])

    def test_a_failure_reaches_the_caller_and_is_not_kept(self) -> None:
        cache: SingleFlightCache[int] = SingleFlightCache(max_entries=2, ttl_seconds=60)

        def fail() -> int:
            raise RuntimeError("429")

        with self.assertRaises(RuntimeError):
            cache.get("k", fail)
        self.assertEqual(cache.get("k", lambda: 3), 3)


class _Body:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.body


def _runtime() -> SearchRuntime:
    return SearchRuntime(llm_client=None)


class ClinicalTrialsFetchTests(unittest.TestCase):
    def _fetch(self, runtime: SearchRuntime, **kwargs):
        return ctgov.fetch_clinicaltrials_studies(
            runtime,
            rate_group="clinicaltrials",
            interval_seconds=0,
            condition="malaria",
            intervention="vaccine",
            max_results=ClinicalTrialsSource.spec.max_results,
            **kwargs,
        )

    def test_a_repeated_request_in_one_run_reaches_the_provider_once(self) -> None:
        body = json.dumps({"studies": [{"protocolSection": {}}]}).encode()
        with patch(
            "services.searcher.transport._open", side_effect=lambda *a, **k: _Body(body)
        ) as opened:
            runtime = _runtime()
            first = self._fetch(runtime)
            first.clear()
            second = self._fetch(runtime)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(len(second), 1)
            # Reuse is per run: another run asks the provider again.
            self._fetch(_runtime())
            self.assertEqual(opened.call_count, 2)

    def test_it_asks_for_the_records_it_keeps_and_only_the_fields_it_reads(self) -> None:
        captured: list[str] = []

        def fake_open(request, *, timeout):
            captured.append(request.full_url)
            return _Body(json.dumps({"studies": []}).encode())

        with patch("services.searcher.transport._open", fake_open):
            self._fetch(_runtime(), first_posted_since="2024-01-01")

        params = dict(parse_qsl(urlsplit(captured[0]).query))
        self.assertEqual(params["pageSize"], str(ClinicalTrialsSource.spec.max_results))
        self.assertIn("protocolSection.identificationModule", params["fields"])
        self.assertEqual(
            params["filter.advanced"], "AREA[StudyFirstPostDate]RANGE[2024-01-01,MAX]"
        )

    def test_each_provider_call_is_paced_against_the_specs_rate_group(self) -> None:
        body = json.dumps({"studies": []}).encode()
        with (
            patch("services.searcher.transport._open", side_effect=lambda *a, **k: _Body(body)),
            patch("services.searcher.calls.pace") as pace,
        ):
            ClinicalTrialsSource().search(
                SearchRequest(
                    scope_ref="q",
                    source="clinicaltrials",
                    query="condition:malaria",
                    options=(("condition", "malaria"),),
                ),
                _runtime(),
                max_tokens=1,
            )
        pace.assert_called_once_with(
            "clinicaltrials", ClinicalTrialsSource.spec.request_interval_seconds
        )
        self.assertGreater(ClinicalTrialsSource.spec.request_interval_seconds, 0)


class PubMedFullTextTests(unittest.TestCase):
    ARTICLE = (
        "<pmc-articleset><article><body>"
        '<sec sec-type="intro"><p>Background prose.</p></sec>'
        '<sec sec-type="results"><p>Efficacy was 82%.</p></sec>'
        "<sec><title>Results</title><p>Untyped section.</p></sec>"
        "</body></article></pmc-articleset>"
    )

    def test_only_the_declared_results_section_is_read(self) -> None:
        root = pubmed.ET.fromstring(self.ARTICLE)
        with patch.object(pubmed, "_request_xml", return_value=root):
            text = pubmed._pmc_results_section(_runtime(), "PMC1")
        self.assertEqual(text, "Efficacy was 82%.")

    def test_the_results_section_is_bounded_by_the_excerpt(self) -> None:
        article = (
            '<pmc-articleset><article><body><sec sec-type="results"><p>{}</p></sec>'
            "</body></article></pmc-articleset>"
        )
        root = pubmed.ET.fromstring(article.format("word " * 10_000))
        with patch.object(pubmed, "_request_xml", return_value=root):
            text = pubmed._pmc_results_section(_runtime(), "PMC1")
        self.assertLessEqual(len(text), pubmed.MAX_EXCERPT_CHARS)


if __name__ == "__main__":
    unittest.main()
