"""The canonical layer publishes what the model said, and nothing more.

This refactor moved fields; it must not have moved a grade. These tests pin the
judgments themselves against a fixed set of model replies, so a future change to
the merge cannot quietly alter a report card while the shape still validates.
"""

from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.models import (
    ABSENT_CONTENT_STATUS,
    CONTENT_STATUSES,
    DIMENSIONS,
    PRESENT_CONTENT_STATUSES,
    InspectionConfig,
    SectionSpec,
    VariableSpec,
    average_score,
    score_to_grade,
)
from services.inspector.stages.grader import _merge_variable_bearing


def _section() -> SectionSpec:
    return SectionSpec(
        name="Profile",
        description="Profile section",
        weight=1.0,
        variables=[
            VariableSpec(name="Efficacy", description="Efficacy target"),
            VariableSpec(name="Safety", description="Safety target"),
        ],
    )


def _item(name: str, grade: str, blocks: list[str], status: str, issue: str) -> dict:
    return {
        "variable_name": name,
        "block_ids": blocks,
        "grade": grade,
        "issues": [issue],
        "recommendation": f"Fix {name}.",
        "content_status": status,
    }


class CanonicalFidelityTests(unittest.TestCase):
    def test_the_merge_reports_the_grades_the_model_returned(self) -> None:
        merged = _merge_variable_bearing(
            _section(),
            {
                "completeness": {
                    "variable_grades": [
                        _item("Efficacy", "A", ["b1"], "substantive", "none"),
                        _item("Safety", "C", ["b1"], "partial", "half filled"),
                    ]
                },
                "adherence": {
                    "variable_grades": [
                        _item("Efficacy", "B", ["b1"], "substantive", "naming"),
                        _item("Safety", "D", ["b2"], "partial", "token"),
                    ]
                },
                "rigor": {
                    "variable_grades": [
                        _item("Efficacy", "F", ["b2"], "substantive", "vague"),
                        _item("Safety", "A", ["b1"], "partial", "fine"),
                    ]
                },
            },
        )

        actual = {
            variable.variable_name: {
                dimension: (
                    variable.dimensions[dimension].grade,
                    variable.dimensions[dimension].issues,
                    variable.dimensions[dimension].recommendation,
                    variable.dimensions[dimension].cited_block_ids,
                )
                for dimension in DIMENSIONS
            }
            for variable in merged.variable_grades
        }
        self.assertEqual(
            actual,
            {
                "Efficacy": {
                    "completeness": ("A", ["none"], "Fix Efficacy.", ["b1"]),
                    "adherence": ("B", ["naming"], "Fix Efficacy.", ["b1"]),
                    "rigor": ("F", ["vague"], "Fix Efficacy.", ["b2"]),
                },
                "Safety": {
                    "completeness": ("C", ["half filled"], "Fix Safety.", ["b1"]),
                    "adherence": ("D", ["token"], "Fix Safety.", ["b2"]),
                    "rigor": ("A", ["fine"], "Fix Safety.", ["b1"]),
                },
            },
        )

    def test_absence_overrides_the_model_on_exactly_three_axes(self) -> None:
        merged = _merge_variable_bearing(
            _section(),
            {
                dimension: {
                    "variable_grades": [
                        _item("Efficacy", "A", ["b1"], "substantive", "none"),
                        _item("Safety", "B", [], ABSENT_CONTENT_STATUS, "ignored"),
                    ]
                }
                for dimension in DIMENSIONS
            },
        )

        safety = merged.variable_grades[1]
        # The model's own letters for an absent variable are replaced, because
        # absent content cannot be complete, well-formed, or rigorous.
        self.assertEqual(safety.dimensions["completeness"].grade, "F")
        self.assertEqual(safety.dimensions["adherence"].grade, "F")
        self.assertEqual(safety.dimensions["rigor"].grade, "N/A")
        self.assertEqual(safety.cited_block_ids, [])
        # A present sibling is untouched by its neighbour's absence.
        self.assertEqual(merged.variable_grades[0].dimensions["completeness"].grade, "A")


class GradingScaleTests(unittest.TestCase):
    """One scale, shared by the variable, section, and document roll-ups."""

    def test_boundaries_round_the_way_the_report_card_expects(self) -> None:
        self.assertEqual(score_to_grade(None), "N/A")
        for score, expected in (
            (4.0, "A"), (3.5, "A"), (3.49, "B"), (2.5, "B"),
            (2.49, "C"), (1.5, "C"), (1.49, "D"), (0.5, "D"), (0.49, "F"), (0.0, "F"),
        ):
            self.assertEqual(score_to_grade(score), expected, f"score {score}")

    def test_an_all_na_rollup_stays_na_rather_than_becoming_f(self) -> None:
        self.assertIsNone(average_score(["N/A", "N/A"]))
        self.assertEqual(score_to_grade(average_score(["N/A", "N/A"])), "N/A")

    def test_na_children_do_not_drag_an_average_down(self) -> None:
        self.assertEqual(average_score(["A", "N/A"]), 4.0)
        self.assertEqual(score_to_grade(average_score(["A", "N/A"])), "A")


class VocabularyTests(unittest.TestCase):
    def test_presence_vocabulary_partitions_cleanly(self) -> None:
        self.assertIn(ABSENT_CONTENT_STATUS, CONTENT_STATUSES)
        self.assertTrue(PRESENT_CONTENT_STATUSES < CONTENT_STATUSES)
        self.assertNotIn(ABSENT_CONTENT_STATUS, PRESENT_CONTENT_STATUSES)
        # `not_applicable` is neither present nor absent: the rubric does not ask.
        self.assertEqual(
            CONTENT_STATUSES - PRESENT_CONTENT_STATUSES - {ABSENT_CONTENT_STATUS},
            {"not_applicable"},
        )


if __name__ == "__main__":
    unittest.main()
