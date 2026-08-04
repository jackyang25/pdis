from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.contract import validate_result_contract
from services.inspector.models import (
    InspectionConfig,
    InspectionResult,
    SectionSpec,
    VariableSpec,
)
from services.inspector.stages.grader import (
    _merge_variable_bearing,
    _parse_cross_section_payload,
    _parse_dimension_payload,
    _cross_section_user_message,
)


def block(block_id: str, section: str) -> ContentBlock:
    return ContentBlock(
        id=block_id,
        doc_id="document",
        ordinal=int(block_id.rsplit("b", 1)[-1]),
        block_type="paragraph",
        content=f"Content for {section}",
        heading_stack=[],
        structural_meta={},
        style_hint={},
        section_label=section,
    )


def config() -> InspectionConfig:
    return InspectionConfig(
        type_key="test",
        org="org",
        source_type="itpp",
        intervention_class="vaccine",
        display_name="Test",
        sections=[
            SectionSpec(
                name="Profile",
                description="Profile targets",
                weight=1,
                variables=[
                    VariableSpec(name="Efficacy", description="Efficacy target"),
                    VariableSpec(name="Safety", description="Safety target"),
                ],
            )
        ],
    )


class InspectorContractTests(unittest.TestCase):
    def test_dimension_response_must_account_for_the_entire_rubric(self) -> None:
        section = config().sections[0]
        blocks = [block("document:b1", "Profile")]
        payload = {
            "variable_grades": [
                {
                    "variable_name": "Efficacy",
                    "block_ids": ["document:b1"],
                    "verdict": "meets",
                    "issues": [],
                    "recommendation": "",
                    "content_status": "substantive",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "accounted for exactly once"):
            _parse_dimension_payload(payload, "completeness", section, blocks)

    def test_content_status_is_the_only_record_of_absence(self) -> None:
        """Absence has one representation, carried by the variable it describes.

        It was previously recorded twice - once as a `content_status` and again in
        a parallel list of names - so the two could disagree. The parser requires
        every rubric variable in `variable_grades`, so the name list said nothing
        the status did not.
        """
        section = config().sections[0]
        present = {
            "variable_name": "Efficacy",
            "block_ids": ["document:b1"],
            "verdict": "meets",
            "issues": [],
            "recommendation": "",
            "content_status": "substantive",
        }
        absent = {
            "variable_name": "Safety",
            "block_ids": [],
            "verdict": "not_applicable",
            "issues": [],
            "recommendation": "",
            "content_status": "missing",
        }
        merged = _merge_variable_bearing(
            section,
            {
                "completeness": {"variable_grades": [present, absent]},
                "adherence": {"variable_grades": [present, absent]},
                "rigor": {"variable_grades": [present, absent]},
            },
        )

        self.assertEqual(
            [item.variable_name for item in merged.variable_grades],
            ["Efficacy", "Safety"],
        )
        safety = merged.variable_grades[1]
        self.assertEqual(safety.content_status, "missing")
        self.assertEqual(safety.dimensions["completeness"].verdict, "critical")
        self.assertEqual(safety.dimensions["adherence"].verdict, "critical")
        self.assertEqual(safety.dimensions["rigor"].verdict, "not_applicable")
        self.assertEqual(merged.missing_variables, ["Safety"])
        for dimension in ("completeness", "adherence", "rigor"):
            self.assertEqual(safety.dimensions[dimension].cited_block_ids, [])

    def test_each_dimension_keeps_its_own_lineage(self) -> None:
        """Independent judgments cite independently, so lineage is per dimension."""
        section = config().sections[0]

        def item(name: str, blocks: list[str], status: str) -> dict:
            return {
                "variable_name": name,
                "block_ids": blocks,
                "verdict": "for_consideration",
                "issues": [],
                "recommendation": "",
                "content_status": status,
            }

        merged = _merge_variable_bearing(
            section,
            {
                "completeness": {
                    "variable_grades": [
                        item("Efficacy", ["document:b1"], "substantive"),
                        item("Safety", ["document:b1"], "substantive"),
                    ]
                },
                "adherence": {
                    "variable_grades": [
                        item("Efficacy", [], "substantive"),
                        item("Safety", ["document:b1"], "substantive"),
                    ]
                },
                "rigor": {
                    "variable_grades": [
                        item("Efficacy", ["document:b1"], "substantive"),
                        item("Safety", [], "substantive"),
                    ]
                },
            },
        )

        efficacy = merged.variable_grades[0]
        self.assertEqual(efficacy.dimensions["completeness"].cited_block_ids, ["document:b1"])
        self.assertEqual(efficacy.dimensions["adherence"].cited_block_ids, [])
        self.assertEqual(efficacy.dimensions["rigor"].cited_block_ids, ["document:b1"])
        # The variable-level view is the union, derived so it cannot disagree.
        self.assertEqual(efficacy.cited_block_ids, ["document:b1"])

    def test_cross_section_findings_require_a_block_from_each_section(self) -> None:
        blocks_by_section = {
            "Profile": [block("document:b1", "Profile")],
            "Plan": [block("document:b2", "Plan")],
        }
        invalid = {
            "findings": [
                {
                    "description": "Values conflict.",
                    "sections": ["Profile", "Plan"],
                    "recommendation": "Reconcile values.",
                    "block_ids": ["document:b1"],
                }
            ],
        }
        self.assertIsNone(_parse_cross_section_payload(invalid, blocks_by_section))

    def test_bounded_consistency_context_is_reported_as_partial(self) -> None:
        first = block("document:b1", "Profile")
        second = block("document:b2", "Profile")
        third = block("document:b3", "Plan")
        fourth = block("document:b4", "Plan")
        for item, value in zip((first, second, third, fourth), "ABCD"):
            item.content = value * 40000
        _message, selected, limited = _cross_section_user_message(
            {"Profile": [first, second], "Plan": [third, fourth]}
        )
        self.assertTrue(limited)
        self.assertEqual(set(selected), {"Profile", "Plan"})

    def test_final_contract_rejects_a_missing_rubric_variable(self) -> None:
        cfg = config()
        result = InspectionResult(
            doc_id="document",
            section_grades=[],
            grading_status="complete",
            blocks=[block("document:b1", "Profile")],
        )
        with self.assertRaisesRegex(ValueError, "section ledger"):
            validate_result_contract(result, cfg)


if __name__ == "__main__":
    unittest.main()
