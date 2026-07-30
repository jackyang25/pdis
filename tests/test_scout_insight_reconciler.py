"""Semantic duplicate grouping for extracted insights.

Extraction creates objects; this layer decides which of those objects are the
same fact. It may only partition existing insight IDs and pick a representative.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.scout.models import Insight
from services.scout.stages.insight_extractor import merge_duplicate_insights
from services.scout.stages.insight_reconciler import reconcile_duplicate_insights
from services.searcher import Finding


def _finding(url: str) -> Finding:
    return Finding(
        url=url,
        title=url,
        query="efficacy",
        retrieved_at=datetime.now(timezone.utc),
        excerpt="A source record states the result.",
        source="pubmed",
    )


def _insight(statement: str, url: str, attribute_ref: str = "efficacy") -> Insight:
    return Insight(
        statement=statement,
        supporting_findings=[_finding(url)],
        attribute_ref=attribute_ref,
    )


class _GroupingClient:
    """Group by a supplied mapping of representative id to member ids."""

    def __init__(self, groups: list[tuple[int, list[int]]]) -> None:
        self.groups = groups
        self.requested_ids: list[list[str]] = []

    def call_structured(self, _system, _message, *_args, **kwargs):
        allowed = list(
            kwargs["schema"]["properties"]["groups"]["items"]["properties"]
            ["representative_insight_id"]["enum"]
        )
        self.requested_ids.append(allowed)
        return {"groups": [
            {
                "representative_insight_id": allowed[representative],
                "member_insight_ids": [allowed[member] for member in members],
                "reason": "The same fact stated in different words.",
            }
            for representative, members in self.groups
        ]}


class _FailingClient:
    def call_structured(self, *_args, **_kwargs):
        raise RuntimeError("provider unavailable")


class InsightReconcilerTests(unittest.TestCase):
    def test_paraphrases_of_one_fact_become_one_insight_citing_both_sources(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy among children.",
                     "https://example.test/b"),
        ]
        client = _GroupingClient([(0, [0, 1])])

        reconciled = reconcile_duplicate_insights(insights, client)

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0].statement, insights[0].statement)
        self.assertEqual(
            [finding.url for finding in reconciled[0].supporting_findings],
            ["https://example.test/a", "https://example.test/b"],
        )

    def test_distinct_facts_are_preserved_as_singleton_groups(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("Two doses are given four weeks apart.", "https://example.test/b"),
        ]
        client = _GroupingClient([(0, [0]), (1, [1])])

        reconciled = reconcile_duplicate_insights(insights, client)

        self.assertEqual(
            [item.statement for item in reconciled],
            [item.statement for item in insights],
        )

    def test_insights_for_different_fields_are_never_compared(self) -> None:
        insights = [
            _insight("Efficacy was 74%.", "https://example.test/a", "efficacy"),
            _insight("Efficacy was 74%.", "https://example.test/b", "safety"),
        ]
        client = _GroupingClient([(0, [0])])

        reconciled = reconcile_duplicate_insights(insights, client)

        self.assertEqual(len(reconciled), 2)
        self.assertEqual(client.requested_ids, [])

    def test_a_provider_failure_retains_every_insight(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy in children.",
                     "https://example.test/b"),
        ]

        reconciled = reconcile_duplicate_insights(insights, _FailingClient())

        self.assertEqual(len(reconciled), 2)

    def test_an_incomplete_partition_is_rejected_and_changes_nothing(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy in children.",
                     "https://example.test/b"),
        ]
        # Omits the second ID, so the response is not a partition.
        client = _GroupingClient([(0, [0])])

        reconciled = reconcile_duplicate_insights(insights, client)

        self.assertEqual(len(reconciled), 2)

    def test_one_field_is_reconciled_per_request(self) -> None:
        insights = [
            _insight("A.", "https://example.test/a", "efficacy"),
            _insight("B.", "https://example.test/b", "efficacy"),
            _insight("C.", "https://example.test/c", "safety"),
            _insight("D.", "https://example.test/d", "safety"),
        ]
        client = _GroupingClient([(0, [0]), (1, [1])])

        reconcile_duplicate_insights(insights, client)

        self.assertEqual([len(batch) for batch in client.requested_ids], [2, 2])


class DeterministicIdentityTests(unittest.TestCase):
    """The deterministic pass decides identity only; paraphrase is the AI layer's."""

    def test_the_same_statement_respaced_is_one_insight(self) -> None:
        merged = merge_duplicate_insights([
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("Efficacy   was 74% in\nchildren.", "https://example.test/b"),
        ])

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            [finding.url for finding in merged[0].supporting_findings],
            ["https://example.test/a", "https://example.test/b"],
        )

    def test_statements_differing_by_punctuation_are_left_to_the_ai_layer(self) -> None:
        merged = merge_duplicate_insights([
            _insight("Efficacy was 80% in adults.", "https://example.test/a"),
            _insight("Efficacy was 80 in adults.", "https://example.test/b"),
        ])

        self.assertEqual(len(merged), 2)

    def test_the_same_statement_for_different_fields_stays_separate(self) -> None:
        merged = merge_duplicate_insights([
            _insight("Efficacy was 74%.", "https://example.test/a", "efficacy"),
            _insight("Efficacy was 74%.", "https://example.test/b", "safety"),
        ])

        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
