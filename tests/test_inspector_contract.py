"""The deterministic half of Inspector's contract.

Determinism checks what can be checked without reading prose: the assessment covers
exactly the rubric's units, lineage points at blocks that exist in the right
section, and no unit reports the same reason twice. Judgment belongs to the model;
these are the claims code can refuse on its own.
"""

from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.assembly import assess_sections, rubric_units
from services.inspector.contract import validate_result_contract
from services.inspector.models import (
    Finding,
    InspectionConfig,
    InspectionResult,
    SectionSpec,
    VariableSpec,
)


def _block(block_id: str, section: str) -> ContentBlock:
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


def _config() -> InspectionConfig:
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
                variables=[
                    VariableSpec(name="Efficacy", description="Efficacy target"),
                    VariableSpec(name="Safety", description="Safety target"),
                ],
            )
        ],
    )


def _finding(reason: str, variable: str = "Efficacy", blocks: list[str] | None = None) -> Finding:
    return Finding(
        id=f"Profile|{variable}|{reason}",
        reason=reason,
        statement="A stated defect.",
        recommendation="Do the thing.",
        section_name="Profile",
        variable_name=variable,
        cited_block_ids=[] if reason == "missing" else (blocks or ["document:b1"]),
    )


def _result(
    config: InspectionConfig,
    findings: list[Finding],
    *,
    document_findings: list[Finding] | None = None,
    blocks: list[ContentBlock] | None = None,
    mapped: dict[str, list[str]] | None = None,
) -> InspectionResult:
    source = blocks if blocks is not None else [_block("document:b1", "Profile")]
    mapping = mapped if mapped is not None else {
        section.name: [b.id for b in source if b.section_label == section.name]
        for section in config.sections
    }
    return InspectionResult(
        doc_id="document",
        sections=assess_sections(config, findings, mapped_blocks=mapping),
        document_findings=document_findings or [],
        consistency_status="complete",
        assessment_status="complete",
        blocks=source,
    )


class LedgerTests(unittest.TestCase):
    def test_a_complete_assessment_passes(self) -> None:
        config = _config()
        self.assertEqual(len(rubric_units(config)), 2)

        result = _result(config, [])

        self.assertIs(validate_result_contract(result, config), result)

    def test_a_missing_unit_is_refused(self) -> None:
        config = _config()
        result = _result(config, [])
        result.sections[0].units = result.sections[0].units[:1]

        with self.assertRaisesRegex(ValueError, "units do not match the rubric"):
            validate_result_contract(result, config)

    def test_a_reordered_section_is_refused(self) -> None:
        config = _config()
        result = _result(config, [])
        result.sections[0].section_name = "Invented"

        with self.assertRaisesRegex(ValueError, "sections do not match the rubric"):
            validate_result_contract(result, config)


class FindingLineageTests(unittest.TestCase):
    def test_a_unit_cannot_raise_the_same_reason_twice(self) -> None:
        config = _config()
        result = _result(config, [])
        result.sections[0].units[0].findings = [_finding("unclear"), _finding("unclear")]

        with self.assertRaisesRegex(ValueError, "raises a reason twice"):
            validate_result_contract(result, config)

    def test_an_absent_unit_cannot_also_raise_other_findings(self) -> None:
        """The check that keeps one absence from becoming two entries again."""
        config = _config()
        result = _result(config, [])
        result.sections[0].units[0].findings = [_finding("missing"), _finding("off_template")]

        with self.assertRaisesRegex(ValueError, "cannot also raise other findings"):
            validate_result_contract(result, config)

    def test_a_finding_must_cite_within_its_own_section(self) -> None:
        config = _config()
        result = _result(
            config,
            [_finding("unclear", blocks=["document:b2"])],
            blocks=[_block("document:b1", "Profile"), _block("document:b2", "Plan")],
            mapped={"Profile": ["document:b1"]},
        )

        with self.assertRaisesRegex(ValueError, "outside its scope"):
            validate_result_contract(result, config)

    def test_a_finding_filed_against_the_wrong_unit_is_refused(self) -> None:
        config = _config()
        result = _result(config, [])
        result.sections[0].units[1].findings = [_finding("unclear", variable="Efficacy")]

        with self.assertRaisesRegex(ValueError, "wrong unit"):
            validate_result_contract(result, config)

    def test_duplicate_finding_ids_are_refused(self) -> None:
        config = _config()
        result = _result(config, [])
        result.sections[0].units[0].findings = [_finding("unclear")]
        result.sections[0].units[1].findings = [
            Finding(
                id="Profile|Efficacy|unclear",
                reason="unclear",
                statement="Same id.",
                section_name="Profile",
                variable_name="Safety",
                cited_block_ids=["document:b1"],
            )
        ]

        with self.assertRaisesRegex(ValueError, "id is not unique"):
            validate_result_contract(result, config)


class SectionMappingTests(unittest.TestCase):
    def test_a_section_cannot_map_a_block_labelled_elsewhere(self) -> None:
        config = _config()
        result = _result(
            config,
            [],
            blocks=[_block("document:b1", "Profile"), _block("document:b2", "Plan")],
            mapped={"Profile": ["document:b2"]},
        )

        with self.assertRaisesRegex(ValueError, "labelled for another section"):
            validate_result_contract(result, config)

    def test_presence_is_derived_from_the_mapping_rather_than_stored(self) -> None:
        """"Absent yet mapping blocks" is no longer expressible, so nothing checks it."""
        config = _config()
        result = _result(config, [])

        self.assertTrue(result.sections[0].is_present)
        result.sections[0].mapped_block_ids = []
        self.assertFalse(result.sections[0].is_present)
        with self.assertRaises(AttributeError):
            result.sections[0].is_present = True  # type: ignore[misc]


class ConflictTests(unittest.TestCase):
    def _conflict(self, block_ids: list[str]) -> Finding:
        return Finding(
            id="conflict|0",
            reason="conflicting",
            statement="Two sections disagree.",
            recommendation="Reconcile them.",
            cited_block_ids=block_ids,
        )

    def test_a_conflict_must_span_two_sections(self) -> None:
        config = _config()
        result = _result(config, [], document_findings=[self._conflict(["document:b1"])])

        with self.assertRaisesRegex(ValueError, "at least two sections"):
            validate_result_contract(result, config)

    def test_conflicts_require_a_completed_check(self) -> None:
        config = _config()
        result = _result(
            config,
            [],
            document_findings=[self._conflict(["document:b1", "document:b2"])],
            blocks=[_block("document:b1", "Profile"), _block("document:b2", "Plan")],
            mapped={"Profile": ["document:b1"]},
        )
        result.consistency_status = "failed"

        with self.assertRaisesRegex(ValueError, "require a completed check"):
            validate_result_contract(result, config)


class RunCompletionTests(unittest.TestCase):
    def test_an_incomplete_run_cannot_become_a_final_result(self) -> None:
        config = _config()
        result = _result(config, [])
        result.assessment_status = "unknown"

        with self.assertRaisesRegex(ValueError, "must be complete"):
            validate_result_contract(result, config)

    def test_blocks_from_another_document_are_refused(self) -> None:
        config = _config()
        result = _result(config, [])
        result.doc_id = "other"

        with self.assertRaisesRegex(ValueError, "blocks from another document"):
            validate_result_contract(result, config)


if __name__ == "__main__":
    unittest.main()


class DerivedValueTests(unittest.TestCase):
    """A derived value must fail loudly rather than default to a plausible answer.

    `status`, `level`, and `status_counts` are computed during serialization. The API
    models used to default them, and `status` defaulted to "met" - so a unit whose
    status went missing would have published as satisfied.
    """

    def test_no_derived_field_anywhere_carries_a_default(self) -> None:
        """The rule, not a list of the three fields that happened to break it.

        A derived value is computed, so it is never absent - which means a default on
        one can only ever mask a bug. The derived set is read from the serializer
        rather than written down here, so a derived field added tomorrow is covered
        without anyone remembering to add it.
        """
        from dataclasses import asdict

        from api.schemas import (
            InspectionResultOut,
            RubricFindingOut,
            SectionAssessmentOut,
            UnitAssessmentOut,
        )
        from services.inspector.models import inspection_result_to_dict

        config = _config()
        result = _result(config, [_finding("unclear")])
        plain = asdict(result)
        published = inspection_result_to_dict(result)

        # Whatever the serializer adds beyond `asdict` is, by definition, derived.
        models = {
            "result": (InspectionResultOut, published, plain),
            "section": (
                SectionAssessmentOut,
                published["sections"][0],
                plain["sections"][0],
            ),
            "unit": (
                UnitAssessmentOut,
                published["sections"][0]["units"][0],
                plain["sections"][0]["units"][0],
            ),
            "finding": (
                RubricFindingOut,
                published["sections"][0]["units"][0]["findings"][0],
                plain["sections"][0]["units"][0]["findings"][0],
            ),
        }
        checked = 0
        for level, (model, after, before) in models.items():
            for name in set(after) - set(before):
                checked += 1
                self.assertTrue(
                    model.model_fields[name].is_required(),
                    f"{model.__name__}.{name} is derived at the {level} level and "
                    "must not have a default",
                )
        self.assertGreaterEqual(checked, 4, "the derived set was not discovered")

    def test_serialization_publishes_every_derived_field(self) -> None:
        from api.schemas import InspectionResultOut
        from services.inspector.models import inspection_result_to_dict

        config = _config()
        result = _result(config, [_finding("unclear")])
        payload = inspection_result_to_dict(result)

        # Constructing the API model is the check: a missing derived value now has no
        # default to fall back on.
        out = InspectionResultOut(**payload)
        self.assertEqual(out.sections[0].units[0].status, "could_be_stronger")
        self.assertEqual(out.sections[0].units[0].findings[0].level, "could_be_stronger")
        self.assertEqual(out.sections[0].status_counts["could_be_stronger"], 1)

    def test_a_truncated_payload_raises_rather_than_publishing(self) -> None:
        from services.inspector.models import inspection_result_to_dict

        config = _config()
        result = _result(config, [])
        original = inspection_result_to_dict

        # `zip` truncates silently, so the serializer checks its own shape first.
        result.sections.append(result.sections[0])
        payload = original(result)
        self.assertEqual(len(payload["sections"]), len(result.sections))


class PresenceBindingTests(unittest.TestCase):
    """Presence has two representations, and they are produced together."""

    def test_an_absent_section_requires_every_unit_to_report_it(self) -> None:
        config = _config()
        result = _result(config, [])
        result.sections[0].mapped_block_ids = []

        with self.assertRaisesRegex(ValueError, "must report it missing"):
            validate_result_contract(result, config)

    def test_an_absent_section_whose_units_all_report_it_passes(self) -> None:
        from services.inspector.assembly import absent_unit_findings

        config = _config()
        result = _result(config, absent_unit_findings(config, "Profile"))
        result.sections[0].mapped_block_ids = []

        self.assertIs(validate_result_contract(result, config), result)
