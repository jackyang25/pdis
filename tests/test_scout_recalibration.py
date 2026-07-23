from __future__ import annotations

import unittest

from api.routes.scout import _recalibration_inputs
from api.schemas import (
    ContentBlockOut,
    DocumentContextValidationOut,
    FindingOut,
    FunnelStatsOut,
    InsightOut,
    MatchOut,
    QuantitativeTargetOut,
    ScoutRecalibrationRequest,
    ScoutRunResponse,
    VariableOut,
)
from services.scout import Attribute, QuantitativeTarget
from services.scout.stages.conformity import revalidate_quantitative_targets


class ScoutRecalibrationBoundaryTests(unittest.TestCase):
    def test_saved_target_must_still_match_its_exact_portable_block(self) -> None:
        document = "[block:document/b-0001]\nTarget efficacy is at least 80%."
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            value=80,
            comparator=">=",
            unit="%",
            label="efficacy threshold",
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0001"],
        )
        attribute = Attribute(
            name="efficacy",
            description="Clinical efficacy",
            block_ids=["document/b-0001"],
            document_target=target.quote,
            target_resolved=True,
            quantitative_targets=[target],
        )

        self.assertEqual(
            [item.id for item in revalidate_quantitative_targets(attribute, document)],
            [target.id],
        )
        tampered = QuantitativeTarget(
            attribute_ref="efficacy",
            value=90,
            comparator=">=",
            unit="%",
            label="efficacy threshold",
            role="threshold",
            quote=target.quote,
            doc_block_ids=target.doc_block_ids,
        )
        self.assertEqual(
            revalidate_quantitative_targets(
                Attribute(
                    name="efficacy",
                    description="Clinical efficacy",
                    block_ids=["document/b-0001"],
                    document_target=target.quote,
                    target_resolved=True,
                    quantitative_targets=[tampered],
                ),
                document,
            ),
            [],
        )

    def test_current_wire_result_rehydrates_without_reinterpreting_provenance(self) -> None:
        result = ScoutRunResponse(
            org="bmgf",
            source_type="itpp",
            intervention_class="vaccine",
            indication="malaria",
            context_validation=DocumentContextValidationOut(
                status="match",
                configured_indication="malaria",
            ),
            variables=[
                VariableOut(
                    name="efficacy",
                    description="Clinical efficacy",
                    block_ids=["document/b-0001"],
                    document_target="Target efficacy is at least 80%.",
                    target_resolved=True,
                    quantitative_targets=[
                        QuantitativeTargetOut(
                            id="qt-canonical",
                            attribute_ref="efficacy",
                            value=80,
                            comparator=">=",
                            unit="%",
                            label="efficacy threshold",
                            role="threshold",
                            quote="Target efficacy is at least 80%.",
                            doc_block_ids=["document/b-0001"],
                        )
                    ],
                )
            ],
            matches=[
                MatchOut(
                    insight=InsightOut(
                        id="i-stable",
                        statement="A trial reported efficacy of 82%.",
                        query="malaria vaccine efficacy",
                        retrieval_target_ids=["qt-canonical"],
                        supporting_findings=[
                            FindingOut(
                                url="https://example.test/study",
                                title="Study",
                                query="malaria vaccine efficacy",
                                retrieved_at="2026-07-20T12:00:00+00:00",
                                excerpt="The reported efficacy was 82% at 12 months.",
                                source="pubmed",
                                excerpt_source_lane="pubmed",
                            )
                        ],
                        org="bmgf",
                        source_type="itpp",
                        intervention_class="vaccine",
                        indication="malaria",
                        attribute_ref="efficacy",
                    ),
                    relation="extends",
                    reason="Adds a comparator.",
                    doc_block_ids=["document/b-0001"],
                )
            ],
            assessments=[],
            stats=FunnelStatsOut(
                queries=1,
                findings=1,
                unique_findings=1,
                insights=1,
                matches=1,
                assessments=0,
            ),
            blocks=[
                ContentBlockOut(
                    id="document/b-0001",
                    doc_id="document",
                    ordinal=1,
                    block_type="paragraph",
                    content="Target efficacy is at least 80%.",
                    heading_stack=[],
                )
            ],
        )

        request = ScoutRecalibrationRequest(
            quantitative_contract_version=1,
            result=result,
        )
        attributes, blocks, insights = _recalibration_inputs(request.result)

        self.assertEqual(attributes[0].document_target, "Target efficacy is at least 80%.")
        self.assertEqual(attributes[0].block_ids, ["document/b-0001"])
        self.assertEqual(attributes[0].quantitative_targets[0].id, "qt-canonical")
        self.assertEqual(blocks[0].id, "document/b-0001")
        self.assertEqual(insights[0].id, "i-stable")
        self.assertEqual(insights[0].retrieval_target_ids, ["qt-canonical"])
        self.assertEqual(insights[0].supporting_findings[0].url, "https://example.test/study")
        self.assertEqual(
            insights[0].supporting_findings[0].excerpt,
            "The reported efficacy was 82% at 12 months.",
        )
        self.assertEqual(
            insights[0].supporting_findings[0].excerpt_source_lane,
            "pubmed",
        )


if __name__ == "__main__":
    unittest.main()
