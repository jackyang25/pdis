from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.chunker import ContentBlock
from services.scout.contract import validate_result_contract
from services.scout.models import (
    Attribute,
    DocumentContextValidation,
    EvidenceAssessment,
    FunnelStats,
    Insight,
    Match,
    ScoutResult,
)
from services.searcher import Finding


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
            target_resolved=True,
        ),
        Attribute(
            name="safety",
            description="Safety target",
            block_ids=[blocks[1].id],
            document_target="Field 2 target.",
            target_resolved=True,
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


if __name__ == "__main__":
    unittest.main()
