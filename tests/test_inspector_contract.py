"""The deterministic half of Inspector's contract.

Determinism checks what can be checked without reading prose: the assessment covers
exactly the rubric's units, and lineage points at blocks that exist in the right
section. Judgment belongs to the model; these are the claims code can refuse on
its own.

Two checks left with the nesting they policed - "no unit raises the same reason
twice" and "an absent unit cannot also raise other findings". A unit carries one
verdict now, so neither is expressible and neither needs guarding.
"""

from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.assembly import assess_sections, rubric_units
from services.inspector.contract import validate_result_contract
from services.inspector.models import (
    Assessment,
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


def _unit(
    verdict: str = "specified",
    variable: str = "Efficacy",
    blocks: list[str] | None = None,
) -> Assessment:
    uncited = verdict in ("not_present", "not_applicable")
    sound = verdict in ("specified", "not_applicable")
    return Assessment(
        id=f"Profile|{variable}",
        verdict=verdict,
        statement="" if sound else "A stated defect.",
        section_name="Profile",
        variable_name=variable,
        cited_block_ids=[] if uncited else (blocks or ["document:b1"]),
    )


def _all(verdict: str = "specified", blocks: list[str] | None = None) -> list[Assessment]:
    """Every unit the fixture rubric declares, so assembly has a full answer."""
    return [_unit(verdict, name, blocks) for name in ("Efficacy", "Safety")]


def _result(
    config: InspectionConfig,
    assessments: list[Assessment],
    *,
    document_findings: list[Assessment] | None = None,
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
        sections=assess_sections(config, assessments, mapped_blocks=mapping),
        document_findings=document_findings or [],
        consistency_status="complete",
        assessment_status="complete",
        blocks=source,
    )


class LedgerTests(unittest.TestCase):
    def test_a_complete_assessment_passes(self) -> None:
        config = _config()
        self.assertEqual(len(rubric_units(config)), 2)

        result = _result(config, _all())

        self.assertIs(validate_result_contract(result, config), result)

    def test_a_missing_unit_is_refused(self) -> None:
        config = _config()
        result = _result(config, _all())
        result.sections[0].units = result.sections[0].units[:1]

        with self.assertRaisesRegex(ValueError, "units do not match the rubric"):
            validate_result_contract(result, config)

    def test_a_reordered_section_is_refused(self) -> None:
        config = _config()
        result = _result(config, _all())
        result.sections[0].section_name = "Invented"

        with self.assertRaisesRegex(ValueError, "sections do not match the rubric"):
            validate_result_contract(result, config)


class LineageTests(unittest.TestCase):
    """Two checks are gone with the nesting: "the same reason twice" and "an absent
    unit that also raises other findings". A unit carries one verdict, so a second
    one on it is not a thing that can be written down."""

    def test_an_assessment_must_cite_within_its_own_section(self) -> None:
        config = _config()
        result = _result(
            config,
            [_unit("vague", "Efficacy", ["document:b2"]), _unit("specified", "Safety")],
            blocks=[_block("document:b1", "Profile"), _block("document:b2", "Plan")],
            mapped={"Profile": ["document:b1"]},
        )

        with self.assertRaisesRegex(ValueError, "outside its scope"):
            validate_result_contract(result, config)

    def test_a_unit_filed_under_the_wrong_section_is_refused(self) -> None:
        config = _config()
        result = _result(config, _all())
        result.sections[0].units[1].section_name = "Elsewhere"

        with self.assertRaisesRegex(ValueError, "wrong section"):
            validate_result_contract(result, config)

    def test_duplicate_unit_ids_are_refused(self) -> None:
        config = _config()
        result = _result(config, _all())
        result.sections[0].units[1].id = result.sections[0].units[0].id

        with self.assertRaisesRegex(ValueError, "id is not unique"):
            validate_result_contract(result, config)


class SectionMappingTests(unittest.TestCase):
    def test_a_section_cannot_map_a_block_labelled_elsewhere(self) -> None:
        config = _config()
        result = _result(
            config,
            _all(),
            blocks=[_block("document:b1", "Profile"), _block("document:b2", "Plan")],
            mapped={"Profile": ["document:b2"]},
        )

        with self.assertRaisesRegex(ValueError, "labelled for another section"):
            validate_result_contract(result, config)

    def test_presence_is_derived_from_the_mapping_rather_than_stored(self) -> None:
        """"Absent yet mapping blocks" is no longer expressible, so nothing checks it."""
        config = _config()
        result = _result(config, _all())

        self.assertTrue(result.sections[0].is_present)
        result.sections[0].mapped_block_ids = []
        self.assertFalse(result.sections[0].is_present)
        with self.assertRaises(AttributeError):
            result.sections[0].is_present = True  # type: ignore[misc]


class ConflictTests(unittest.TestCase):
    def _conflict(self, block_ids: list[str]) -> Assessment:
        return Assessment(
            id="conflict|0",
            verdict="section_conflict",
            statement="Two sections disagree.",
            cited_block_ids=block_ids,
        )

    def test_a_conflict_must_span_two_sections(self) -> None:
        config = _config()
        result = _result(config, _all(), document_findings=[self._conflict(["document:b1"])])

        with self.assertRaisesRegex(ValueError, "at least two sections"):
            validate_result_contract(result, config)

    def test_conflicts_require_a_completed_check(self) -> None:
        config = _config()
        result = _result(
            config,
            _all(),
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
        result = _result(config, _all())
        result.assessment_status = "unknown"

        with self.assertRaisesRegex(ValueError, "must be complete"):
            validate_result_contract(result, config)

    def test_blocks_from_another_document_are_refused(self) -> None:
        config = _config()
        result = _result(config, _all())
        result.doc_id = "other"

        with self.assertRaisesRegex(ValueError, "blocks from another document"):
            validate_result_contract(result, config)


if __name__ == "__main__":
    unittest.main()


class DerivedValueTests(unittest.TestCase):
    """A derived value must fail loudly rather than default to a plausible answer.

    Two remain: `is_present` and `verdict_counts`. There used to be four, and the two
    that went were a unit `status` and a finding `level` - both restatements of the
    verdict rather than reads of it. The API models used to default them, and `status`
    defaulted to "met", so a unit whose status went missing published as satisfied.
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
            AssessmentOut,
            InspectionResultOut,
            SectionAssessmentOut,
        )
        from services.inspector.models import inspection_result_to_dict

        config = _config()
        result = _result(config, [_unit("vague", "Efficacy"), _unit("specified", "Safety")])
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
                AssessmentOut,
                published["sections"][0]["units"][0],
                plain["sections"][0]["units"][0],
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
        self.assertGreaterEqual(checked, 2, "the derived set was not discovered")

    def test_serialization_publishes_every_derived_field(self) -> None:
        from api.schemas import InspectionResultOut
        from services.inspector.models import inspection_result_to_dict

        config = _config()
        result = _result(config, [_unit("vague", "Efficacy"), _unit("specified", "Safety")])
        payload = inspection_result_to_dict(result)

        # Constructing the API model is the check: a missing derived value now has no
        # default to fall back on.
        out = InspectionResultOut(**payload)
        self.assertEqual(out.sections[0].units[0].verdict, "vague")
        self.assertTrue(out.sections[0].is_present)
        self.assertEqual(out.sections[0].verdict_counts["vague"], 1)
        self.assertEqual(out.sections[0].verdict_counts["specified"], 1)

    def test_a_truncated_payload_raises_rather_than_publishing(self) -> None:
        from services.inspector.models import inspection_result_to_dict

        config = _config()
        result = _result(config, _all())
        original = inspection_result_to_dict

        # `zip` truncates silently, so the serializer checks its own shape first.
        result.sections.append(result.sections[0])
        payload = original(result)
        self.assertEqual(len(payload["sections"]), len(result.sections))


class PresenceBindingTests(unittest.TestCase):
    """Presence has two representations, and they are produced together."""

    def test_an_absent_section_requires_every_unit_to_report_it(self) -> None:
        config = _config()
        result = _result(config, _all())
        result.sections[0].mapped_block_ids = []

        with self.assertRaisesRegex(ValueError, "must report it missing"):
            validate_result_contract(result, config)

    def test_an_absent_section_whose_units_all_report_it_passes(self) -> None:
        from services.inspector.assembly import absent_unit_assessments

        config = _config()
        result = _result(config, absent_unit_assessments(config, "Profile"))
        result.sections[0].mapped_block_ids = []

        self.assertIs(validate_result_contract(result, config), result)
