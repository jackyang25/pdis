"""Separation between an AI source verdict and a mapping failure.

A source disposition carries one of two different kinds of claim: what the model
concluded about a source, or that the pipeline never obtained a usable
conclusion. These tests hold those channels apart so a processing gap can never
be read as evidentiary ambiguity.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.scout.ai_contracts import source_measurement_batch
from services.scout.models import (
    ComparisonRule,
    Finding,
    Insight,
    NumericExpression,
    QUANTITATIVE_SEMANTIC_FIELDS,
    QuantitativeFieldLink,
    QuantitativeTarget,
    SemanticSlot,
    SourcePassageDisposition,
)
from services.scout.stages.conformity import (
    _SourcePassage,
    _map_source_passage_batch,
    _validated_source_decisions,
)
from shared.ai import ResponseRefusedError, ResponseTruncatedError


QUOTE = "Protective efficacy was 55% in the overall population."


def _target() -> QuantitativeTarget:
    return QuantitativeTarget(
        field_links=[QuantitativeFieldLink(
            attribute_ref="efficacy",
            relation="defines",
            reason="Test fixture.",
        )],
        expression=NumericExpression(
            kind="bound", value=80, comparator=">=", unit="%"
        ),
        role="threshold",
        quote="Target efficacy is at least 80%.",
        doc_block_ids=["document/b-0003"],
        semantic_profile={
            "measure": SemanticSlot(state="specified", value="protective efficacy")
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


def _passage() -> _SourcePassage:
    source_finding = Finding(
        url="https://doi.org/10.1000/example",
        title="Example trial",
        query="protective efficacy",
        retrieved_at=datetime.now(timezone.utc),
        excerpt=QUOTE,
        source="pubmed",
    )
    return _SourcePassage(
        id="sp-one",
        insight=Insight(
            statement="The study reports overall efficacy.",
            supporting_findings=[source_finding],
            attribute_ref="efficacy",
        ),
        finding=source_finding,
        text=QUOTE,
        record_id="doi:10.1000/example",
        identity_status="canonical",
    )


class SourceDecisionContractTests(unittest.TestCase):
    """The published schema must state every constraint the validator enforces."""

    def test_schema_requires_a_non_empty_reason_everywhere_code_does(self) -> None:
        contract = source_measurement_batch({"measure"}, ["sp-one"])
        source = contract.schema["properties"]["sources"]["items"]["anyOf"][0]["properties"]

        self.assertEqual(source["reason"].get("minLength"), 1)
        self.assertEqual(source["reason"].get("pattern"), "\\S")
        self.assertEqual(
            source["evidence_unit_partition"]["properties"]["reason"].get("minLength"),
            1,
        )


class SourceDecisionRetentionTests(unittest.TestCase):
    """A verdict survives whatever its unused siblings do."""

    def test_no_measurement_verdict_survives_an_unusable_unit_partition(self) -> None:
        """Partitioning is meaningless with no measurements to partition."""
        passage = _passage()

        mapped, dispositions, issues = _validated_source_decisions(
            [{
                "source_id": passage.id,
                "status": "no_relevant_measurement",
                "reason": "The passage reports a different endpoint.",
                "evidence_unit_partition": {"status": "", "reason": ""},
                "measurements": [],
            }],
            passages={passage.id: passage},
            target=_target(),
        )

        self.assertEqual(issues, {})
        self.assertEqual(mapped, [])
        self.assertEqual(len(dispositions), 1)
        self.assertEqual(dispositions[0].status, "no_relevant_measurement")
        self.assertEqual(dispositions[0].failure_code, "")

    def test_found_measurements_still_require_a_valid_unit_partition(self) -> None:
        passage = _passage()

        _mapped, dispositions, issues = _validated_source_decisions(
            [{
                "source_id": passage.id,
                "status": "measurements_found",
                "reason": "The passage reports the target measure.",
                "evidence_unit_partition": {"status": "", "reason": ""},
                "measurements": [],
            }],
            passages={passage.id: passage},
            target=_target(),
        )

        self.assertEqual(dispositions, [])
        self.assertEqual(issues, {passage.id: "invalid_evidence_unit_partition"})


class RecordedMappingFailureTests(unittest.TestCase):
    def test_a_refusal_is_recorded_per_source_and_never_retried(self) -> None:
        calls: list[int] = []

        class Refuses:
            def call_structured(self, _system, _message, max_tokens, **_kwargs):
                calls.append(max_tokens)
                raise ResponseRefusedError("declined")

        result = _map_source_passage_batch(
            (), _target(), [_passage()], Refuses(),
            indication="malaria", intervention_class="vaccine", max_tokens=100,
        )

        self.assertEqual(len(calls), 1)
        (disposition,) = result.dispositions
        self.assertEqual((disposition.status, disposition.failure_code),
                         ("not_assessed", "response_refused"))


class TruncatedMappingTests(unittest.TestCase):
    def test_a_twice_truncated_batch_is_recorded_per_source_with_its_code(self) -> None:
        budgets: list[int] = []

        class Truncates:
            def call_structured(self, _system, _message, max_tokens, **_kwargs):
                budgets.append(max_tokens)
                raise ResponseTruncatedError("cut off")

        result = _map_source_passage_batch(
            (), _target(), [_passage()], Truncates(),
            indication="malaria", intervention_class="vaccine", max_tokens=100,
        )

        self.assertEqual(budgets, [100, 200])
        (disposition,) = result.dispositions
        self.assertEqual(disposition.status, "not_assessed")
        self.assertEqual(disposition.failure_code, "response_truncated")


class MappingFailureChannelTests(unittest.TestCase):
    """A pipeline failure is not one of the model's three verdicts."""

    def test_unusable_decision_is_not_assessed_rather_than_uncertain(self) -> None:
        disposition = SourcePassageDisposition(
            source_id="sp-one",
            status="not_assessed",
            reason="Source mapping rejected after one retry.",
            failure_code="invalid_model_response",
        )

        self.assertEqual(disposition.status, "not_assessed")
        self.assertEqual(disposition.failure_code, "invalid_model_response")

    def test_not_assessed_requires_a_machine_readable_failure_code(self) -> None:
        with self.assertRaises(ValueError):
            SourcePassageDisposition(
                source_id="sp-one",
                status="not_assessed",
                reason="Source mapping rejected after one retry.",
            )

    def test_a_failure_code_is_one_of_the_shared_codes(self) -> None:
        """The causes stay in the prose; the code is the vocabulary every stage uses."""
        with self.assertRaises(ValueError):
            SourcePassageDisposition(
                source_id="sp-one",
                status="not_assessed",
                reason="Source mapping rejected [source_quote_not_found] after one retry.",
                failure_code="source_quote_not_found",
            )

    def test_a_model_verdict_cannot_carry_a_failure_code(self) -> None:
        with self.assertRaises(ValueError):
            SourcePassageDisposition(
                source_id="sp-one",
                status="no_relevant_measurement",
                reason="The passage reports a different endpoint.",
                failure_code="invalid_model_response",
            )


if __name__ == "__main__":
    unittest.main()
