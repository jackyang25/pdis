"""The Searcher interface must expose what the pipeline it calls actually accepts.

Two surfaces drifted apart once already. `run_pipeline` has accepted `condition` and
`intervention` since the ClinicalTrials adapter needed them, and the HTTP route never
forwarded either, so the only way to reach them was a Python call. The interface was
therefore narrower than the function behind it, and the narrowing was silent: with both
blank, every field-addressed adapter falls back to anchoring on the query text, which is
a field value no provider's index holds.

These tests hold the two boundaries that made that invisible:

    the route forwards every parameter of `run_pipeline` that is not operational
    the run reports what each lane did, so an empty lane is not read as no evidence
"""

from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone

from services.searcher import SearchReport, outcomes_to_dicts, run_pipeline
from services.searcher.models import (
    Finding,
    SearchOutcome,
    SearchRequest,
)

from api.routes import searcher as searcher_route

#: Parameters of `run_pipeline` that are deliberately not user-facing.
#:
#: Two budgets, an error policy and two injected capabilities. Every other parameter
#: describes the search a reader asked for, so it belongs on the interface.
OPERATIONAL = frozenset(
    {"runtime", "max_tokens", "max_uses", "raise_source_errors", "progress_callback"}
)


def _outcome(source: str, query: str, **kwargs) -> SearchOutcome:
    return SearchOutcome(
        request=SearchRequest(scope_ref="query", source=source, query=query),
        **kwargs,
    )


class RouteParameterDriftTests(unittest.TestCase):
    def test_route_accepts_every_non_operational_pipeline_parameter(self) -> None:
        expected = {
            name
            for name in inspect.signature(run_pipeline).parameters
            if name not in OPERATIONAL
        }
        accepted = set(inspect.signature(searcher_route.run_searcher).parameters)
        # `sources` is the plural form the route takes as one comma-joined field.
        missing = {name for name in expected if name not in accepted}
        self.assertEqual(
            missing,
            set(),
            "run_pipeline parameters unreachable from the route: "
            f"{sorted(missing)}. Either forward them or name them operational.",
        )

    def test_operational_parameters_stay_off_the_interface(self) -> None:
        accepted = set(inspect.signature(searcher_route.run_searcher).parameters)
        self.assertEqual(accepted & OPERATIONAL, set())

    def test_condition_and_intervention_are_the_facets_forwarded(self) -> None:
        """Named explicitly, so deleting the wiring fails here rather than in a run."""
        accepted = set(inspect.signature(searcher_route.run_searcher).parameters)
        self.assertLessEqual({"query", "sources", "condition", "intervention"}, accepted)


class OutcomeReportingTests(unittest.TestCase):
    def test_report_carries_findings_and_outcomes_together(self) -> None:
        report = SearchReport()
        self.assertEqual(report.findings, [])
        self.assertEqual(report.outcomes, [])

    def test_empty_skipped_and_failed_lanes_stay_distinct(self) -> None:
        rows = outcomes_to_dicts(
            [
                _outcome("pubmed", "melanoma AND vaccine"),
                _outcome("ctis", "condition:melanoma", status="skipped"),
                _outcome("chembl", "condition:melanoma", status="failed", error="429"),
            ]
        )
        self.assertEqual(
            [(row["source"], row["status"], row["returned"]) for row in rows],
            [("pubmed", "complete", 0), ("ctis", "skipped", 0), ("chembl", "failed", 0)],
        )
        self.assertEqual(rows[2]["error"], "429")

    def test_reported_query_is_the_native_one(self) -> None:
        """The whole point: the provider's request, not the reader's sentence."""
        rows = outcomes_to_dicts([_outcome("clinicaltrials", "condition:melanoma")])
        self.assertEqual(rows[0]["query"], "condition:melanoma")

    def test_returned_counts_the_request_not_the_deduped_union(self) -> None:
        found = Finding(
            url="https://example.org/a",
            title="A",
            query="q",
            retrieved_at=datetime.now(timezone.utc),
        )
        rows = outcomes_to_dicts(
            [
                _outcome("web", "q", findings=[found]),
                _outcome("pubmed", "q", findings=[found]),
            ]
        )
        # Both lanes did return it. Deduplication is what the findings list owns.
        self.assertEqual([row["returned"] for row in rows], [1, 1])


if __name__ == "__main__":
    unittest.main()
