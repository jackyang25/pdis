"""Inspector publishes one atom, under one vocabulary, on one axis.

Two shapes preceded this. The first asked three questions per rubric unit and
published a verdict for each, so one defect was counted three times. The second
fixed that but stacked three vocabularies over the single fact it produced: a
`reason` the model chose, a `level` that was a lookup on the reason, and a `status`
that bucketed the levels into three - so a reader saw "Insufficient" on a finding
and "Not met" on the unit above it with no way to know those were one judgement
said twice. It also asked the model for a `recommendation` beside every statement,
which restated it as an imperative.

These tests pin what is left: one vocabulary, one verdict per unit, and the two
derivations that remain because they are reads rather than judgements.
"""

from __future__ import annotations

import unittest

from services.inspector.assembly import (
    absent_unit_assessments,
    assess_sections,
    rank_assessments,
    rubric_units,
    unit_id,
)
from services.inspector.models import (
    ASSESSED_VERDICTS,
    UNCITED_VERDICTS,
    UNIT_VERDICTS,
    VERDICTS,
    Assessment,
    InspectionConfig,
    InspectionResult,
    SectionAssessment,
    SectionSpec,
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


def _unit(
    verdict: str,
    section: str = "Core Variables",
    variable: str | None = "Efficacy",
    optional: bool = False,
) -> Assessment:
    return Assessment(
        id=unit_id(section, variable),
        verdict=verdict,
        statement="A stated defect." if verdict in ASSESSED_VERDICTS else "",
        section_name=section,
        variable_name=variable,
        optional=optional,
        cited_block_ids=[] if verdict in UNCITED_VERDICTS else ["b1"],
    )


def _every_unit(config: InspectionConfig, verdict: str = "specified") -> list[Assessment]:
    return [
        _unit(verdict, section, variable, optional)
        for section, variable, optional in rubric_units(config)
    ]


class VocabularyTests(unittest.TestCase):
    def test_one_vocabulary_covers_every_way_a_unit_can_stand(self) -> None:
        self.assertEqual(
            VERDICTS,
            (
                "specified",
                "not_present",
                "placeholder",
                "insufficient",
                "vague",
                "section_conflict",
                "not_applicable",
            ),
        )

    def test_a_conflict_is_the_only_verdict_no_unit_can_carry(self) -> None:
        """It spans sections, so it belongs to the document rather than a unit."""
        self.assertEqual(set(VERDICTS) - set(UNIT_VERDICTS), {"section_conflict"})

    def test_nothing_to_cite_is_exactly_nothing_there(self) -> None:
        self.assertEqual(set(UNCITED_VERDICTS), {"not_present", "not_applicable"})

    def test_work_is_every_verdict_but_the_two_that_are_not(self) -> None:
        """`specified` is the rubric satisfied; `not_applicable` is it not asking."""
        self.assertEqual(
            set(VERDICTS) - set(ASSESSED_VERDICTS),
            {"specified", "not_applicable"},
        )

    def test_no_second_axis_survives(self) -> None:
        """A level and a status both said again what the verdict already says."""
        import services.inspector.models as models

        for gone in (
            "FindingReason",
            "FINDING_REASONS",
            "FindingLevel",
            "FINDING_LEVELS",
            "LEVEL_BY_REASON",
            "UnitStatus",
            "UNIT_STATUSES",
            "UNCITED_REASON",
            "Finding",
            "UnitAssessment",
        ):
            self.assertFalse(hasattr(models, gone), f"{gone} is still declared")

    def test_a_verdict_is_named_the_way_it_is_rendered(self) -> None:
        """The old keys did not match their labels and collided across axes.

        `unmet` rendered as "Insufficient" while the status `not_met` rendered as
        "Not met" - two near-identical keys for two different axes, which is how a
        reader came to think they were one field.
        """
        self.assertNotIn("unmet", VERDICTS)
        self.assertNotIn("not_met", VERDICTS)
        self.assertIn("insufficient", VERDICTS)

    def test_no_verdict_judges_layout_on_its_own(self) -> None:
        """`off_template` asked a different question from the rest.

        Every other value answers "does the content say enough"; that one answered
        "is it in the right shape". Two questions in one field means a unit that is
        both misnamed and unmeasurable is filed as one of them and the other fact is
        lost. A layout that costs a reader something is `insufficient` or `vague` on
        its own merits.
        """
        self.assertNotIn("off_template", VERDICTS)


class AssessmentTests(unittest.TestCase):
    def test_an_absent_unit_cannot_cite_a_block(self) -> None:
        with self.assertRaises(ValueError):
            Assessment(
                id="x",
                verdict="not_present",
                statement="Nothing here.",
                section_name="Core Variables",
                variable_name="Efficacy",
                cited_block_ids=["b1"],
            )

    def test_anything_read_from_the_document_must_say_where(self) -> None:
        with self.assertRaises(ValueError):
            Assessment(
                id="x",
                verdict="vague",
                statement="Loosely worded.",
                section_name="Core Variables",
                variable_name="Efficacy",
            )

    def test_a_sound_unit_has_nothing_to_state(self) -> None:
        """A sentence there would be a claim with no defect behind it."""
        with self.assertRaises(ValueError):
            Assessment(
                id="x",
                verdict="specified",
                statement="Looks fine.",
                section_name="Core Variables",
                variable_name="Efficacy",
                cited_block_ids=["b1"],
            )

    def test_a_shortfall_must_say_what_is_wrong(self) -> None:
        with self.assertRaises(ValueError):
            Assessment(
                id="x",
                verdict="insufficient",
                section_name="Core Variables",
                variable_name="Efficacy",
                cited_block_ids=["b1"],
            )

    def test_a_variable_assessment_must_name_its_section(self) -> None:
        with self.assertRaises(ValueError):
            Assessment(
                id="x",
                verdict="vague",
                statement="Loose.",
                variable_name="Efficacy",
                cited_block_ids=["b1"],
            )

    def test_a_document_assessment_names_no_unit(self) -> None:
        item = Assessment(
            id="conflict|0",
            verdict="section_conflict",
            statement="Two sections disagree.",
            cited_block_ids=["b1", "b2"],
        )

        self.assertIsNone(item.section_name)
        self.assertIsNone(item.variable_name)

    def test_needs_work_reads_the_one_axis_rather_than_adding_one(self) -> None:
        self.assertTrue(_unit("insufficient").needs_work)
        self.assertTrue(_unit("vague").needs_work)
        self.assertFalse(_unit("specified").needs_work)
        self.assertFalse(_unit("not_applicable", optional=True).needs_work)

    def test_only_an_optional_unit_can_be_not_applicable(self) -> None:
        """Whether absence is acceptable is the rubric author's decision.

        Left ungated, a model could return `not_applicable` on a required unit and the
        unit would drop out of the worklist - a real shortfall disappearing quietly,
        which is the one failure mode this tool must not have.
        """
        with self.assertRaises(ValueError):
            Assessment(
                id="x",
                verdict="not_applicable",
                section_name="Core Variables",
                variable_name="Efficacy",
                optional=False,
            )

    def test_no_recommendation_field_survives(self) -> None:
        """It restated the statement as an imperative, and the web layer had grown
        a guard to hide one of the two."""
        self.assertNotIn("recommendation", Assessment.__dataclass_fields__)


class DenominatorTests(unittest.TestCase):
    """The rubric decides what was assessed, never the model's output."""

    def test_a_prose_section_is_one_unnamed_unit(self) -> None:
        config = _config()
        sections = assess_sections(config, _every_unit(config))

        introduction = sections[0]
        self.assertEqual(len(introduction.units), 1)
        self.assertIsNone(introduction.units[0].variable_name)

    def test_a_unit_nobody_assessed_is_refused_rather_than_filled(self) -> None:
        """"Not checked" must never read as "nothing wrong"."""
        config = _config()
        answered = _every_unit(config)[:-1]

        with self.assertRaises(ValueError):
            assess_sections(config, answered)

    def test_an_assessment_outside_the_rubric_is_refused(self) -> None:
        config = _config()
        stray = _unit("vague", section="Nowhere", variable="Ghost")

        with self.assertRaises(ValueError):
            assess_sections(config, [*_every_unit(config), stray])

    def test_a_section_counts_its_units_by_verdict(self) -> None:
        config = _config()
        units = _every_unit(config)
        units[1] = _unit("insufficient", "Core Variables", "Efficacy")
        sections = assess_sections(config, units)

        core = next(s for s in sections if s.section_name == "Core Variables")
        self.assertEqual(core.verdict_counts["insufficient"], 1)
        self.assertEqual(core.verdict_counts["specified"], 1)
        self.assertEqual(sum(core.verdict_counts.values()), len(core.units))


class RankTests(unittest.TestCase):
    """Order comes from the vocabulary and the rubric, never from a new judgement."""

    def test_a_worse_verdict_precedes_a_lesser_one(self) -> None:
        config = _config()
        units = _every_unit(config)
        units[1] = _unit("vague", "Core Variables", "Efficacy")
        units[2] = _unit("not_present", "Core Variables", "Safety")

        ordered = rank_assessments(config, assess_sections(config, units))

        self.assertEqual(
            [item.verdict for item in ordered], ["not_present", "vague"]
        )

    def test_rubric_order_breaks_the_tie(self) -> None:
        config = _config()
        units = _every_unit(config)
        units[1] = _unit("vague", "Core Variables", "Efficacy")
        units[2] = _unit("vague", "Core Variables", "Safety")

        ordered = rank_assessments(config, assess_sections(config, units))

        self.assertEqual([item.variable_name for item in ordered], ["Efficacy", "Safety"])

    def test_a_sound_unit_is_not_work(self) -> None:
        config = _config()
        ordered = rank_assessments(config, assess_sections(config, _every_unit(config)))

        self.assertEqual(ordered, [])

    def test_an_accepted_absence_is_not_work(self) -> None:
        """The rubric accepts it, so it is not a shortfall to rank."""
        config = _config()
        units = _every_unit(config)
        units[-1] = _unit(
            "not_applicable", "Additional Variables", "Companion Test", optional=True
        )

        ordered = rank_assessments(config, assess_sections(config, units))

        self.assertEqual(ordered, [])

    def test_ranks_are_dense_and_start_at_zero(self) -> None:
        config = _config()
        units = _every_unit(config)
        units[1] = _unit("vague", "Core Variables", "Efficacy")
        units[2] = _unit("insufficient", "Core Variables", "Safety")

        ordered = rank_assessments(config, assess_sections(config, units))

        self.assertEqual([item.rank for item in ordered], list(range(len(ordered))))


class AbsenceTests(unittest.TestCase):
    def test_an_unwritten_section_reports_every_unit_absent(self) -> None:
        """Collapsing it into one line would leave the rest looking assessed."""
        config = _config()
        absent = absent_unit_assessments(config, "Core Variables")

        self.assertEqual([item.variable_name for item in absent], ["Efficacy", "Safety"])
        self.assertTrue(all(item.verdict == "not_present" for item in absent))
        self.assertTrue(all(not item.cited_block_ids for item in absent))


class ResultTests(unittest.TestCase):
    def test_the_document_publishes_no_second_copy_of_its_units(self) -> None:
        """A worklist is the same units ordered by rank, composed on read."""
        self.assertNotIn("worklist", InspectionResult.__dataclass_fields__)
        self.assertNotIn("top_findings", InspectionResult.__dataclass_fields__)

    def test_a_conflict_is_the_same_shape_as_any_other_assessment(self) -> None:
        config = _config()
        conflict = Assessment(
            id="conflict|0",
            verdict="section_conflict",
            statement="Two sections disagree about efficacy.",
            cited_block_ids=["b1", "b2"],
        )
        sections = assess_sections(config, _every_unit(config))
        ordered = rank_assessments(config, sections, [conflict])

        self.assertEqual(ordered, [conflict])
        self.assertEqual(conflict.rank, 0)


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
