from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.contract import validate_result_contract
from services.inspector.models import (
    DIMENSIONS,
    DimensionGrade,
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
            "missing_variables": [],
            "variable_grades": [
                {
                    "variable_name": "Efficacy",
                    "block_ids": ["document:b1"],
                    "grade": "A",
                    "issues": [],
                    "recommendation": "",
                    "content_status": "substantive",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "accounted for exactly once"):
            _parse_dimension_payload(payload, "completeness", section, blocks)

    def test_missing_variable_remains_in_the_rollup_ledger(self) -> None:
        section = config().sections[0]
        present = {
            "variable_name": "Efficacy",
            "block_ids": ["document:b1"],
            "grade": "A",
            "issues": [],
            "recommendation": "",
        }
        missing = {
            "variable_name": "Safety",
            "block_ids": [],
            "grade": "N/A",
            "issues": [],
            "recommendation": "",
        }
        merged = _merge_variable_bearing(
            section,
            {
                "completeness": {
                    "missing_variables": ["Safety"],
                    "variable_grades": [present],
                },
                "adherence": {"missing_variables": [], "variable_grades": [present, missing]},
                "rigor": {"missing_variables": [], "variable_grades": [present, missing]},
            },
        )
        self.assertEqual([item.variable_name for item in merged.variable_grades], ["Efficacy", "Safety"])
        safety = merged.variable_grades[1]
        self.assertEqual(safety.dimensions["completeness"].grade, "F")
        self.assertEqual(safety.dimensions["adherence"].grade, "F")
        self.assertEqual(safety.dimensions["rigor"].grade, "N/A")

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
            dimensions={name: DimensionGrade("A") for name in DIMENSIONS},
            section_grades=[],
            grading_status="complete",
        )
        with self.assertRaisesRegex(ValueError, "section ledger"):
            validate_result_contract(result, [block("document:b1", "Profile")], cfg)


if __name__ == "__main__":
    unittest.main()
