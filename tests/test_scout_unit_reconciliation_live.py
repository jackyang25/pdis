"""Opt-in sampled semantic checks; no retrieval or real document uploads.

RUN_SCOUT_SEMANTIC_EVAL=1 python -m unittest tests.test_scout_unit_reconciliation_live
Requires configured model credentials and incurs model usage. Passing fixtures
do not guarantee semantic accuracy on all documents.
"""

import os
import unittest

from services.scout.models import Attribute, DocumentSpan
from services.scout.stages.unit_reconciler import reconcile_units
from shared.openai_client import OpenAIClient


def claim(name, description, quote, block_id):
    return Attribute(name, description, document_spans=[DocumentSpan(quote, [block_id])],
                     definition_mode="dynamic", target_resolved=True, evidence_domain="regulatory")


@unittest.skipUnless(os.environ.get("RUN_SCOUT_SEMANTIC_EVAL") == "1", "opt-in live model evaluation")
class UnitReconciliationLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = OpenAIClient()

    def test_equivalent_restatements_merge_without_merging_distinct_qualifiers(self):
        units = [
            claim("filing", "Timing of Product A regulatory submission.",
                  "Product A regulatory submission is planned for 2030.", "doc/b1"),
            claim("submission", "Planned filing schedule for Product A.",
                  "The sponsor plans to file Product A's regulatory submission in 2030.", "doc/b2"),
            claim("approval", "Timing of Product A approval.",
                  "Product A regulatory approval is expected in 2030.", "doc/b3"),
            claim("later_filing", "Timing of Product A regulatory submission.",
                  "Product A regulatory submission is planned for 2031.", "doc/b4"),
            claim("achieved", "Completed Product A regulatory submission.",
                  "Product A regulatory submission was completed in 2030.", "doc/b5"),
            claim("other_product", "Timing of Product B regulatory submission.",
                  "Product B regulatory submission is planned for 2030.", "doc/b6"),
        ]
        result = reconcile_units(units, self.client)
        self.assertEqual({frozenset(u.block_ids) for u in result}, {
            frozenset({"doc/b1", "doc/b2"}), frozenset({"doc/b3"}),
            frozenset({"doc/b4"}), frozenset({"doc/b5"}), frozenset({"doc/b6"}),
        })

    def test_shared_passage_does_not_erase_distinct_evaluation_scopes(self):
        passage = "Product A submission is planned in 2030; its approval is expected in 2031."
        result = reconcile_units([
            claim("submission", "Timing of Product A submission.", passage, "doc/b1"),
            claim("approval", "Timing of Product A approval.", passage, "doc/b1"),
        ], self.client)
        self.assertEqual([u.name for u in result], ["submission", "approval"])

    def test_partial_overlap_uncertainty_and_population_differences_stay_separate(self):
        cases = [
            ("broad", "Protective efficacy target.", "The vaccine efficacy target is at least 70%."),
            ("infants", "Protective efficacy target in infants.",
             "The vaccine efficacy target in infants is at least 70%."),
            ("adults", "Protective efficacy target in adults.",
             "The vaccine efficacy target in adults is at least 70%."),
            ("optimistic", "Optimistic efficacy target in infants.",
             "The optimistic vaccine efficacy target in infants is at least 90%."),
            ("storage", "Required storage temperature.", "Store at 2–8°C."),
            ("storage_and_life", "Storage temperature and shelf life.",
             "Store at 2–8°C with a shelf life of at least 12 months."),
            ("not_approved", "Product A approval status in 2030.",
             "Product A was not approved in 2030."),
            ("approved", "Product A approval status in 2030.", "Product A was approved in 2030."),
        ]
        units = [claim(name, description, quote, f"doc/b{i}")
                 for i, (name, description, quote) in enumerate(cases)]
        result = reconcile_units(units, self.client)
        self.assertEqual([u.name for u in result], [case[0] for case in cases])


if __name__ == "__main__":
    unittest.main()
