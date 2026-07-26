from __future__ import annotations

import unittest

from services.scout.models import (
    Attribute,
    ConformityScore,
    EvidenceUnitIdentity,
    Measurement,
    MeasurementSemanticAssessment,
    NumericExpression,
    QuantitativeTarget,
    SemanticDimensionAssessment,
    SemanticSlot,
    TernaryDecision,
)
from services.scout.stages.evidence_reviewer import prefill_evidence_review


def _assessment() -> MeasurementSemanticAssessment:
    return MeasurementSemanticAssessment(
        source_ownership=TernaryDecision(state="yes"),
        dimensions={
            name: SemanticDimensionAssessment(
                source=SemanticSlot(
                    state="specified" if name == "measure" else "not_specified",
                    value="protective efficacy" if name == "measure" else "",
                ),
                compatibility=TernaryDecision(state="yes"),
            )
            for name in (
                "measure",
                "endpoint",
                "intervention",
                "population",
                "regimen",
                "time_horizon",
                "statistic",
                "conditions",
            )
        },
    )


def _measurement(candidate_id: str, value: float) -> Measurement:
    return Measurement(
        candidate_id=candidate_id,
        expression=NumericExpression(kind="point_estimate", value=value, unit="%"),
        url="https://example.test/study",
        source_quote=f"Protective efficacy was {value:g}%.",
        source_record_id="doi:study",
        evidence_unit_id="doi:study/unit:record",
        evidence_unit=EvidenceUnitIdentity(),
        semantic_assessment=_assessment(),
        semantic_status="comparable",
        semantic_reason="Every required dimension is compatible.",
    )


class _Client:
    def __init__(self, decision: str = "admit", fail: bool = False) -> None:
        self.decision = decision
        self.fail = fail

    def call_structured(self, _system, _message, *_args, **kwargs):
        if self.fail:
            raise RuntimeError("provider unavailable")
        item = kwargs["schema"]["properties"]["reviews"]["items"]["properties"]
        group_id = item["group_id"]["enum"][0]
        candidate_ids = [value for value in item["selected_candidate_id"]["enum"] if value]
        return {"reviews": [{
            "group_id": group_id,
            "decision": self.decision,
            "selected_candidate_id": candidate_ids[-1] if self.decision == "admit" else "",
            "reason": "Independent review selected the direct comparator.",
        }]}


class EvidenceReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0001"],
            semantic_profile={
                "measure": SemanticSlot(
                    state="specified", value="protective efficacy"
                )
            },
            comparison_dimensions=["measure"],
        )
        self.attribute = Attribute(
            name="efficacy",
            description="Protective efficacy",
            quantitative_targets=[self.target],
        )
        self.measurements = [_measurement("candidate-a", 70), _measurement("candidate-b", 90)]
        self.score = ConformityScore(
            attribute_ref="efficacy",
            target_id=self.target.id,
            target_role="threshold",
            target_value=80,
            comparator=">=",
            unit="%",
            target_meeting_count=0,
            target_meeting_rate=0,
            verdict="No admitted comparators",
            excluded_measurements=self.measurements,
        )

    def test_independent_review_selects_one_existing_candidate_without_admitting_it(self) -> None:
        [reviewed] = prefill_evidence_review(
            [self.score], [self.attribute], _Client(),
        )
        by_id = {item.candidate_id: item for item in reviewed.excluded_measurements}
        self.assertEqual(by_id["candidate-a"].ai_recommendation, "reject")
        self.assertEqual(by_id["candidate-b"].ai_recommendation, "admit")
        self.assertTrue(all(
            item.admission_status == "needs_review"
            for item in reviewed.excluded_measurements
        ))
        self.assertEqual(
            by_id["candidate-b"].source_quote,
            self.measurements[1].source_quote,
        )

    def test_failed_or_missing_review_degrades_to_flag(self) -> None:
        for client in (None, _Client(fail=True)):
            with self.subTest(client=client):
                [reviewed] = prefill_evidence_review(
                    [self.score], [self.attribute], client,
                )
                self.assertTrue(all(
                    item.ai_recommendation == "flag"
                    for item in reviewed.excluded_measurements
                ))


if __name__ == "__main__":
    unittest.main()
