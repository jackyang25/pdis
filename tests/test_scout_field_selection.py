"""The reviewer chooses which fields Scout searches; the rest are recorded `not_searched`.

`not_searched` is the third state only code records, beside `no_evidence` and
`not_assessed`, and it means something neither does: nobody looked, because the reviewer
said not to. It is never offered to a model, carries no failure code, and cites nothing.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from api.routes.scout import _response_from_result
from services.scout import (
    FieldSelectionError,
    pipeline,
    result_from_target_review,
)
from services.scout.contract import validate_result_contract
from services.scout.models import (
    NO_EVIDENCE,
    NOT_SEARCHED,
    RECORDED_EVIDENCE_STRENGTHS,
    RECORDED_PRECEDENT,
    RECORDED_PRECEDENT_OUTCOMES,
    VALID_EVIDENCE_STRENGTHS,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
    EvidenceAssessment,
    FunnelStats,
    PrecedentSignal,
    QuantitativeLedger,
    QueryIntent,
    ScoutResult,
    SearchTrace,
)
from tests.test_scout_contract import _result


def _excluded(result: ScoutResult, field: str = "safety") -> ScoutResult:
    """`_result()` with one field left out at review: its records become `not_searched`."""
    result.not_searched_fields = [field]
    result.assessments = [
        assessment if assessment.attribute_ref != field else EvidenceAssessment(
            attribute_ref=field, strength=NOT_SEARCHED,
            doc_target=assessment.doc_target, doc_block_ids=assessment.doc_block_ids,
        )
        for assessment in result.assessments
    ]
    result.precedents = [
        signal if signal.attribute_ref != field else PrecedentSignal(
            attribute_ref=field, precedent=NOT_SEARCHED, outcome=NOT_SEARCHED,
            doc_block_ids=signal.doc_block_ids,
        )
        for signal in result.precedents
    ]
    return result


class VocabularyTests(unittest.TestCase):
    def test_not_searched_is_recorded_and_never_offered_to_a_model(self) -> None:
        for offered, recorded in (
            (VALID_EVIDENCE_STRENGTHS, RECORDED_EVIDENCE_STRENGTHS),
            (VALID_PRECEDENT, RECORDED_PRECEDENT),
            (VALID_PRECEDENT_OUTCOMES, RECORDED_PRECEDENT_OUTCOMES),
        ):
            self.assertNotIn(NOT_SEARCHED, offered)
            self.assertIn(NOT_SEARCHED, recorded)

    def test_not_searched_carries_no_failure_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "failure code"):
            EvidenceAssessment(attribute_ref="efficacy", strength=NOT_SEARCHED,
                               failure_code="provider_error")
        with self.assertRaisesRegex(ValueError, "both precedent axes"):
            PrecedentSignal(attribute_ref="efficacy", precedent=NOT_SEARCHED,
                            outcome=NO_EVIDENCE)


class ContractTests(unittest.TestCase):
    def test_an_excluded_field_holds_not_searched_on_both_records(self) -> None:
        result = _excluded(_result())
        self.assertIs(validate_result_contract(result), result)

    def test_not_searched_is_exactly_the_excluded_fields(self) -> None:
        # A field marked not_searched that the reviewer did not exclude.
        result = _excluded(_result())
        result.not_searched_fields = []
        with self.assertRaisesRegex(ValueError, "not_searched"):
            validate_result_contract(result)
        # An excluded field that holds a verdict anyway.
        result = _result()
        result.not_searched_fields = ["safety"]
        with self.assertRaisesRegex(ValueError, "not_searched"):
            validate_result_contract(result)

    def test_the_selection_names_searchable_fields_once(self) -> None:
        for names, message in ((["unknown"], "searchable"), (["safety", "safety"], "duplicate")):
            with self.subTest(names=names):
                result = _excluded(_result())
                result.not_searched_fields = names
                with self.assertRaisesRegex(ValueError, message):
                    validate_result_contract(result)

    def test_an_excluded_field_has_no_evidence_and_was_not_searched(self) -> None:
        result = _excluded(_result(), field="efficacy")
        # Its insight is still in the result.
        with self.assertRaisesRegex(ValueError, "not searched"):
            validate_result_contract(result)

        result = _excluded(_result())
        result.search_plan = [SearchTrace(attribute_ref="safety", lane="pubmed", query="q")]
        with self.assertRaisesRegex(ValueError, "not searched"):
            validate_result_contract(result)

    def test_not_searched_cites_nothing(self) -> None:
        result = _excluded(_result())
        finding = result.matches[0].insight.supporting_findings[0]
        result.assessments[1].supporting_findings = [finding]
        with self.assertRaisesRegex(ValueError, "cites evidence"):
            validate_result_contract(result)

    def test_a_draft_carries_the_selection_and_no_downstream_records(self) -> None:
        result = _result()
        draft = replace(
            result, phase="target_review", matches=[], assessments=[], precedents=[],
            stats=FunnelStats(queries=0, findings=0, unique_findings=0, insights=0,
                              matches=0, assessments=0),
            not_searched_fields=["safety"],
        )
        self.assertIs(validate_result_contract(draft), draft)


def _draft_payload(not_searched: list[str]) -> dict:
    draft = replace(
        _result(), phase="target_review", matches=[], assessments=[], precedents=[],
        stats=FunnelStats(queries=0, findings=0, unique_findings=0, insights=0,
                          matches=0, assessments=0),
        not_searched_fields=not_searched,
    )
    return _response_from_result(
        draft, org="bmgf", source_type="itpp", intervention_class="vaccine",
        indication="malaria",
    ).model_dump()


class DraftRoundTripTests(unittest.TestCase):
    def test_the_selection_survives_the_draft_round_trip(self) -> None:
        prepared = result_from_target_review(_draft_payload(["safety"]))
        self.assertEqual(prepared.not_searched_fields, ["safety"])

    def test_a_draft_that_searches_nothing_is_refused(self) -> None:
        with self.assertRaisesRegex(FieldSelectionError, "at least one field"):
            result_from_target_review(_draft_payload(["efficacy", "safety"]))

    def test_the_route_refuses_it_before_the_stream_opens(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/scout/continue", json={"draft": _draft_payload(["efficacy", "safety"])},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("at least one field", response.json()["detail"])


class ContinuationTests(unittest.TestCase):
    """Only selected fields reach query planning and every judging stage."""

    def _prepared(self, not_searched: list[str]) -> ScoutResult:
        return result_from_target_review(_draft_payload(not_searched))

    def _continue(self, prepared: ScoutResult, **patches):
        with patch.multiple(pipeline, **patches):
            return pipeline.continue_pipeline(
                prepared,
                config=SimpleNamespace(
                    sources=(), drift_framing="", evidence_framing="", precedent_framing="",
                ),
                openai_client=object(), quantitative_mapping_client=object(),
                retrieval_runtime=object(), org="bmgf", source_type="itpp",
                intervention_class="vaccine", indication="malaria",
            )

    def test_an_excluded_field_is_never_planned_and_is_recorded_not_searched(self) -> None:
        planned: list[str] = []

        def queries(attributes, *_args, **_kwargs):
            planned.extend(attribute.name for attribute in attributes)
            return {}

        result = self._continue(
            self._prepared(["safety"]),
            finalize_quantitative_document_review=lambda variables, ledger: (variables, ledger),
            _extract_queries_all_variables=queries,
        )
        self.assertEqual(planned, ["efficacy"])
        self.assertEqual(
            [(item.attribute_ref, item.strength) for item in result.assessments],
            [("efficacy", NO_EVIDENCE), ("safety", NOT_SEARCHED)],
        )
        self.assertEqual(
            [(item.attribute_ref, item.precedent, item.outcome) for item in result.precedents],
            [("efficacy", NO_EVIDENCE, NO_EVIDENCE), ("safety", NOT_SEARCHED, NOT_SEARCHED)],
        )
        self.assertEqual(result.not_searched_fields, ["safety"])

    def test_judging_stages_receive_only_the_selected_fields(self) -> None:
        source = _result()
        match = source.matches[0]
        insight = match.insight
        seen: dict[str, list[str]] = {}

        def names(stage, value):
            def record(attributes, *_args, **_kwargs):
                seen[stage] = [attribute.name for attribute in attributes]
                return value
            return record

        result = self._continue(
            self._prepared(["safety"]),
            finalize_quantitative_document_review=lambda variables, ledger: (variables, ledger),
            _extract_queries_all_variables=lambda *_a, **_k: {
                "efficacy": [QueryIntent(text="q", tracks=["general"])],
            },
            build_retrieval_intents=lambda *_a, **_k: [],
            plan_requests=lambda *_a, **_k: [],
            build_program_intents=lambda *_a, **_k: [],
            _search_all=lambda *_a, **_k: (
                {"efficacy": list(insight.supporting_findings)}, 1, [],
            ),
            read_announcements=lambda *_a, **_k: SimpleNamespace(
                read=0, named=0, failed=0, failed_by_code={},
            ),
            reconcile_projection_names=lambda *_a, **_k: ({}, None),
            build_development_landscape=lambda *_a, **_k: [],
            build_safety_observations=lambda *_a, **_k: [],
            classify_projection_relationships=names("projections", ([], [])),
            _extract_insights_all_variables=lambda *_a, **_k: ([insight], []),
            _classify_drift_all=lambda *_a, **_k: [match],
            _assess_evidence_all_variables=names("evidence", [source.assessments[0]]),
            _score_conformity_all_variables=names("conformity", []),
            prefill_evidence_review=lambda conformity, *_a, **_k: conformity,
            _classify_precedent_all_variables=names("precedent", [source.precedents[0]]),
        )
        self.assertEqual(
            seen,
            {stage: ["efficacy"] for stage in ("projections", "evidence", "conformity", "precedent")},
        )
        self.assertEqual(
            [(item.attribute_ref, item.strength) for item in result.assessments],
            [("efficacy", "partial"), ("safety", NOT_SEARCHED)],
        )
        self.assertEqual(result.stats.assessments, 2)
        # Published through the schema, the state and the selection both survive.
        published = _response_from_result(
            result, org="bmgf", source_type="itpp", intervention_class="vaccine",
            indication="malaria",
        )
        self.assertEqual(published.not_searched_fields, ["safety"])
        self.assertEqual(published.assessments[1].strength, NOT_SEARCHED)

    def test_a_continuation_that_searches_nothing_is_refused(self) -> None:
        prepared = self._prepared(["safety"])
        prepared.not_searched_fields = ["efficacy", "safety"]
        with self.assertRaises(FieldSelectionError):
            self._continue(prepared, _extract_queries_all_variables=lambda *_a, **_k: {})


class CalibrationTests(unittest.TestCase):
    def test_a_target_of_only_excluded_fields_is_not_calibrated(self) -> None:
        from services.scout.models import (
            QUANTITATIVE_SEMANTIC_FIELDS, ComparisonRule, DocumentSpan, NumericExpression,
            QuantitativeFieldLink, QuantitativeLedgerReview, QuantitativeTarget, SemanticSlot,
        )
        from services.scout.stages.conformity import empty_conformity_scores

        result = _excluded(_result())
        span = DocumentSpan(quote="Field 2 target.", block_ids=[result.blocks[1].id])
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(
                attribute_ref="safety", relation="defines", reason="States safety.",
            )],
            expression=NumericExpression(kind="bound", value=2, comparator="<=", unit="events"),
            role="threshold", quote=span.quote, doc_block_ids=span.block_ids,
            semantic_profile={"measure": SemanticSlot(state="specified", value="events")},
            comparison_contract={
                name: ComparisonRule(
                    mode="exact" if name == "measure" else "unconstrained",
                    scope="events" if name == "measure" else "",
                )
                for name in QUANTITATIVE_SEMANTIC_FIELDS
            },
            provenance_spans=[span], semantic_provenance={"measure": [span]},
            review_status="approved",
        )
        result.variables[1] = replace(
            result.variables[1], quantitative_target_ids=[target.id],
            quantitative_target_status="present",
        )
        result.quantitative_ledger = QuantitativeLedger(
            status="complete", block_ids=[result.blocks[1].id], targets=[target],
            reviews=[QuantitativeLedgerReview(
                unit_id="unit-1", block_id=result.blocks[1].id, quote=span.quote,
                classification="target", attribute_refs=["safety"], reason="Mapped.",
                target_ids=[target.id], review_status="resolved",
            )],
        )
        # The target stays in the ledger and holds no calibration.
        self.assertIs(validate_result_contract(result), result)

        result.conformity = empty_conformity_scores([target])
        with self.assertRaisesRegex(ValueError, "not searched"):
            validate_result_contract(result)

        # Searched, the same target must be calibrated, as before.
        result.conformity = []
        unexcluded = replace(result, not_searched_fields=[])
        unexcluded.assessments = _result().assessments
        unexcluded.precedents = _result().precedents
        with self.assertRaisesRegex(ValueError, "do not cover the target set"):
            validate_result_contract(unexcluded)


if __name__ == "__main__":
    unittest.main()
