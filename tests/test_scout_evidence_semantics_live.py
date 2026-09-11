"""Opt-in semantic regression checks using real, server-configured model clients.

RUN_SCOUT_SEMANTIC_EVAL=1 python -m unittest tests.test_scout_evidence_semantics_live

Requires model credentials in the environment and incurs model usage. Synthetic
sources are supplied directly: no document upload or web search is performed.
These tests measure sampled behavior, not a guarantee of model correctness.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import unittest

from services.scout import find_config
from services.scout.models import Insight
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.insight_extractor import extract_insights
from services.searcher import Finding
from shared.openai_client import OpenAIClient


@unittest.skipUnless(
    os.environ.get("RUN_SCOUT_SEMANTIC_EVAL") == "1",
    "opt-in live model evaluation",
)
class ScoutEvidenceSemanticsLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = OpenAIClient()

    def test_search_silence_is_not_a_document_conflict(self):
        self._check_relations([
            (
                "search_silence",
                "Product A approval is expected in 2027.",
                "The retrieved findings do not state any expected approval timing for Product A.",
                "unrelated",
            ),
        ])

    def test_source_owned_facts_keep_their_relationship(self):
        self._check_relations([
            (
                "explicit_delay",
                "Product A approval is expected in 2027.",
                "The regulator announced Product A cannot be approved before 2029.",
                "contradicts",
            ),
            (
                "explicit_support",
                "Product A was approved in 2025.",
                "The regulator confirms that Product A was approved in 2025.",
                "confirms",
            ),
            (
                "not_yet_is_not_never",
                "Product A approval is expected by December 2027.",
                "As of January 2027, Product A remains under regulatory review.",
                "extends",
            ),
            (
                "context_plus_search_silence",
                "Product A approval is expected in 2027.",
                "The regulator requires a manufacturing inspection before approval; "
                "the retrieved findings do not state Product A's approval date.",
                "extends",
            ),
            (
                "source_owned_negative",
                "Product A received regulatory approval in 2025.",
                "The regulator explicitly states that Product A did not receive "
                "regulatory approval in 2025.",
                "contradicts",
            ),
        ])

    def _check_relations(self, cases):
        # Each case still makes its own production request. Fan-out changes
        # latency, never which other cases the model sees.
        tasks = [(doc_type, case) for doc_type in ("itpp", "ctpp", "ipdp") for case in cases]

        def run(task):
            doc_type, (name, claim, statement, expected) = task
            matches = classify_drift(
                [f"[block:synthetic/b-0001]\n{claim}"],
                [Insight(id=name, statement=statement, attribute_ref="regulatory_approval")],
                self.client,
                indication="respiratory syncytial virus",
                intervention_class="vaccine",
                framing=find_config("bmgf", doc_type, "vaccine").drift_framing,
            )
            return doc_type, name, expected, matches

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(run, tasks))
        for doc_type, name, expected, matches in results:
            with self.subTest(source_type=doc_type, case=name):
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].relation, expected, matches[0].reason)

    def test_extraction_separates_search_silence_from_source_owned_negative(self):
        for name, excerpt, expected_count in [
            (
                "search_silence",
                "No matching approval timing for Product A was found in the retrieved snippets.",
                0,
            ),
            (
                "unrelated_snippet_despite_query",
                "The regional office held a general public-health workshop in 2025.",
                0,
            ),
            (
                "source_owned_negative",
                "The regulator explicitly states that Product A did not receive "
                "regulatory approval in 2025.",
                1,
            ),
        ]:
            with self.subTest(case=name):
                finding = Finding(
                    url=f"https://example.org/{name}",
                    title="Synthetic retrieval result",
                    query="Product A regulatory approval timing",
                    retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    excerpt=excerpt,
                )
                insights = extract_insights(
                    [finding], self.client,
                    indication="respiratory syncytial virus",
                    intervention_class="vaccine",
                    attribute_ref="regulatory_approval",
                    attribute_description="The timing and status of regulatory approval.",
                )
                self.assertEqual(len(insights), expected_count, [i.statement for i in insights])
                if insights:
                    self.assertEqual(insights[0].supporting_findings, [finding])
