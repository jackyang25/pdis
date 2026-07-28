from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.models import SectionSpec, VariableSpec
from services.inspector.stages.grader import (
    _cross_section_schema,
    _dimension_schema,
    _grade_section,
)


def _block() -> ContentBlock:
    return ContentBlock(
        id="document:b1",
        doc_id="document",
        ordinal=1,
        block_type="paragraph",
        content="Efficacy is stated; the safety target is absent.",
        heading_stack=[],
        structural_meta={},
        style_hint={},
        section_label="Profile",
    )


def _section() -> SectionSpec:
    return SectionSpec(
        name="Profile",
        description="Product targets",
        weight=1,
        variables=[
            VariableSpec(name="Efficacy", description="Efficacy target"),
            VariableSpec(name="Safety", description="Safety target"),
        ],
    )


class _StructuredClient:
    def call_structured(self, _system, _message, *_args, schema, **_kwargs):
        item = schema["properties"]["variable_grades"]["items"]
        names = item["properties"]["variable_name"]["enum"]
        completeness = "content_status" in item["properties"]
        grades = []
        for name in names:
            missing = name == "Safety"
            value = {
                "variable_name": name,
                "block_ids": [] if missing else ["document:b1"],
                "grade": "N/A" if missing else "A",
                "issues": [],
                "recommendation": "",
            }
            if completeness:
                value["content_status"] = "missing" if missing else "substantive"
            grades.append(value)
        return {"variable_grades": grades}


class _EmptyStructuredClient:
    def call_structured(self, *_args, **_kwargs):
        return None


class _AbsentVariableClient:
    """Models independent dimensions before completeness owns absence."""

    def call_structured(self, _system, _message, *_args, schema, schema_name, **_kwargs):
        item = schema["properties"]["variable_grades"]["items"]
        names = item["properties"]["variable_name"]["enum"]
        completeness = schema_name == "inspector_completeness_grade"
        grades = []
        for name in names:
            missing = name == "Safety"
            value = {
                "variable_name": name,
                "block_ids": [] if missing else ["document:b1"],
                # Adherence may penalize absence before completeness establishes it.
                "grade": "F" if missing else "A",
                "issues": [],
                "recommendation": "",
            }
            if completeness:
                value["content_status"] = "missing" if missing else "substantive"
            grades.append(value)
        return {"variable_grades": grades}


class InspectorStructuredGradingTests(unittest.TestCase):
    def test_openai_wire_schemas_do_not_use_unsupported_unique_items(self) -> None:
        dimension_schema = _dimension_schema("completeness", _section(), [_block()])
        block_ids = dimension_schema["properties"]["variable_grades"]["items"][
            "properties"
        ]["block_ids"]
        self.assertNotIn("uniqueItems", block_ids)

        cross_section_schema = _cross_section_schema(
            {"Profile": [_block()], "Other": []}
        )
        finding = cross_section_schema["properties"]["findings"]["items"]
        self.assertNotIn("uniqueItems", finding["properties"]["sections"])
        self.assertNotIn("uniqueItems", finding["properties"]["block_ids"])

    def test_missing_variable_has_one_authoritative_cross_dimension_outcome(self) -> None:
        result = _grade_section(
            section_spec=_section(),
            section_blocks=[_block()],
            llm_client=_StructuredClient(),
            max_tokens=4000,
        )
        self.assertEqual(result.missing_variables, ["Safety"])
        safety = result.variable_grades[1]
        self.assertEqual(safety.dimensions["completeness"].grade, "F")
        self.assertEqual(safety.dimensions["adherence"].grade, "F")
        self.assertEqual(safety.dimensions["rigor"].grade, "N/A")

    def test_absent_variable_does_not_require_impossible_adherence_lineage(self) -> None:
        result = _grade_section(
            section_spec=_section(),
            section_blocks=[_block()],
            llm_client=_AbsentVariableClient(),
            max_tokens=4000,
        )
        safety = result.variable_grades[1]
        self.assertEqual(result.missing_variables, ["Safety"])
        self.assertEqual(safety.block_ids, [])
        self.assertEqual(safety.dimensions["completeness"].grade, "F")
        self.assertEqual(safety.dimensions["adherence"].grade, "F")
        self.assertEqual(safety.dimensions["rigor"].grade, "N/A")

    def test_failed_core_batch_raises_instead_of_emitting_na_fallbacks(self) -> None:
        with self.assertRaisesRegex(ValueError, "could not complete completeness grading"):
            _grade_section(
                section_spec=_section(),
                section_blocks=[_block()],
                llm_client=_EmptyStructuredClient(),
                max_tokens=4000,
            )


if __name__ == "__main__":
    unittest.main()
