"""Rehydrating a review draft is Scout's contract, not the transport's.

The rules enforced here — which phase may continue, that a draft carries no
downstream judgments, and that a field cannot reference an unknown target — are
structural integrity rules. They belong beside the rest of Scout's contract so
one caller cannot skip them and a second caller need not copy them.
"""

from __future__ import annotations

import unittest

from services.scout import result_from_target_review


def _draft() -> dict:
    return {
        "phase": "target_review",
        "search_plan": [],
        "matches": [],
        "assessments": [],
        "conformity": [],
        "precedents": [],
        "development_landscape": [],
        "safety_observations": [],
        "stats": {
            "queries": 0,
            "findings": 0,
            "unique_findings": 0,
            "insights": 0,
            "matches": 0,
            "assessments": 0,
        },
        "context_validation": {
            "status": "match",
            "configured_indication": "malaria",
            "document_indication": "malaria",
            "reason": "The document concerns the configured indication.",
            "doc_block_ids": [],
        },
        "quantitative_ledger": {
            "status": "not_applicable",
            "reason": "No numeric target was stated.",
            "block_ids": [],
            "reviews": [],
            "targets": [],
        },
        "variables": [{
            "name": "efficacy",
            "description": "Protective efficacy",
            "block_ids": ["document/b-0001"],
            "document_target": "at least 80% efficacy",
            "document_spans": [{
                "quote": "at least 80% efficacy",
                "block_ids": ["document/b-0001"],
            }],
            "definition_mode": "fixed",
            "target_resolved": True,
            "target_resolution_reason": "Resolved from an exact span.",
            "evidence_domain": "clinical",
            "entities": [],
            "quantitative_target_ids": [],
            "quantitative_statement_dispositions": [],
            "quantitative_target_status": "not_applicable",
            "quantitative_target_status_reason": "No numeric target was stated.",
        }],
        "blocks": [{
            "id": "document/b-0001",
            "doc_id": "document",
            "ordinal": 1,
            "block_type": "paragraph",
            "content": "Target: at least 80% efficacy.",
            "heading_stack": [],
            "structural_meta": {},
            "style_hint": {},
            "section_label": None,
            "image": None,
        }],
    }


class DraftRehydrationTests(unittest.TestCase):
    def test_a_review_draft_rehydrates_into_the_pre_retrieval_contract(self) -> None:
        result = result_from_target_review(_draft())

        self.assertEqual(result.phase, "target_review")
        self.assertEqual([variable.name for variable in result.variables], ["efficacy"])
        self.assertEqual([block.id for block in result.blocks], ["document/b-0001"])
        self.assertEqual(result.matches, [])
        self.assertEqual(result.assessments, [])

    def test_only_a_target_review_draft_may_continue(self) -> None:
        draft = _draft()
        draft["phase"] = "complete"

        with self.assertRaises(ValueError):
            result_from_target_review(draft)

    def test_a_draft_carrying_downstream_results_is_refused(self) -> None:
        draft = _draft()
        draft["matches"] = [{"anything": "here"}]

        with self.assertRaises(ValueError):
            result_from_target_review(draft)

    def test_a_field_cannot_reference_a_target_the_draft_does_not_carry(self) -> None:
        draft = _draft()
        draft["variables"][0]["quantitative_target_ids"] = ["qt-unknown"]

        result = result_from_target_review(draft)

        self.assertEqual(result.variables[0].quantitative_target_ids, [])


if __name__ == "__main__":
    unittest.main()
