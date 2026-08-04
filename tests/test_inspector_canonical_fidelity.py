"""The canonical layer publishes what the model said, and nothing more.

These tests pin the judgments themselves against a fixed set of model replies, so
a change to the merge cannot quietly alter what a document was told while the
shape still validates.
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


def _item(name: str, verdict: str, blocks: list[str], status: str, issue: str) -> dict:
    return {
        "variable_name": name,
        "block_ids": blocks,
        "verdict": verdict,
        "issues": [issue],
        "recommendation": f"Fix {name}.",
        "content_status": status,
    }


class CanonicalFidelityTests(unittest.TestCase):
    def test_the_merge_reports_the_verdicts_the_model_returned(self) -> None:
        merged = _merge_variable_bearing(
            _section(),
            {
                "completeness": {
                    "variable_grades": [
                        _item("Efficacy", "meets", ["b1"], "substantive", "none"),
                        _item("Safety", "for_consideration", ["b1"], "partial", "half filled"),
                    ]
                },
                "adherence": {
                    "variable_grades": [
                        _item("Efficacy", "for_consideration", ["b1"], "substantive", "naming"),
                        _item("Safety", "critical", ["b2"], "partial", "token"),
                    ]
                },
                "rigor": {
                    "variable_grades": [
                        _item("Efficacy", "critical", ["b2"], "substantive", "vague"),
                        _item("Safety", "meets", ["b1"], "partial", "fine"),
                    ]
                },
            },
        )

        actual = {
            variable.variable_name: {
                dimension: (
                    variable.dimensions[dimension].verdict,
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
                    "completeness": ("meets", ["none"], "Fix Efficacy.", ["b1"]),
                    "adherence": ("for_consideration", ["naming"], "Fix Efficacy.", ["b1"]),
                    "rigor": ("critical", ["vague"], "Fix Efficacy.", ["b2"]),
                },
                "Safety": {
                    "completeness": ("for_consideration", ["half filled"], "Fix Safety.", ["b1"]),
                    "adherence": ("critical", ["token"], "Fix Safety.", ["b2"]),
                    "rigor": ("meets", ["fine"], "Fix Safety.", ["b1"]),
                },
            },
        )

    def test_absence_overrides_the_model_on_exactly_three_axes(self) -> None:
        merged = _merge_variable_bearing(
            _section(),
            {
                dimension: {
                    "variable_grades": [
                        _item("Efficacy", "meets", ["b1"], "substantive", "none"),
                        _item("Safety", "for_consideration", [], ABSENT_CONTENT_STATUS, "ignored"),
                    ]
                }
                for dimension in DIMENSIONS
            },
        )

        safety = merged.variable_grades[1]
        # The model's own verdicts for an absent variable are replaced, because
        # absent content cannot be complete, well-formed, or rigorous.
        self.assertEqual(safety.dimensions["completeness"].verdict, "critical")
        self.assertEqual(safety.dimensions["adherence"].verdict, "critical")
        self.assertEqual(safety.dimensions["rigor"].verdict, "not_applicable")
        self.assertEqual(safety.cited_block_ids, [])
        # A present sibling is untouched by its neighbour's absence.
        self.assertEqual(
            merged.variable_grades[0].dimensions["completeness"].verdict, "meets"
        )


class NoRolledUpVerdictTests(unittest.TestCase):
    """A section that has variables publishes counts, not a verdict of its own."""

    def test_a_variable_bearing_section_carries_no_verdict(self) -> None:
        merged = _merge_variable_bearing(
            _section(),
            {
                dimension: {
                    "variable_grades": [
                        _item("Efficacy", "critical", ["b1"], "substantive", "vague"),
                        _item("Safety", "meets", ["b2"], "substantive", ""),
                    ]
                }
                for dimension in DIMENSIONS
            },
        )

        self.assertEqual(
            {name: assessment.verdict for name, assessment in merged.dimensions.items()},
            {dimension: "not_applicable" for dimension in DIMENSIONS},
        )
        self.assertEqual(
            merged.gap_counts, {"critical": 3, "for_consideration": 0}
        )


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
