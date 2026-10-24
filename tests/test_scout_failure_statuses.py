"""A stage that obtained no verdict says so, with a code, and keeps its subject.

Each Scout axis offers the model a closed vocabulary. A failed stage used to file
its subject under one of those values - drift as `unrelated`, grounding and
precedent as `unknown`, the context check as `uncertain` - which reads as
something the evidence said. `not_assessed` is never offered to a model, so only
code can record it, and it always carries a machine-readable failure code.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import httpx
import openai

from api.schemas import (
    DevelopmentProgramOut,
    DocumentContextValidationOut,
    EvidenceAssessmentOut,
    MatchOut,
    PrecedentOut,
)
from services.scout.ai_contracts import (
    context_validation,
    drift_relation,
    evidence_assessment,
    precedent_assessment,
    projection_relationship_batch,
)
from services.scout.models import (
    NO_EVIDENCE,
    NOT_ASSESSED,
    Attribute,
    DevelopmentProgram,
    DocumentContextValidation,
    EvidenceAssessment,
    Insight,
    Match,
    PrecedentSignal,
    matches_to_dicts,
)
from services.scout.stages.context_validator import validate_document_context
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.evidence_assessor import assess_evidence
from services.scout.stages.precedent_classifier import classify_precedent
from services.scout.stages.projection_classifier import (
    classify_projection_relationships,
)
from services.searcher import Finding
from shared.ai import ResponseRefusedError, ResponseTruncatedError

DOCUMENT = "[block:document/b-0001]\nTarget efficacy is at least 80%."


def provider_down() -> openai.APIError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://provider.test"))


class _Client:
    """Replays payloads (or raises exceptions) in order, recording each request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        self.calls.append({"max_tokens": max_tokens, **kwargs})
        if not self.replies:
            raise AssertionError("unexpected model call")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _insight() -> Insight:
    return Insight(
        statement="A comparable vaccine reached 85% efficacy.",
        supporting_findings=[Finding(
            url="https://example.test/a",
            title="Trial",
            query="malaria vaccine efficacy",
            retrieved_at=datetime.now(timezone.utc),
            excerpt="Efficacy was 85%.",
            source="pubmed",
        )],
        attribute_ref="efficacy",
    )


def _attribute() -> Attribute:
    return Attribute(
        "efficacy",
        "Target product efficacy",
        block_ids=["document/b-0001"],
        document_target="Target efficacy is at least 80%.",
        target_resolved=True,
    )


def _enum(schema: dict) -> set[str]:
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            found.update(value for value in node.get("enum", []) if isinstance(value, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(schema)
    return found


class OfferedVocabularyTests(unittest.TestCase):
    def test_no_model_is_offered_the_pipeline_status(self) -> None:
        for contract in (
            drift_relation(["document/b-0001"]),
            evidence_assessment(1),
            precedent_assessment(1),
            context_validation(["document/b-0001"]),
            projection_relationship_batch(["dp-a"]),
        ):
            with self.subTest(contract=contract.name):
                self.assertNotIn(NOT_ASSESSED, _enum(contract.schema))


class DriftFailureTests(unittest.TestCase):
    def _classify(self, client):
        return classify_drift(
            DOCUMENT, _insight(), client,
            indication="malaria", intervention_class="vaccine",
        )

    def test_an_invalid_relation_is_not_assessed_rather_than_unrelated(self) -> None:
        uncited = {"match": {
            "relation": "confirms", "reason": "It supports the target.",
            "doc_block_ids": [],
        }}
        match = self._classify(_Client(uncited, uncited))

        self.assertEqual(match.relation, NOT_ASSESSED)
        self.assertEqual(match.failure_code, "invalid_model_response")
        self.assertEqual(match.doc_block_ids, [])

    def test_a_truncated_reply_is_retried_with_more_room(self) -> None:
        valid = {"match": {
            "relation": "confirms", "reason": "It supports the target.",
            "doc_block_ids": ["document/b-0001"],
        }}
        client = _Client(ResponseTruncatedError("cut off"), valid)

        match = self._classify(client)

        self.assertEqual(match.relation, "confirms")
        self.assertEqual(client.calls[1]["max_tokens"], 2 * client.calls[0]["max_tokens"])

    def test_repeated_truncation_keeps_its_code(self) -> None:
        client = _Client(ResponseTruncatedError("cut off"), ResponseTruncatedError("cut off"))
        match = self._classify(client)
        self.assertEqual((match.relation, match.failure_code), (NOT_ASSESSED, "response_truncated"))

    def test_provider_failures_and_refusals_are_recorded_with_their_code(self) -> None:
        for reply, code in ((provider_down(), "provider_error"),
                            (ResponseRefusedError("declined"), "response_refused")):
            with self.subTest(code=code):
                client = _Client(reply)
                match = self._classify(client)
                self.assertEqual((match.relation, match.failure_code), (NOT_ASSESSED, code))
                self.assertEqual(len(client.calls), 1)

    def test_a_programming_error_still_stops_the_run(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "bug"):
            self._classify(_Client(RuntimeError("bug")))

    def test_the_insight_follows_the_binding_and_its_images(self) -> None:
        valid = {"match": {"relation": "unrelated", "reason": "Off-topic.", "doc_block_ids": []}}
        client = _Client(valid)
        self._classify(client)
        self.assertIn("A comparable vaccine reached 85% efficacy.", client.calls[0]["trailing_text"])

    def test_the_failure_code_reaches_the_wire(self) -> None:
        match = self._classify(_Client(None, None))
        wire = MatchOut.model_validate(matches_to_dicts([match])[0])
        self.assertEqual((wire.relation, wire.failure_code), (NOT_ASSESSED, "invalid_model_response"))


class EvidenceFailureTests(unittest.TestCase):
    def test_an_invalid_assessment_is_not_assessed(self) -> None:
        uncited = {"assessment": {
            "strength": "partial", "supporting_insight_indices": [], "reason": "Some.",
        }}
        result = assess_evidence(
            _attribute(), DOCUMENT, [_insight()], _Client(uncited, uncited),
            indication="malaria", intervention_class="vaccine",
        )

        self.assertEqual(result.strength, NOT_ASSESSED)
        self.assertEqual(result.failure_code, "invalid_model_response")
        self.assertEqual(result.supporting_insight_ids, [])
        self.assertEqual(result.doc_target, "Target efficacy is at least 80%.")

    def test_no_insights_is_no_evidence_without_a_model_call_or_a_code(self) -> None:
        """Not the model's `unknown` and not a failure: nothing was there to weigh."""
        client = _Client()
        result = assess_evidence(
            _attribute(), DOCUMENT, [], client,
            indication="malaria", intervention_class="vaccine",
        )
        self.assertEqual((result.strength, result.failure_code, result.reason),
                         (NO_EVIDENCE, "", ""))
        self.assertEqual(client.calls, [])


class PrecedentFailureTests(unittest.TestCase):
    def test_an_invalid_classification_leaves_both_axes_not_assessed(self) -> None:
        uncited = {"assessment": {
            "precedent": "direct", "outcome": "favorable", "reason": "Prior work.",
            "coverage_insight_indices": [], "outcome_insight_indices": [],
        }}
        signal = classify_precedent(
            _attribute(), DOCUMENT, [_insight()], _Client(uncited, uncited),
            indication="malaria", intervention_class="vaccine",
        )

        self.assertEqual((signal.precedent, signal.outcome), (NOT_ASSESSED, NOT_ASSESSED))
        self.assertEqual(signal.failure_code, "invalid_model_response")
        self.assertEqual(signal.supporting_insight_ids, [])

    def test_no_insights_keeps_the_variable_as_no_evidence(self) -> None:
        """The subject is kept, never dropped, and no model is asked to guess."""
        client = _Client()
        signal = classify_precedent(
            _attribute(), DOCUMENT, [], client,
            indication="malaria", intervention_class="vaccine",
        )
        self.assertEqual((signal.precedent, signal.outcome), (NO_EVIDENCE, NO_EVIDENCE))
        self.assertEqual(client.calls, [])


class ContextValidationFailureTests(unittest.TestCase):
    def test_an_unanswered_check_is_not_assessed_rather_than_uncertain(self) -> None:
        validation = validate_document_context(
            DOCUMENT, _Client(None, None), indication="malaria",
        )
        self.assertEqual(validation.status, NOT_ASSESSED)
        self.assertEqual(validation.failure_code, "invalid_model_response")
        self.assertEqual(
            DocumentContextValidationOut.model_validate(validation.__dict__).status,
            NOT_ASSESSED,
        )

    def test_an_uncited_verdict_is_retried_before_it_is_given_up(self) -> None:
        verdict = {"status": "match", "document_indication": "malaria", "reason": "Malaria."}
        uncited = {"validation": {**verdict, "block_ids": []}}
        cited = {"validation": {**verdict, "block_ids": ["document/b-0001"]}}
        validation = validate_document_context(
            DOCUMENT, _Client(uncited, cited), indication="malaria",
        )
        self.assertEqual((validation.status, validation.failure_code), ("match", ""))


class ProjectionFailureTests(unittest.TestCase):
    def _classify(self, client):
        programs, _ = classify_projection_relationships(
            [_attribute()], [DevelopmentProgram(name="A", projection_id="dp-a")], [],
            client, indication="malaria", intervention_class="vaccine",
        )
        return programs[0]

    def test_an_invalid_relationship_is_retried_then_not_assessed(self) -> None:
        invalid = {"relationships": [
            {"projection_id": "dp-a", "target_relationship": "direct", "reason": ""},
        ]}
        client = _Client(invalid, invalid)

        program = self._classify(client)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(program.target_relationship, NOT_ASSESSED)
        self.assertEqual(program.target_relationship_failure_code, "invalid_model_response")

    def test_a_provider_failure_is_recorded_not_relabelled_unknown(self) -> None:
        program = self._classify(_Client(provider_down()))
        self.assertEqual(
            (program.target_relationship, program.target_relationship_failure_code),
            (NOT_ASSESSED, "provider_error"),
        )
        DevelopmentProgramOut.model_validate(program.__dict__ | {"supporting_findings": []})


class PairingTests(unittest.TestCase):
    def test_a_failure_code_belongs_to_exactly_not_assessed(self) -> None:
        insight = _insight()
        with self.assertRaises(ValueError):
            Match(insight=insight, relation=NOT_ASSESSED, reason="Failed.")
        with self.assertRaises(ValueError):
            Match(insight=insight, relation="unrelated", reason="Off-topic.",
                  failure_code="invalid_model_response")
        with self.assertRaises(ValueError):
            EvidenceAssessment(attribute_ref="efficacy", strength=NOT_ASSESSED)
        with self.assertRaises(ValueError):
            PrecedentSignal(attribute_ref="efficacy", precedent=NOT_ASSESSED,
                            outcome="unknown", failure_code="provider_error")
        with self.assertRaises(ValueError):
            DocumentContextValidation(status="uncertain", configured_indication="malaria",
                                      failure_code="provider_error")

    def test_no_evidence_carries_no_failure_code(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceAssessment(attribute_ref="efficacy", strength=NO_EVIDENCE,
                               failure_code="provider_error")
        with self.assertRaises(ValueError):
            PrecedentSignal(attribute_ref="efficacy", precedent=NO_EVIDENCE, outcome="unknown")

    def test_wire_models_accept_the_pipeline_status(self) -> None:
        EvidenceAssessmentOut.model_validate({
            "attribute_ref": "efficacy", "strength": NOT_ASSESSED, "reason": "Failed.",
            "supporting_findings": [], "failure_code": "response_truncated",
        })
        PrecedentOut.model_validate({
            "attribute_ref": "efficacy", "precedent": NOT_ASSESSED,
            "outcome": NOT_ASSESSED, "failure_code": "provider_error",
        })


if __name__ == "__main__":
    unittest.main()
