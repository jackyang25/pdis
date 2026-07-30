from __future__ import annotations

import unittest
from dataclasses import replace

from services.scout.models import (
    Attribute,
    ComparisonRule,
    ConformityScore,
    EvidenceUnitIdentity,
    Measurement,
    MeasurementSemanticAssessment,
    NumericExpression,
    QuantitativeFieldLink,
    QUANTITATIVE_SEMANTIC_FIELDS,
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
        self.candidate_batches: list[list[str]] = []
        self.system_prompts: list[str] = []
        self.user_messages: list[str] = []

    def call_structured(self, system, message, *_args, **kwargs):
        if self.fail:
            raise RuntimeError("provider unavailable")
        self.system_prompts.append(system)
        self.user_messages.append(message)
        item = kwargs["schema"]["properties"]["reviews"]["items"]["properties"]
        group_id = item["group_id"]["enum"][0]
        candidate_ids = item["decisions"]["items"]["properties"]["candidate_id"]["enum"]
        self.candidate_batches.append(candidate_ids)
        return {"reviews": [{
            "group_id": group_id,
            "decisions": [{
                "candidate_id": candidate_id,
                "decision": (
                    self.decision
                    if self.decision != "admit" or candidate_id == candidate_ids[-1]
                    else "reject"
                ),
                "reason": "Independent review evaluated this source-record candidate.",
            } for candidate_id in candidate_ids],
        }]}


class EvidenceReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            comparison_contract={
                name: ComparisonRule(
                    mode="exact" if name == "measure" else "unconstrained",
                    scope="protective efficacy" if name == "measure" else "",
                    reason="Fixture comparison rule.",
                )
                for name in QUANTITATIVE_SEMANTIC_FIELDS
            },
        )
        self.attribute = Attribute(
            name="efficacy",
            description="Protective efficacy",
            quantitative_target_ids=[self.target.id],
        )
        self.measurements = [_measurement("candidate-a", 70), _measurement("candidate-b", 90)]
        self.score = ConformityScore(
            attribute_refs=["efficacy"],
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
            [self.score], [self.target], _Client(),
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

    def test_each_source_record_is_reviewed_in_its_own_request(self) -> None:
        """An admission recommendation must not see an unrelated source record."""
        other = replace(
            _measurement("candidate-c", 85),
            source_record_id="doi:other",
            evidence_unit_id="doi:other/unit:record",
        )
        score = replace(
            self.score,
            excluded_measurements=[*self.measurements, other],
        )
        client = _Client()

        prefill_evidence_review([score], [self.target], client)

        self.assertEqual(
            sorted(sorted(batch) for batch in client.candidate_batches),
            [["candidate-a", "candidate-b"], ["candidate-c"]],
        )

    def test_failed_or_missing_review_degrades_to_flag(self) -> None:
        for client in (None, _Client(fail=True)):
            with self.subTest(client=client):
                [reviewed] = prefill_evidence_review(
                    [self.score], [self.target], client,
                )
                self.assertTrue(all(
                    item.ai_recommendation == "flag"
                    for item in reviewed.excluded_measurements
                ))

    def test_multiple_admit_recommendations_for_one_unit_fail_closed(self) -> None:
        class _AllAdmitClient(_Client):
            def call_structured(self, _system, _message, *_args, **kwargs):
                item = kwargs["schema"]["properties"]["reviews"]["items"]["properties"]
                group_id = item["group_id"]["enum"][0]
                candidate_ids = item["decisions"]["items"]["properties"]["candidate_id"]["enum"]
                return {"reviews": [{
                    "group_id": group_id,
                    "decisions": [{
                        "candidate_id": candidate_id,
                        "decision": "admit",
                        "reason": "Fixture attempts to admit every alternative.",
                    } for candidate_id in candidate_ids],
                }]}

        [reviewed] = prefill_evidence_review(
            [self.score], [self.target], _AllAdmitClient(),
        )

        self.assertTrue(all(
            item.ai_recommendation == "flag"
            for item in reviewed.excluded_measurements
        ))

    def test_distinct_unit_proposals_from_one_source_are_reviewed_together(self) -> None:
        measurements = [
            replace(
                self.measurements[0],
                evidence_unit_id="doi:study/unit:overall",
                evidence_unit=EvidenceUnitIdentity(
                    status="resolved",
                    group=SemanticSlot(state="specified", value="overall population"),
                    reason="Overall study population.",
                ),
            ),
            replace(
                self.measurements[1],
                evidence_unit_id="doi:study/unit:subgroup",
                evidence_unit=EvidenceUnitIdentity(
                    status="resolved",
                    cohort=SemanticSlot(state="specified", value="booster subgroup"),
                    reason="Booster subgroup within the study population.",
                ),
            ),
        ]
        score = replace(self.score, excluded_measurements=measurements)
        client = _Client()

        [reviewed] = prefill_evidence_review([score], [self.target], client)

        self.assertEqual(client.candidate_batches, [["candidate-a", "candidate-b"]])
        by_id = {item.candidate_id: item for item in reviewed.excluded_measurements}
        self.assertEqual(by_id["candidate-a"].ai_recommendation, "reject")
        self.assertEqual(by_id["candidate-b"].ai_recommendation, "admit")

    def test_review_payload_withholds_target_cutoff_and_comparator(self) -> None:
        client = _Client()

        prefill_evidence_review([self.score], [self.target], client)

        self.assertEqual(len(client.user_messages), 1)
        payload = client.user_messages[0]
        self.assertNotIn("Document target:", payload)
        self.assertNotIn("Exact document quote:", payload)
        self.assertNotIn(self.target.quote, payload)
        self.assertNotIn('"value": 80', payload)
        self.assertNotIn('"comparator": ">="', payload)
        self.assertIn("Comparator measure unit: %", payload)
        self.assertIn("Required target dimensions:", payload)
        self.assertIn("Protective efficacy was 70%.", payload)
        self.assertIn("Protective efficacy was 90%.", payload)

    def test_review_payload_is_invariant_to_target_cutoff_and_direction(self) -> None:
        alternate_target = replace(
            self.target,
            expression=NumericExpression(
                kind="bound", value=5, comparator="<", unit="%"
            ),
            quote="Target efficacy is below 5%.",
        )
        alternate_score = replace(
            self.score,
            target_id=alternate_target.id,
            target_value=5,
            comparator="<",
        )
        original_client = _Client()
        alternate_client = _Client()

        prefill_evidence_review([self.score], [self.target], original_client)
        prefill_evidence_review(
            [alternate_score], [alternate_target], alternate_client,
        )

        self.assertEqual(
            original_client.user_messages,
            alternate_client.user_messages,
        )


if __name__ == "__main__":
    unittest.main()
