"""Inspector reports gaps by severity, not a letter grade.

A letter implied two things the tool cannot support: that the distance from A to
B equals the distance from D to F, and that a section's quality is the mean of
its parts. Both were arithmetic on a subjective label. A gap is now stated at the
severity the model assigned it, and a roll-up counts gaps rather than averaging
them.
"""

from __future__ import annotations

import unittest

from services.inspector.models import (
    DIMENSION_VERDICTS,
    GAP_VERDICTS,
    DimensionAssessment,
    InspectionResult,
    SectionGrade,
    VariableGrade,
)


def _variable(name: str, verdict: str, issue: str = "A stated gap.") -> VariableGrade:
    return VariableGrade(
        variable_name=name,
        dimensions={
            "completeness": DimensionAssessment(
                verdict=verdict, issues=[issue] if issue else []
            ),
            "adherence": DimensionAssessment(verdict="meets"),
            "rigor": DimensionAssessment(verdict="meets"),
        },
        content_status="substantive",
    )


class VerdictVocabularyTests(unittest.TestCase):
    def test_the_vocabulary_holds_two_severities_and_two_non_gaps(self) -> None:
        self.assertEqual(
            DIMENSION_VERDICTS,
            frozenset({"critical", "for_consideration", "meets", "not_applicable"}),
        )
        self.assertEqual(GAP_VERDICTS, frozenset({"critical", "for_consideration"}))

    def test_a_verdict_outside_the_vocabulary_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            DimensionAssessment(verdict="B")

    def test_no_letter_scale_survives(self) -> None:
        """A converter left in place is a second vocabulary waiting to return."""
        import services.inspector.models as models

        for removed in ("Grade", "VALID_GRADES", "GRADE_TO_SCORE",
                        "score_to_grade", "average_score"):
            self.assertFalse(
                hasattr(models, removed), f"{removed} still exists"
            )


class GapCountTests(unittest.TestCase):
    """A roll-up counts what was found; it does not average a judgement."""

    def test_a_section_counts_its_variables_gaps_by_severity(self) -> None:
        section = SectionGrade(
            section_name="Profile",
            variable_grades=[
                _variable("Efficacy", "critical"),
                _variable("Safety", "for_consideration"),
                _variable("Dose", "for_consideration"),
                _variable("Route", "meets", issue=""),
            ],
        )

        self.assertEqual(section.gap_counts, {"critical": 1, "for_consideration": 2})

    def test_a_prose_section_counts_its_own_dimensions(self) -> None:
        """A section without variables is assessed directly, so it counts directly."""
        section = SectionGrade(
            section_name="Narrative",
            dimensions={
                "completeness": DimensionAssessment(
                    verdict="critical", issues=["A stated gap."]
                ),
                "adherence": DimensionAssessment(verdict="meets"),
                "rigor": DimensionAssessment(
                    verdict="for_consideration", issues=["A softer gap."]
                ),
            },
        )

        self.assertEqual(section.gap_counts, {"critical": 1, "for_consideration": 1})

    def test_a_missing_section_is_one_critical_gap(self) -> None:
        section = SectionGrade(section_name="Absent", is_present=False)

        self.assertEqual(section.gap_counts, {"critical": 1, "for_consideration": 0})

    def test_the_document_sums_its_sections(self) -> None:
        result = InspectionResult(
            doc_id="document",
            section_grades=[
                SectionGrade(
                    section_name="Profile",
                    variable_grades=[_variable("Efficacy", "critical")],
                ),
                SectionGrade(section_name="Absent", is_present=False),
            ],
        )

        self.assertEqual(result.gap_counts, {"critical": 2, "for_consideration": 0})


if __name__ == "__main__":
    unittest.main()
