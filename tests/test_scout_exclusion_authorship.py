"""Why a measurement was left out, kept separable by who established it.

Two different kinds of claim were joined into one dot-separated paragraph:

    Regimen compatibility is unknown: the quote does not state the injection spacing ...
    - numeric expression is range, not an atomic scalar

The first is a model's reading and can be wrong. The second is a check over the source's own
numbers and cannot be. Joined, a reader cannot tell which is which, and the interface rendered
both in the tone that means "a model wrote this".

`exclusion_reasons` stays the complete list so nothing reading it loses anything.
`structural_reasons` carries the deterministic half on its own.

The fixtures come from `test_scout_lineage`, which already builds these objects the way the
pipeline does; a second set of constructors here would drift from the real shapes.
"""

from __future__ import annotations

import unittest

from services.scout.models import (
    Measurement,
    NumericExpression,
    QuantitativeFieldLink,
    QuantitativeTarget,
)
from services.scout.stages.conformity import _partition_cohort

from tests.test_scout_lineage import (
    comparison_contract,
    same_comparability,
    semantic_assessment,
    semantic_profile,
)


def target(unit: str = "injections") -> QuantitativeTarget:
    profile = semantic_profile("injections administered")
    return QuantitativeTarget(
        field_links=[
            QuantitativeFieldLink(
                attribute_ref="drug.efficacy", relation="defines", reason="Test fixture."
            )
        ],
        expression=NumericExpression(kind="bound", value=4, comparator="<=", unit=unit),
        role="threshold",
        quote="No more than 4 injections.",
        doc_block_ids=["document/b-0001"],
        semantic_profile=profile,
        comparison_contract=comparison_contract(profile),
    )


def candidate(*, kind: str = "range", unit: str = "injections") -> Measurement:
    # A range carries its ends; a point estimate carries a value. The model rejects either
    # shape being given the other's fields, so the fixture has to match the kind.
    bounds = (
        {"lower": 1.0, "upper": 3.0}
        if kind in {"range", "confidence_interval"}
        else {"value": 2.0}
    )
    return Measurement(
        expression=NumericExpression(kind=kind, unit=unit, **bounds),
        semantic_assessment=semantic_assessment(
            source_profile=semantic_profile("injections administered"),
            comparability=same_comparability(),
        ),
        candidate_id="qm-fixture",
        source_record_id="doi:10.1/fixture",
        source_quote="one to three injections were given",
        url="https://example.org/a",
    )


class StructuralReasonsTests(unittest.TestCase):
    def test_a_check_is_recorded_apart_from_the_full_list(self):
        _, excluded = _partition_cohort([candidate()], target())
        self.assertEqual(len(excluded), 1)
        item = excluded[0]
        self.assertTrue(item.structural_reasons, "the check was not recorded on its own")
        # The full list still holds it, so nothing reading `exclusion_reasons` loses it.
        for reason in item.structural_reasons:
            self.assertIn(reason, item.exclusion_reasons)

    def test_a_check_states_the_fact_not_the_internal_requirement(self):
        """"not an atomic scalar" named the rule. A reader needs the fact about their source."""
        _, excluded = _partition_cohort([candidate()], target())
        joined = " ".join(excluded[0].structural_reasons).casefold()
        self.assertNotIn("atomic", joined)
        self.assertNotIn("scalar", joined)
        self.assertIn("single number", joined)

    def test_a_unit_mismatch_names_both_units(self):
        _, excluded = _partition_cohort(
            [candidate(kind="point_estimate", unit="mL")], target("injections")
        )
        joined = " ".join(excluded[0].structural_reasons)
        self.assertIn("mL", joined)
        self.assertIn("injections", joined)

    def test_a_comparable_measurement_records_no_check(self):
        """The field is empty rather than absent, so the interface has one thing to test."""
        included, excluded = _partition_cohort(
            [candidate(kind="point_estimate")], target()
        )
        for item in included + excluded:
            self.assertEqual(item.structural_reasons, [])

    def test_a_reason_is_never_stated_twice(self):
        _, excluded = _partition_cohort([candidate()], target())
        reasons = excluded[0].exclusion_reasons
        self.assertEqual(len(reasons), len(set(reasons)), reasons)

    def test_no_reason_carries_an_em_dash(self):
        """Reader-facing. An em dash hides whether a clause explains, qualifies, or restarts."""
        _, excluded = _partition_cohort([candidate()], target())
        for reason in excluded[0].exclusion_reasons:
            self.assertNotIn("—", reason)

    def test_no_reason_prefixes_a_status_the_interface_already_shows(self):
        _, excluded = _partition_cohort([candidate()], target())
        for reason in excluded[0].exclusion_reasons:
            self.assertFalse(reason.startswith("semantic status:"), reason)


if __name__ == "__main__":
    unittest.main()
