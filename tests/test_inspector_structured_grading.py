from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.models import InspectionConfig, SectionSpec, VariableSpec
from services.inspector.stages.grader import (
    _cross_section_schema,
    _dimension_schema,
    _grade_section,
    _variable_batches,
    check_cross_section,
)


def _labeled_block(block_id: str, ordinal: int, section_label: str) -> ContentBlock:
    return ContentBlock(
        id=block_id,
        doc_id="document",
        ordinal=ordinal,
        block_type="paragraph",
        content=f"Content filed under {section_label}.",
        heading_stack=[],
        structural_meta={},
        style_hint={},
        section_label=section_label,
    )


class _RecordingCrossSectionClient:
    """Captures the closed vocabulary the consistency pass offers the model."""

    def __init__(self) -> None:
        self.section_names: list[str] | None = None
        self.block_ids: list[str] | None = None

    def call_structured(self, _system, _message, *_args, schema, **_kwargs):
        finding = schema["properties"]["findings"]["items"]["properties"]
        self.section_names = finding["sections"]["items"]["enum"]
        self.block_ids = finding["block_ids"]["items"]["enum"]
        return {"findings": []}


class _OutOfRubricCrossSectionClient:
    """A model that names a section outside the rubric despite the schema."""

    def call_structured(self, _system, _message, *_args, schema, **_kwargs):
        return {
            "findings": [
                {
                    "description": "The metadata stamp disagrees with the profile.",
                    "sections": ["Profile", "Other"],
                    "recommendation": "Reconcile them.",
                    "block_ids": ["document:b1"],
                }
            ]
        }


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
                "verdict": "not_applicable" if missing else "meets",
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
        completeness = schema_name == "inspector_completeness_verdict"
        grades = []
        for name in names:
            missing = name == "Safety"
            value = {
                "variable_name": name,
                "block_ids": [] if missing else ["document:b1"],
                # Adherence may penalize absence before completeness establishes it.
                "verdict": "critical" if missing else "meets",
                "issues": [],
                "recommendation": "",
            }
            if completeness:
                value["content_status"] = "missing" if missing else "substantive"
            grades.append(value)
        return {"variable_grades": grades}


class VariableRequestScopeTests(unittest.TestCase):
    def test_each_rubric_variable_is_graded_in_its_own_request(self) -> None:
        """One grade per variable, so an unrelated variable cannot sway it."""
        variables = [
            VariableSpec(name=f"V{index}", description=f"Variable {index}")
            for index in range(3)
        ]

        batches = _variable_batches(variables)

        self.assertEqual(
            [[variable.name for variable in batch] for batch in batches],
            [["V0"], ["V1"], ["V2"]],
        )

    def test_a_section_without_variables_still_yields_one_request(self) -> None:
        self.assertEqual(_variable_batches([]), [[]])


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
        self.assertEqual(safety.dimensions["completeness"].verdict, "critical")
        self.assertEqual(safety.dimensions["adherence"].verdict, "critical")
        self.assertEqual(safety.dimensions["rigor"].verdict, "not_applicable")

    def test_absent_variable_does_not_require_impossible_adherence_lineage(self) -> None:
        result = _grade_section(
            section_spec=_section(),
            section_blocks=[_block()],
            llm_client=_AbsentVariableClient(),
            max_tokens=4000,
        )
        safety = result.variable_grades[1]
        self.assertEqual(result.missing_variables, ["Safety"])
        self.assertEqual(safety.content_status, "missing")
        # Absence is the one claim that cannot carry lineage, on any axis.
        self.assertEqual(safety.cited_block_ids, [])
        for dimension in ("completeness", "adherence", "rigor"):
            self.assertEqual(safety.dimensions[dimension].cited_block_ids, [])
        self.assertEqual(safety.dimensions["completeness"].verdict, "critical")
        self.assertEqual(safety.dimensions["adherence"].verdict, "critical")
        self.assertEqual(safety.dimensions["rigor"].verdict, "not_applicable")

    def test_failed_core_batch_raises_instead_of_emitting_na_fallbacks(self) -> None:
        with self.assertRaisesRegex(ValueError, "could not complete completeness grading"):
            _grade_section(
                section_spec=_section(),
                section_blocks=[_block()],
                llm_client=_EmptyStructuredClient(),
                max_tokens=4000,
            )


class CrossSectionScopeTests(unittest.TestCase):
    """The consistency pass may only name sections the rubric defines.

    Chunker labels blocks with its own taxonomy, which appends "Document
    Metadata" and "Other". Offering those to the model produces findings that
    `validate_result_contract` rejects, and the raise discards a fully graded
    document over a pass that is only additive.
    """

    def _config(self) -> InspectionConfig:
        return InspectionConfig(
            type_key="test_itpp_vaccine",
            org="test",
            source_type="itpp",
            intervention_class="vaccine",
            display_name="Test",
            sections=[
                SectionSpec(name="Profile", description="Targets", weight=1, variables=[]),
                SectionSpec(name="Timeline", description="Dates", weight=1, variables=[]),
            ],
        )

    def _labeled_blocks(self) -> list[ContentBlock]:
        return [
            _labeled_block("document:b1", 1, "Profile"),
            _labeled_block("document:b2", 2, "Timeline"),
            _labeled_block("document:b3", 3, "Other"),
            _labeled_block("document:b4", 4, "Document Metadata"),
        ]

    def test_only_rubric_sections_are_offered_to_the_model(self) -> None:
        client = _RecordingCrossSectionClient()
        check_cross_section(
            self._labeled_blocks(), self._config(), client, max_tokens=4000
        )
        self.assertEqual(client.section_names, ["Profile", "Timeline"])
        self.assertEqual(
            client.block_ids,
            ["document:b1", "document:b2"],
            "a block labelled outside the rubric is not citable evidence here",
        )

    def test_a_document_with_one_rubric_section_is_not_applicable(self) -> None:
        # "Other" and "Document Metadata" are not a second section to conflict
        # with, so counting them would run a pass that cannot produce a finding.
        blocks = [
            _labeled_block("document:b1", 1, "Profile"),
            _labeled_block("document:b3", 3, "Other"),
            _labeled_block("document:b4", 4, "Document Metadata"),
        ]
        client = _RecordingCrossSectionClient()
        findings, status = check_cross_section(
            blocks, self._config(), client, max_tokens=4000
        )
        self.assertEqual((findings, status), ([], "not_applicable"))
        self.assertIsNone(client.section_names, "the model was called anyway")

    def test_an_out_of_rubric_finding_degrades_instead_of_being_returned(self) -> None:
        findings, status = check_cross_section(
            self._labeled_blocks(),
            self._config(),
            _OutOfRubricCrossSectionClient(),
            max_tokens=4000,
        )
        self.assertEqual(findings, [])
        self.assertEqual(status, "failed")


if __name__ == "__main__":
    unittest.main()
