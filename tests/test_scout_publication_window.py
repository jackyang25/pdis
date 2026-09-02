"""A requested publication window scopes retrieval, not the display.

Every insight, precedent, and benchmark statistic describes the evidence the run
admitted. Filtering later would leave those numbers answering a wider question
than the one the user asked, so the window is applied where evidence enters and
what it held out is recorded rather than discarded.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from services.scout.models import ScoutResult
from services.scout.pipeline import _search_all
from services.searcher import Finding
from services.searcher.models import SearchOutcome, SearchRequest


def _finding(url: str, published: str | None) -> Finding:
    return Finding(
        url=url,
        title=url,
        query="efficacy",
        excerpt="",
        source="pubmed",
        retrieved_at=datetime(2026, 8, 7),
        published_at=datetime.fromisoformat(published) if published else None,
    )


class _StubRuntime:
    """`_search_all` only forwards this to the controller, which is stubbed."""


class PublicationWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        import services.scout.pipeline as pipeline

        self.pipeline = pipeline
        self.original = pipeline.run_requests
        self.addCleanup(setattr, pipeline, "run_requests", self.original)

    def stub_outcomes(self, findings: list[Finding]) -> SearchRequest:
        request = SearchRequest(source="pubmed", query="efficacy", scope_ref="efficacy")
        outcome = SearchOutcome(request=request, findings=findings)
        self.pipeline.run_requests = lambda *_a, **_k: [outcome]
        return request

    def test_a_finding_dated_before_the_window_does_not_enter_the_run(self) -> None:
        request = self.stub_outcomes([
            _finding("https://example.org/old", "2019-04-02"),
            _finding("https://example.org/new", "2026-02-11"),
        ])
        admitted, total, plan = _search_all(
            [request], _StubRuntime(), published_since="2025-01-01"
        )

        self.assertEqual([f.url for f in admitted["efficacy"]], ["https://example.org/new"])
        self.assertEqual(total, 1, "the funnel counts what the run admitted")
        self.assertEqual(plan[0].excluded_before_window, ["https://example.org/old"])
        # The retrieval record stays complete: the window reports a cost, it does
        # not rewrite what the source returned.
        self.assertEqual(plan[0].finding_count, 2)
        self.assertEqual(len(plan[0].source_urls), 2)

    def test_an_undated_finding_is_admitted(self) -> None:
        """Web pages rarely carry a date; absent is not old."""
        request = self.stub_outcomes([
            _finding("https://example.org/page", None),
            _finding("https://example.org/old", "2019-04-02"),
        ])
        admitted, total, plan = _search_all(
            [request], _StubRuntime(), published_since="2025-01-01"
        )

        self.assertEqual([f.url for f in admitted["efficacy"]], ["https://example.org/page"])
        self.assertEqual(total, 1)
        self.assertEqual(plan[0].excluded_before_window, ["https://example.org/old"])

    def test_a_finding_on_the_boundary_is_admitted(self) -> None:
        request = self.stub_outcomes([_finding("https://example.org/edge", "2025-01-01")])
        admitted, _total, plan = _search_all(
            [request], _StubRuntime(), published_since="2025-01-01"
        )

        self.assertEqual([f.url for f in admitted["efficacy"]], ["https://example.org/edge"])
        self.assertEqual(plan[0].excluded_before_window, [])

    def test_no_window_admits_everything_and_records_no_exclusion(self) -> None:
        request = self.stub_outcomes([
            _finding("https://example.org/old", "2001-01-01"),
            _finding("https://example.org/page", None),
        ])
        admitted, total, plan = _search_all([request], _StubRuntime())

        self.assertEqual(len(admitted["efficacy"]), 2)
        self.assertEqual(total, 2)
        self.assertEqual(plan[0].excluded_before_window, [])


class WindowIsRecordedOnTheResultTests(unittest.TestCase):
    """A statistic is unreadable without the window that produced its cohort."""

    def test_the_window_round_trips_as_an_iso_date(self) -> None:
        result = ScoutResult(
            matches=[], assessments=[], stats=None, context_validation=None,
            published_since=" 2025-03-01 ",
        )
        self.assertEqual(result.published_since, "2025-03-01")

    def test_no_window_is_the_default(self) -> None:
        result = ScoutResult(
            matches=[], assessments=[], stats=None, context_validation=None,
        )
        self.assertEqual(result.published_since, "")

    def test_an_unparseable_window_is_refused_at_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "ISO date"):
            ScoutResult(
                matches=[], assessments=[], stats=None, context_validation=None,
                published_since="March 2025",
            )


if __name__ == "__main__":
    unittest.main()


class WindowSurvivesTheReviewRoundTripTests(unittest.TestCase):
    """The client holds the draft between the two phases.

    The window is declared before targets are reviewed and used after, so losing
    it in rehydration would widen the retrieved cohort with nothing to show for
    it — the statistics would silently answer a broader question.
    """

    def draft_payload(self, **overrides) -> dict:
        payload = {
            "phase": "target_review",
            "stats": {
                "queries": 0, "findings": 0, "unique_findings": 0,
                "insights": 0, "matches": 0, "assessments": 0,
            },
            "context_validation": {"status": "match", "configured_indication": "polio"},
            "quantitative_ledger": {
                "status": "not_applicable", "reason": "", "block_ids": [],
                "reviews": [], "targets": [],
            },
            "variables": [],
            "blocks": [],
        }
        payload.update(overrides)
        return payload

    def test_the_window_is_rehydrated_with_the_reviewed_draft(self) -> None:
        from services.scout.contract import result_from_target_review

        draft = result_from_target_review(
            self.draft_payload(published_since="2025-03-01")
        )
        self.assertEqual(draft.published_since, "2025-03-01")

    def test_a_draft_without_a_window_rehydrates_unscoped(self) -> None:
        from services.scout.contract import result_from_target_review

        draft = result_from_target_review(self.draft_payload())
        self.assertEqual(draft.published_since, "")
