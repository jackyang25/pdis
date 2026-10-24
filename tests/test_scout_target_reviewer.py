from __future__ import annotations

import threading
import time
import unittest
import json
from dataclasses import asdict
from dataclasses import replace

import httpx
import openai

from services.chunker import ContentBlock
from services.scout.models import (
    Attribute,
    ComparisonRule,
    DocumentSpan,
    NumericExpression,
    QUANTITATIVE_SEMANTIC_FIELDS,
    QuantitativeLedger,
    QuantitativeFieldLink,
    QuantitativeTarget,
    SemanticSlot,
)
from services.scout.stages.target_reviewer import prefill_target_review


BLOCK_ID = "document/b-0001"


def _target(
    value: float,
    quote: str,
    *,
    attribute_ref: str = "vaccine.efficacy",
) -> QuantitativeTarget:
    return QuantitativeTarget(
        field_links=[QuantitativeFieldLink(attribute_ref=attribute_ref, relation="defines", reason="Test fixture.")],
        expression=NumericExpression(
            kind="bound",
            value=value,
            comparator=">",
            unit="%",
        ),
        role="threshold",
        quote=quote,
        doc_block_ids=[BLOCK_ID],
        semantic_profile={
            "measure": SemanticSlot(state="specified", value="protective efficacy"),
        },
        comparison_contract={
            name: ComparisonRule(
                mode="exact" if name == "measure" else "unconstrained",
                scope="protective efficacy" if name == "measure" else "",
                reason="Fixture comparison rule.",
            )
            for name in QUANTITATIVE_SEMANTIC_FIELDS
        },
        provenance_spans=[DocumentSpan(quote=quote, block_ids=[BLOCK_ID])],
        review_status="needs_review",
    )


class _Client:
    def __init__(self, reviews: list[dict] | None = None, failure: Exception | None = None):
        self.reviews = reviews or []
        self.failure = failure
        self.user_message = ""
        self.document = ""

    def call_structured(self, _system, user_message, *_args, **kwargs):
        # The document leads the request; the proposal follows its images.
        self.document = user_message
        self.user_message = kwargs.get("trailing_text", "")
        if self.failure:
            raise self.failure
        return {"reviews": self.reviews}


class _ConcurrentClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def call_structured(self, _system, _user_message, *_args, **kwargs):
        target_ids = kwargs["schema"]["properties"]["reviews"]["items"][
            "properties"
        ]["target_id"]["enum"]
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.03)
            return {
                "reviews": [
                    {
                        "target_id": target_id,
                        "decision": "confirm",
                        "reason": "The cited passage explicitly states the target.",
                    }
                    for target_id in target_ids
                ]
            }
        finally:
            with self._lock:
                self.active -= 1


class TargetReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.quote = "Threshold efficacy must exceed 80% at 12 months."
        self.target = _target(80, self.quote)
        self.attribute = Attribute(
            name="vaccine.efficacy",
            description="Protective efficacy target",
            document_target=self.quote,
            document_spans=[DocumentSpan(quote=self.quote, block_ids=[BLOCK_ID])],
            target_resolved=True,
            quantitative_target_ids=[self.target.id],
        )
        self.block = ContentBlock(
            id=BLOCK_ID,
            doc_id="document",
            ordinal=1,
            block_type="paragraph",
            content=self.quote + " Background incidence was 14% in a cited study.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        self.ledger = QuantitativeLedger(
            status="complete",
            block_ids=[BLOCK_ID],
            targets=[self.target],
        )

    def test_prefill_selects_only_existing_targets_and_preserves_canonical_data(self) -> None:
        client = _Client([{
            "target_id": self.target.id,
            "decision": "confirm",
            "reason": "The passage explicitly states a threshold requirement.",
        }])

        attributes, ledger = prefill_target_review(
            [self.attribute], self.ledger, [self.block], client,
        )

        reviewed = ledger.targets[0]
        self.assertEqual(reviewed.id, self.target.id)
        self.assertEqual(reviewed.expression, self.target.expression)
        self.assertEqual(reviewed.provenance_spans, self.target.provenance_spans)
        self.assertEqual(reviewed.ai_recommendation, "confirm")
        self.assertEqual(reviewed.review_status, "needs_review")
        self.assertEqual(attributes[0].quantitative_target_ids, [reviewed.id])
        self.assertIn("Background incidence was 14%", client.document)
        self.assertNotIn("[target:", client.document)
        expression_line = next(line for line in client.user_message.splitlines() if line.startswith("Numeric expression: "))
        self.assertEqual(json.loads(expression_line.removeprefix("Numeric expression: ")), asdict(self.target.expression))
        self.assertIn("Target role: threshold", client.user_message)

    def test_failed_ai_review_degrades_to_manual_review_with_its_code(self) -> None:
        for client, code in (
            (_Client([]), "invalid_model_response"),
            (_Client(failure=openai.APIConnectionError(request=httpx.Request("POST", "https://x"))),
             "provider_error"),
        ):
            with self.subTest(code=code):
                _, ledger = prefill_target_review(
                    [self.attribute], self.ledger, [self.block], client,
                )
                self.assertEqual(ledger.targets[0].ai_recommendation, "unavailable")
                self.assertEqual(ledger.targets[0].ai_review_failure_code, code)
                self.assertEqual(ledger.targets[0].review_status, "needs_review")

    def test_a_programming_error_is_not_recorded_as_a_review_failure(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "bug"):
            prefill_target_review(
                [self.attribute], self.ledger, [self.block], _Client(failure=RuntimeError("bug")),
            )

    def test_each_target_is_reviewed_in_its_own_request(self) -> None:
        """A target decision must not see an unrelated proposal in its prompt."""
        class _RecordingClient:
            def __init__(self) -> None:
                self.batches: list[list[str]] = []

            def call_structured(self, _system, _user_message, *_args, **kwargs):
                batch = list(kwargs["schema"]["properties"]["reviews"][
                    "items"
                ]["properties"]["target_id"]["enum"])
                self.batches.append(batch)
                return {"reviews": [
                    {"target_id": target_id, "decision": "flag", "reason": "Check the role."}
                    for target_id in batch
                ]}

        targets = [
            _target(index + 1, f"Target {index + 1} must exceed {index + 1}%.")
            for index in range(3)
        ]
        document_target = " ".join(target.quote for target in targets)
        attribute = replace(
            self.attribute,
            document_target=document_target,
            document_spans=[
                DocumentSpan(quote=document_target, block_ids=[BLOCK_ID])
            ],
            quantitative_target_ids=[target.id for target in targets],
        )
        ledger = QuantitativeLedger(
            status="complete",
            block_ids=[BLOCK_ID],
            targets=targets,
        )
        client = _RecordingClient()

        prefill_target_review(
            [attribute], ledger, [replace(self.block, content=document_target)], client,
        )

        self.assertEqual([len(batch) for batch in client.batches], [1, 1, 1])

    def test_an_incomplete_review_is_retried_once(self) -> None:
        class _IncompleteThenComplete(_ConcurrentClient):
            calls = 0

            def call_structured(self, *args, **kwargs):
                type(self).calls += 1
                if type(self).calls == 1:
                    return {"reviews": []}
                return super().call_structured(*args, **kwargs)

        _, ledger = prefill_target_review(
            [self.attribute], self.ledger, [self.block], _IncompleteThenComplete(),
        )

        self.assertEqual(_IncompleteThenComplete.calls, 2)
        self.assertEqual(ledger.targets[0].ai_recommendation, "confirm")

    def test_review_batches_run_concurrently_without_cross_batch_ids(self) -> None:
        targets = [
            _target(index + 1, f"Target {index + 1} must exceed {index + 1}%.")
            for index in range(17)
        ]
        attribute = Attribute(
            name="vaccine.efficacy",
            description="Protective efficacy target",
            document_target=" ".join(target.quote for target in targets),
            document_spans=[
                DocumentSpan(
                    quote=" ".join(target.quote for target in targets),
                    block_ids=[BLOCK_ID],
                )
            ],
            target_resolved=True,
            quantitative_target_ids=[target.id for target in targets],
        )
        block = ContentBlock(
            id=BLOCK_ID,
            doc_id="document",
            ordinal=1,
            block_type="paragraph",
            content=attribute.document_target,
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        ledger = QuantitativeLedger(
            status="complete",
            block_ids=[BLOCK_ID],
            targets=targets,
        )
        client = _ConcurrentClient()

        reviewed_attributes, reviewed_ledger = prefill_target_review(
            [attribute], ledger, [block], client,
        )

        self.assertGreater(client.max_active, 1)
        self.assertEqual(
            [target.id for target in reviewed_ledger.targets],
            [target.id for target in targets],
        )
        self.assertTrue(all(
            target.review_status == "needs_review"
            for target in reviewed_ledger.targets
        ))
        self.assertEqual(
            reviewed_attributes[0].quantitative_target_ids,
            [target.id for target in reviewed_ledger.targets],
        )

if __name__ == "__main__":
    unittest.main()
