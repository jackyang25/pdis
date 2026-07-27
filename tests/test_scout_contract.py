from __future__ import annotations

import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone

from services.chunker import ContentBlock
from services.scout.contract import validate_result_contract
from services.scout.models import (
    Attribute,
    DocumentContextValidation,
    DocumentSpan,
    EvidenceAssessment,
    FunnelStats,
    Insight,
    Match,
    NumericExpression,
    QuantitativeLedger,
    QuantitativeLedgerReview,
    QuantitativeFieldLink,
    QuantitativeTarget,
    SemanticSlot,
    ScoutResult,
)
from services.searcher import Finding
from api.schemas import VariableOut


def _block(index: int) -> ContentBlock:
    return ContentBlock(
        id=f"document/b-{index:04d}",
        doc_id="document",
        ordinal=index,
        block_type="paragraph",
        content=f"Field {index} target.",
        heading_stack=[],
        structural_meta={},
        style_hint={},
    )


def _finding(url: str) -> Finding:
    return Finding(
        url=url,
        title="Source",
        query="query",
        retrieved_at=datetime.now(timezone.utc),
        excerpt="Source-backed evidence.",
        source="pubmed",
    )


def _result() -> ScoutResult:
    blocks = [_block(1), _block(2)]
    attributes = [
        Attribute(
            name="efficacy",
            description="Efficacy target",
            block_ids=[blocks[0].id],
            document_target="Field 1 target.",
            document_spans=[
                DocumentSpan(
                    quote="Field 1 target.",
                    block_ids=[blocks[0].id],
                )
            ],
            target_resolved=True,
            target_resolution_reason="Resolved from exact document spans.",
        ),
        Attribute(
            name="safety",
            description="Safety target",
            block_ids=[blocks[1].id],
            document_target="Field 2 target.",
            document_spans=[
                DocumentSpan(
                    quote="Field 2 target.",
                    block_ids=[blocks[1].id],
                )
            ],
            target_resolved=True,
            target_resolution_reason="Resolved from exact document spans.",
        ),
    ]
    evidence = _finding("https://example.test/efficacy")
    insight = Insight(
        statement="The study reports efficacy evidence.",
        supporting_findings=[evidence],
        query="query",
        query_tracks=["general"],
        attribute_ref="efficacy",
    )
    return ScoutResult(
        matches=[
            Match(
                insight=insight,
                relation="confirms",
                reason="Supports the target.",
                doc_block_ids=[blocks[0].id],
            )
        ],
        assessments=[
            EvidenceAssessment(
                attribute_ref="efficacy",
                strength="partial",
                reason="One source supports the target.",
                doc_target="Field 1 target.",
                doc_block_ids=[blocks[0].id],
                supporting_insight_ids=[insight.id],
                supporting_findings=[evidence],
            )
        ],
        stats=FunnelStats(
            queries=1,
            findings=1,
            unique_findings=1,
            insights=1,
            matches=1,
            assessments=1,
        ),
        context_validation=DocumentContextValidation(
            status="match",
            configured_indication="malaria",
            document_indication="malaria",
            reason="The document concerns malaria.",
            doc_block_ids=[blocks[0].id],
        ),
        variables=attributes,
        blocks=blocks,
    )


class ScoutResultContractTests(unittest.TestCase):
    def test_api_variable_projection_preserves_claim_provenance(self) -> None:
        variable = _result().variables[0]

        projected = VariableOut.model_validate(asdict(variable))

        self.assertEqual(projected.document_spans[0].quote, "Field 1 target.")
        self.assertEqual(
            projected.target_resolution_reason,
            "Resolved from exact document spans.",
        )

    def test_valid_independent_axes_pass(self) -> None:
        result = _result()
        self.assertIs(validate_result_contract(result), result)

    def test_assessment_cannot_cite_another_fields_insight(self) -> None:
        result = _result()
        result.assessments[0].attribute_ref = "safety"
        result.assessments[0].doc_block_ids = ["document/b-0002"]

        with self.assertRaisesRegex(ValueError, "another field"):
            validate_result_contract(result)

    def test_match_cannot_cite_another_fields_document_block(self) -> None:
        result = _result()
        result.matches[0].doc_block_ids = ["document/b-0002"]

        with self.assertRaisesRegex(ValueError, "unknown IDs"):
            validate_result_contract(result)

    def test_fresh_target_requires_exact_document_spans(self) -> None:
        result = _result()
        result.variables[0].document_spans = []

        with self.assertRaisesRegex(ValueError, "without exact spans"):
            validate_result_contract(result)

    def test_target_field_links_must_reference_known_fields(self) -> None:
        result = _result()
        shared_span = DocumentSpan(
            quote="No more than three injections.",
            block_ids=[result.blocks[0].id],
        )
        result.variables = [
            replace(attribute, document_spans=[shared_span])
            for attribute in result.variables
        ]

        target = QuantitativeTarget(
                field_links=[
                    QuantitativeFieldLink(
                        attribute_ref="efficacy",
                        relation="defines",
                        reason="The statement specifies efficacy.",
                    ),
                    QuantitativeFieldLink(
                        attribute_ref="unknown-field",
                        relation="context_for",
                        reason="Invalid test link.",
                    ),
                ],
                expression=NumericExpression(
                    kind="bound",
                    value=3,
                    comparator="<=",
                    unit="injections",
                ),
                role="threshold",
                quote=shared_span.quote,
                doc_block_ids=shared_span.block_ids,
                comparison_dimensions=["measure"],
                semantic_profile={
                    "measure": SemanticSlot(
                        state="specified",
                        value="injections per regimen",
                    )
                },
                provenance_spans=[shared_span],
                semantic_provenance={"measure": [shared_span]},
                review_status="approved",
            )
        result.variables = [
            replace(
                attribute,
                quantitative_target_ids=[target.id] if attribute.name == "efficacy" else [],
                quantitative_target_status=(
                    "present" if attribute.name == "efficacy" else "not_applicable"
                ),
            )
            for attribute in result.variables
        ]
        result.quantitative_ledger = QuantitativeLedger(
            status="complete",
            block_ids=[result.blocks[0].id],
            targets=[target],
            reviews=[
                QuantitativeLedgerReview(
                    unit_id="unit-1",
                    block_id=result.blocks[0].id,
                    quote=shared_span.quote,
                    classification="target",
                    attribute_refs=["efficacy"],
                    reason="Mapped target.",
                    target_ids=[target.id],
                    review_status="resolved",
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "target .* fields contain unknown IDs"):
            validate_result_contract(result)


if __name__ == "__main__":
    unittest.main()
