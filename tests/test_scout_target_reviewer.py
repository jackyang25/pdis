from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.scout.models import (
    Attribute,
    DocumentSpan,
    NumericExpression,
    QuantitativeLedger,
    QuantitativeTarget,
    SemanticSlot,
)
from services.scout.stages.target_reviewer import prefill_target_review


BLOCK_ID = "document/b-0001"


def _target(value: float, quote: str) -> QuantitativeTarget:
    return QuantitativeTarget(
        attribute_ref="vaccine.efficacy",
        expression=NumericExpression(
            kind="bound",
            value=value,
            comparator=">",
            unit="%",
        ),
        role="threshold",
        quote=quote,
        doc_block_ids=[BLOCK_ID],
        comparison_dimensions=["measure"],
        semantic_profile={
            "measure": SemanticSlot(state="specified", value="protective efficacy"),
        },
        provenance_spans=[DocumentSpan(quote=quote, block_ids=[BLOCK_ID])],
        review_status="needs_review",
    )


class _Client:
    def __init__(self, reviews: list[dict] | None = None, failure: Exception | None = None):
        self.reviews = reviews or []
        self.failure = failure
        self.user_message = ""

    def call_structured(self, _system, user_message, *_args, **_kwargs):
        self.user_message = user_message
        if self.failure:
            raise self.failure
        return {"reviews": self.reviews}


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
            quantitative_targets=[self.target],
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
        self.assertEqual(reviewed.review_status, "approved")
        self.assertEqual(attributes[0].quantitative_targets, [reviewed])
        self.assertIn("Background incidence was 14%", client.user_message)

    def test_missing_or_failed_ai_review_degrades_to_manual_review(self) -> None:
        for client in (
            None,
            _Client([]),
            _Client(failure=RuntimeError("provider unavailable")),
        ):
            with self.subTest(client="missing" if client is None else type(client.failure).__name__):
                _, ledger = prefill_target_review(
                    [self.attribute], self.ledger, [self.block], client,
                )
                self.assertEqual(ledger.targets[0].ai_recommendation, "flag")
                self.assertEqual(ledger.targets[0].review_status, "needs_review")


if __name__ == "__main__":
    unittest.main()
