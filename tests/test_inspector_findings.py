"""Inspector publishes one finding shape, under one vocabulary.

The shape this replaced asked three questions per rubric unit and published a
verdict for each, so one defect could be counted three times, absence was recorded
in three places that could disagree, and a cross-section conflict carried different
field names for the same concepts. These tests pin the single vocabulary, the
single atom, and the derivations that stop any of it drifting apart again.
"""

from __future__ import annotations

import unittest

from services.inspector.assembly import assess_sections, rank_findings, rubric_units
from services.inspector.models import (
    FINDING_LEVELS,
    FINDING_REASONS,
    LEVEL_BY_REASON,
    UNCITED_REASON,
    UNIT_REASONS,
    Finding,
    InspectionConfig,
    InspectionResult,
    SectionSpec,
    UnitAssessment,
    VariableSpec,
)


def _config() -> InspectionConfig:
    """A rubric with all three unit kinds: prose, required, and optional."""
    return InspectionConfig(
        type_key="test_org_itpp_vaccine",
        org="test_org",
        source_type="itpp",
        intervention_class="vaccine",
        display_name="Test Rubric",
        sections=[
            SectionSpec(name="Introduction", description="Framing."),
            SectionSpec(
                name="Core Variables",
                description="The main table.",
                variables=[
                    VariableSpec(name="Efficacy", description="Protective efficacy."),
                    VariableSpec(name="Safety", description="Adverse event profile."),
                ],
            ),
            SectionSpec(
                name="Additional Variables",
                description="Not relevant to every document.",
                optional=True,
                variables=[VariableSpec(name="Companion Test", description="If needed.")],
            ),
        ],
    )


def _finding(reason: str, section: str = "Core Variables", variable: str | None = "Efficacy") -> Finding:
    return Finding(
        id=f"{section}|{variable or ''}|{reason}",
        reason=reason,
        statement="A stated defect.",
        recommendation="Do the stated thing.",
        section_name=section,
        variable_name=variable,
        cited_block_ids=[] if reason == UNCITED_REASON else ["b1"],
    )


class VocabularyTests(unittest.TestCase):
    def test_one_reason_vocabulary_covers_every_kind_of_defect(self) -> None:
        self.assertEqual(
            FINDING_REASONS,
            ("missing", "placeholder", "unmet", "off_template", "unclear", "conflicting"),
        )

    def test_a_conflict_is_the_only_reason_no_unit_can_raise(self) -> None:
        """It spans sections, so it belongs to the document rather than a unit."""
        self.assertEqual(set(FINDING_REASONS) - set(UNIT_REASONS), {"conflicting"})

    def test_every_reason_maps_to_exactly_one_level(self) -> None:
        """The level is derived, so a reason and a severity cannot disagree."""
        self.assertEqual(set(LEVEL_BY_REASON), set(FINDING_REASONS))
        self.assertEqual(set(LEVEL_BY_REASON.values()), set(FINDING_LEVELS))

    def test_absence_is_the_only_reason_that_cites_nothing(self) -> None:
        self.assertEqual(UNCITED_REASON, "missing")

    def test_the_three_dimension_vocabulary_does_not_survive(self) -> None:
        import services.inspector.models as models

        for removed in (
            "DimensionAssessment",
            "VariableGrade",
            "SectionGrade",
            "TopIssue",
            "CrossSectionFinding",
            "DimensionVerdict",
            "DIMENSIONS",
            "DIMENSION_VERDICTS",
            "GAP_VERDICTS",
            "ContentStatus",
            "CONTENT_STATUSES",
        ):
            self.assertFalse(hasattr(models, removed), f"{removed} still exists")


class FindingTests(unittest.TestCase):
    def test_a_finding_derives_its_level_from_its_reason(self) -> None:
        self.assertEqual(_finding("missing").level, "not_met")
        self.assertEqual(_finding("unclear").level, "could_be_stronger")

    def test_an_absent_unit_cannot_cite_a_block(self) -> None:
        with self.assertRaises(ValueError):
            Finding(
                id="x",
                reason="missing",
                statement="Absent.",
                section_name="Core Variables",
                variable_name="Efficacy",
                cited_block_ids=["b1"],
            )

    def test_a_variable_finding_must_name_its_section(self) -> None:
        with self.assertRaises(ValueError):
            Finding(id="x", reason="unclear", statement="Vague.", variable_name="Efficacy")

    def test_a_document_finding_names_no_unit(self) -> None:
        conflict = Finding(
            id="conflict|0",
            reason="conflicting",
            statement="Two sections disagree.",
            cited_block_ids=["b1", "b9"],
        )

        self.assertIsNone(conflict.section_name)
        self.assertIsNone(conflict.variable_name)


class UnitStatusTests(unittest.TestCase):
    """A unit restates its findings; it never adds a judgment of its own."""

    def test_no_findings_means_met(self) -> None:
        self.assertEqual(UnitAssessment(variable_name="Efficacy").status, "met")

    def test_any_not_met_reason_means_not_met(self) -> None:
        for reason in ("missing", "placeholder", "unmet"):
            unit = UnitAssessment(variable_name="V", findings=[_finding(reason)])
            self.assertEqual(unit.status, "not_met", reason)

    def test_an_improvable_reason_alone_means_could_be_stronger(self) -> None:
        for reason in ("off_template", "unclear"):
            unit = UnitAssessment(variable_name="V", findings=[_finding(reason)])
            self.assertEqual(unit.status, "could_be_stronger", reason)

    def test_the_worst_level_on_the_unit_decides(self) -> None:
        unit = UnitAssessment(
            variable_name="V",
            findings=[_finding("unclear"), _finding("unmet")],
        )
        self.assertEqual(unit.status, "not_met")

    def test_absence_the_rubric_accepts_is_not_a_shortfall(self) -> None:
        unit = UnitAssessment(variable_name="V", optional=True, findings=[_finding("missing")])
        self.assertEqual(unit.status, "not_applicable")


class DenominatorTests(unittest.TestCase):
    """The rubric owns how many units exist; model output cannot shrink it."""

    def test_a_prose_section_is_one_unnamed_unit(self) -> None:
        self.assertEqual(
            rubric_units(_config()),
            [
                ("Introduction", None, False),
                ("Core Variables", "Efficacy", False),
                ("Core Variables", "Safety", False),
                ("Additional Variables", "Companion Test", True),
            ],
        )

    def test_every_unit_is_assessed_even_when_the_model_is_silent(self) -> None:
        config = _config()

        sections = assess_sections(config, findings=[_finding("unclear")])

        self.assertEqual([s.section_name for s in sections], [s.name for s in config.sections])
        self.assertEqual([len(s.units) for s in sections], [1, 2, 1])
        self.assertEqual(
            [unit.status for section in sections for unit in section.units],
            ["met", "could_be_stronger", "met", "met"],
        )

    def test_a_finding_for_a_unit_outside_the_rubric_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            assess_sections(_config(), findings=[_finding("unclear", section="Invented")])

    def test_a_section_counts_its_units_by_status(self) -> None:
        sections = assess_sections(
            _config(),
            findings=[_finding("missing", variable="Efficacy"), _finding("unclear", variable="Safety")],
        )

        self.assertEqual(
            sections[1].status_counts,
            {"met": 0, "could_be_stronger": 1, "not_met": 1, "not_applicable": 0},
        )


class RankTests(unittest.TestCase):
    """Order comes from the rubric's own sequence, not a weight we invented."""

    def test_an_unsatisfied_requirement_precedes_an_improvable_one(self) -> None:
        config = _config()
        sections = assess_sections(
            config,
            findings=[
                _finding("unclear", variable="Efficacy"),
                _finding("unmet", variable="Safety"),
            ],
        )

        ordered = rank_findings(config, sections)

        self.assertEqual([f.reason for f in ordered], ["unmet", "unclear"])

    def test_rubric_order_breaks_the_tie(self) -> None:
        config = _config()
        sections = assess_sections(
            config,
            findings=[
                _finding("unclear", section="Additional Variables", variable="Companion Test"),
                _finding("unclear", section="Core Variables", variable="Safety"),
            ],
        )

        ordered = rank_findings(config, sections)

        self.assertEqual(
            [f.section_name for f in ordered], ["Core Variables", "Additional Variables"]
        )

    def test_accepted_absences_are_not_work(self) -> None:
        config = _config()
        sections = assess_sections(
            config,
            findings=[
                _finding("missing", section="Additional Variables", variable="Companion Test"),
                _finding("unclear", variable="Efficacy"),
            ],
        )

        ordered = rank_findings(config, sections)

        self.assertEqual([f.reason for f in ordered], ["unclear"])

    def test_ranks_are_dense_and_start_at_zero(self) -> None:
        config = _config()
        sections = assess_sections(
            config,
            findings=[_finding("unmet", variable="Efficacy"), _finding("unclear", variable="Safety")],
        )

        ordered = rank_findings(config, sections)

        self.assertEqual([f.rank for f in ordered], [0, 1])


class ResultTests(unittest.TestCase):
    def test_the_document_publishes_no_second_copy_of_its_findings(self) -> None:
        """A flattened array beside the sections would be a shape that can drift."""
        result = InspectionResult(doc_id="d")

        for removed in ("top_issues", "section_grades", "gap_counts", "grading_status"):
            self.assertFalse(hasattr(result, removed), f"{removed} still exists")

    def test_a_conflict_is_the_same_shape_as_any_other_finding(self) -> None:
        result = InspectionResult(
            doc_id="d",
            document_findings=[
                Finding(
                    id="conflict|0",
                    reason="conflicting",
                    statement="Two sections disagree on target population.",
                    recommendation="Reconcile them.",
                    cited_block_ids=["b3", "b9"],
                )
            ],
        )

        conflict = result.document_findings[0]
        self.assertEqual(conflict.level, "not_met")
        self.assertEqual(conflict.cited_block_ids, ["b3", "b9"])


class ConfigTests(unittest.TestCase):
    def test_a_section_and_a_variable_declare_the_same_things(self) -> None:
        """One shape at both levels, so a reader learns the schema once."""
        section_fields = set(SectionSpec.__dataclass_fields__)
        variable_fields = set(VariableSpec.__dataclass_fields__)

        self.assertEqual(section_fields - variable_fields, {"variables"})

    def test_no_authored_weight_survives(self) -> None:
        """It ranked one list, was calibrated by nobody, and sat in eleven configs."""
        self.assertNotIn("weight", SectionSpec.__dataclass_fields__)

    def test_expectations_are_one_block_not_three(self) -> None:
        for field in ("completeness", "adherence", "rigor"):
            self.assertNotIn(field, SectionSpec.__dataclass_fields__)
            self.assertNotIn(field, VariableSpec.__dataclass_fields__)
        self.assertIn("expectations", VariableSpec.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()


class ProvenanceTests(unittest.TestCase):
    """Where a rubric's structure came from is answerable from the file."""

    def test_every_shipped_rubric_records_what_it_mirrors(self) -> None:
        from services.inspector.models import available_configs

        for config in available_configs():
            self.assertTrue(
                config.mirrors,
                f"{config.type_key} does not record its source template",
            )

    def test_mirrors_is_free_text_rather_than_a_structured_claim(self) -> None:
        """The sources do not share a shape, so neither does the field.

        Naming a library, document, and revision separately would bake in the
        conventions of one source and need reworking for the next.
        """
        self.assertEqual(InspectionConfig.__dataclass_fields__["mirrors"].type, "str")

    def test_a_rubric_may_omit_provenance_without_failing_to_load(self) -> None:
        """A rubric that mirrors nothing is legitimate; the field is optional."""
        config = InspectionConfig(
            type_key="t",
            org="o",
            source_type="itpp",
            intervention_class="vaccine",
            display_name="T",
            sections=[SectionSpec(name="S", description="D")],
        )

        self.assertEqual(config.mirrors, "")
