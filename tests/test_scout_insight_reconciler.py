"""Semantic duplicate grouping for extracted insights.

Extraction creates objects; this layer decides which of those objects are the
same fact. It may only partition existing insight IDs and pick a representative.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import httpx
import openai

from services.scout.models import Insight
from services.scout.stages.insight_reconciler import reconcile_duplicate_insights
from services.searcher import Finding


def reconcile(insights, client):
    return reconcile_duplicate_insights(insights, client)[0]


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
            }
            for representative, members in self.groups
        ]}


class _FailingClient:
    def call_structured(self, *_args, **_kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://provider.test"))


class InsightReconcilerTests(unittest.TestCase):
    def test_paraphrases_of_one_fact_become_one_insight_citing_both_sources(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy among children.",
                     "https://example.test/b"),
        ]
        client = _GroupingClient([(0, [0, 1])])

        reconciled = reconcile(insights, client)

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0].statement, insights[0].statement)
        self.assertEqual(
            [finding.url for finding in reconciled[0].supporting_findings],
            ["https://example.test/a", "https://example.test/b"],
        )

    def test_a_merged_representative_keeps_its_place_and_a_current_id(self) -> None:
        insights = [
            _insight("The vaccine showed 74 percent efficacy among children.",
                     "https://example.test/b"),
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
        ]
        client = _GroupingClient([(1, [0, 1])])

        reconciled = reconcile(insights, client)

        self.assertEqual([item.statement for item in reconciled], [insights[1].statement])
        expected = Insight(
            statement=insights[1].statement,
            supporting_findings=list(reconciled[0].supporting_findings),
            attribute_ref="efficacy",
        )
        self.assertEqual(reconciled[0].id, expected.id)

    def test_an_invalid_partition_is_retried_once(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy in children.",
                     "https://example.test/b"),
        ]

        class InvalidThenValid(_GroupingClient):
            def call_structured(self, *args, **kwargs):
                self.groups = [(0, [0])] if not self.requested_ids else [(0, [0, 1])]
                return super().call_structured(*args, **kwargs)

        client = InvalidThenValid([])
        reconciled = reconcile(insights, client)

        self.assertEqual(len(client.requested_ids), 2)
        self.assertEqual(len(reconciled), 1)

    def test_distinct_facts_are_preserved_as_singleton_groups(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("Two doses are given four weeks apart.", "https://example.test/b"),
        ]
        client = _GroupingClient([(0, [0]), (1, [1])])

        reconciled = reconcile(insights, client)

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

        reconciled = reconcile(insights, client)

        self.assertEqual(len(reconciled), 2)
        self.assertEqual(client.requested_ids, [])

    def test_a_provider_failure_retains_every_insight_and_is_recorded(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy in children.",
                     "https://example.test/b"),
        ]

        reconciled, [record] = reconcile_duplicate_insights(insights, _FailingClient())

        self.assertEqual(len(reconciled), 2)
        self.assertEqual(
            (record.layer, record.scope, record.status, record.failure_code),
            ("insights", "efficacy", "not_reconciled", "provider_error"),
        )

    def test_an_incomplete_partition_is_rejected_and_changes_nothing(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("The vaccine showed 74 percent efficacy in children.",
                     "https://example.test/b"),
        ]
        # Omits the second ID, so the response is not a partition.
        client = _GroupingClient([(0, [0])])

        reconciled, [record] = reconcile_duplicate_insights(insights, client)

        self.assertEqual(len(reconciled), 2)
        self.assertEqual(len(client.requested_ids), 2)
        self.assertEqual((record.status, record.failure_code), ("not_reconciled", "invalid_model_response"))

    def test_one_field_is_reconciled_per_request(self) -> None:
        insights = [
            _insight("A.", "https://example.test/a", "efficacy"),
            _insight("B.", "https://example.test/b", "efficacy"),
            _insight("C.", "https://example.test/c", "safety"),
            _insight("D.", "https://example.test/d", "safety"),
        ]
        client = _GroupingClient([(0, [0]), (1, [1])])

        reconcile(insights, client)

        self.assertEqual([len(batch) for batch in client.requested_ids], [2, 2])


class NoDeterministicIdentityTests(unittest.TestCase):
    """Identity is the model layer's alone: nothing is merged for reading alike."""

    def test_the_same_statement_respaced_is_sent_to_the_identity_layer(self) -> None:
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("Efficacy   was 74% in\nchildren.", "https://example.test/b"),
        ]
        client = _GroupingClient([(0, [0, 1])])

        reconciled = reconcile(insights, client)

        self.assertEqual([len(batch) for batch in client.requested_ids], [2])
        self.assertEqual(len(reconciled), 1)

    def test_identical_insights_kept_apart_get_distinct_ids(self) -> None:
        """One statement from one record twice derives one ID; both must survive."""
        insights = [
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
            _insight("Efficacy was 74% in children.", "https://example.test/a"),
        ]
        self.assertEqual(insights[0].id, insights[1].id)

        reconciled = reconcile(insights, _GroupingClient([(0, [0]), (1, [1])]))

        self.assertEqual(len(reconciled), 2)
        self.assertNotEqual(reconciled[0].id, reconciled[1].id)


if __name__ == "__main__":
    unittest.main()
