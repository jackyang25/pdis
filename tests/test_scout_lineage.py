from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services.chunker import ContentBlock
from services.assistant import document as document_reader
from services.scout.context import select_attribute_context
from services.scout.models import (
    EVIDENCE_DOMAINS,
    Attribute,
    Insight,
    QueryIntent,
    load_attributes,
    load_config,
)
from services.scout.stages.conformity import score_conformity
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.evidence_assessor import assess_evidence
from services.scout.stages.precedent_classifier import classify_precedent
from services.scout.stages.query_extractor import _parse_queries
from services.scout.stages.intent_builder import build_retrieval_intents
from services.scout.stages.target_resolver import resolve_document_target
from services.scout.stages.unit_extractor import _document_chunks, extract_units
from services.searcher import Finding, merge_findings, plan_requests, source_keys


class StaticClient:
    def __init__(self, response: object):
        self.response = response
        self.calls = 0
        self.image_calls: list[list[dict[str, str]]] = []

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        images: list[dict[str, str]] | None = None,
    ) -> str:
        self.calls += 1
        self.image_calls.append(images or [])
        return json.dumps(self.response)


def finding(url: str, *, query: str = "query", source: str = "web") -> Finding:
    return Finding(
        url=url,
        title=url,
        query=query,
        retrieved_at=datetime.now(timezone.utc),
        excerpt="source evidence",
        source=source,
    )


def block(index: int, content: str) -> ContentBlock:
    return ContentBlock(
        id=f"document/b-{index:04d}",
        doc_id="document",
        ordinal=index,
        block_type="paragraph",
        content=content,
        heading_stack=[],
        structural_meta={},
        style_hint={},
    )


class SearchProvenanceTests(unittest.TestCase):
    def test_duplicate_urls_merge_queries_and_lanes(self) -> None:
        existing = finding("https://example.test/a", query="first", source="web")
        incoming = finding("https://example.test/a", query="second", source="pubmed")

        merged = merge_findings(existing, incoming)

        self.assertEqual(merged.queries, ["first", "second"])
        self.assertEqual(merged.source_lanes, ["web", "pubmed"])
        self.assertEqual(merged.source, "web")
        self.assertEqual(
            [(path.query, path.lane) for path in merged.retrieval_paths],
            [("first", "web"), ("second", "pubmed")],
        )


class RetrievalPlanningTests(unittest.TestCase):
    def test_every_fixed_attribute_has_an_authored_evidence_domain(self) -> None:
        for intervention_class in ("vaccine", "drug", "diagnostic", "device"):
            attributes = load_attributes(intervention_class)
            self.assertTrue(attributes, intervention_class)
            for attribute in attributes:
                self.assertIn(attribute.evidence_domain, EVIDENCE_DOMAINS)
                self.assertNotEqual(attribute.evidence_domain, "general")

    def test_every_product_config_has_responsibility_specific_framing(self) -> None:
        config_dir = Path(__file__).resolve().parents[1] / "services" / "scout" / "configs"
        for path in config_dir.glob("bmgf_*.yaml"):
            config = load_config(str(path))
            self.assertTrue(config.drift_framing, path.name)
            self.assertTrue(config.evidence_framing, path.name)
            self.assertTrue(config.conformity_framing, path.name)
            self.assertTrue(config.precedent_framing, path.name)
            self.assertTrue(config.sources, path.name)
            self.assertTrue(set(config.sources).issubset(set(source_keys())), path.name)

    def test_router_uses_lane_native_query_shapes(self) -> None:
        attribute = Attribute(
            "dose_regimen",
            "Number and timing of doses",
            evidence_domain="clinical",
        )
        intents = [
            QueryIntent(
                "latest WHO malaria vaccine doses site:who.int",
                ["general"],
                ["doc/b-0002"],
            ),
            QueryIntent("malaria vaccine dosing failure", ["counterfactual"], ["doc/b-0002"]),
            QueryIntent(
                "malaria vaccine schedule adherence limitations",
                ["counterfactual"],
                ["doc/b-0003"],
            ),
        ]

        retrieval_intents = build_retrieval_intents(
            {attribute.name: intents},
            [attribute],
            indication="malaria",
            intervention_class="vaccine",
        )
        tasks = plan_requests(
            retrieval_intents,
            sources=("web", "pubmed", "clinicaltrials"),
        )

        self.assertEqual(sum(task.source == "web" for task in tasks), 3)
        self.assertEqual(sum(task.source == "pubmed" for task in tasks), 2)
        self.assertEqual(sum(task.source == "clinicaltrials" for task in tasks), 2)
        literature = next(
            task
            for task in tasks
            if task.source == "pubmed" and task.tracks == ("general",)
        )
        self.assertIn("latest WHO malaria vaccine doses", literature.query)
        self.assertNotIn("site:", literature.query)
        registry = next(task for task in tasks if task.source == "clinicaltrials")
        self.assertIn("malaria vaccine doses", registry.query)
        self.assertEqual(registry.document_refs, ("doc/b-0002",))
        counterfactual_literature = next(
            task
            for task in tasks
            if task.source == "pubmed" and task.tracks == ("counterfactual",)
        )
        self.assertEqual(len(counterfactual_literature.intent_ids), 2)
        self.assertEqual(
            counterfactual_literature.input_queries,
            (
                "malaria vaccine dosing failure",
                "malaria vaccine schedule adherence limitations",
            ),
        )
        self.assertIn("schedule adherence limitations", counterfactual_literature.query)
        self.assertEqual(
            counterfactual_literature.document_refs,
            ("doc/b-0002", "doc/b-0003"),
        )

        literature_only = plan_requests(retrieval_intents, sources=("pubmed",))
        self.assertTrue(literature_only)
        self.assertEqual({task.source for task in literature_only}, {"pubmed"})

    def test_query_parser_validates_document_lineage(self) -> None:
        raw = json.dumps(
            [
                {
                    "query": "malaria vaccine dose target",
                    "doc_block_ids": ["doc/b-0002", "invented/b-9999"],
                }
            ]
        )

        intents = _parse_queries(raw, {"doc/b-0002"})

        self.assertEqual(intents[0].doc_block_ids, ["doc/b-0002"])

    def test_plain_text_literature_plan_covers_every_variant(self) -> None:
        attribute = Attribute("durability", "Duration of protection")
        variants = [
            QueryIntent(
                f"malaria vaccine durability concept{index}",
                ["general"],
                [f"doc/b-{index:04d}"],
            )
            for index in range(5)
        ]
        retrieval_intents = build_retrieval_intents(
            {attribute.name: variants},
            [attribute],
            indication="malaria",
            intervention_class="vaccine",
        )

        requests = plan_requests(
            retrieval_intents,
            sources=("semantic_scholar",),
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(len(requests[0].intent_ids), 5)
        self.assertEqual(requests[0].input_queries, tuple(item.text for item in variants))
        self.assertIn("concept4", requests[0].query)
        self.assertEqual(
            requests[0].document_refs,
            tuple(f"doc/b-{index:04d}" for index in range(5)),
        )


class DocumentContextTests(unittest.TestCase):
    def test_unit_extraction_receives_block_labeled_visuals(self) -> None:
        client = StaticClient(
            [
                {
                    "name": "timeline",
                    "description": "Regulatory approval timing and feasibility.",
                    "evidence_domain": "regulatory",
                    "document_target": "Approval is targeted for 2030.",
                    "entities": [
                        {
                            "name": "RTS,S",
                            "entity_type": "vaccine",
                            "identifier": "",
                        }
                    ],
                    "block_ids": ["document/b-0002"],
                }
            ]
        )

        units = extract_units(
            "[block:document/b-0002]\n[image]",
            intervention_class="vaccine",
            source_type="ipdp",
            indication="malaria",
            llm_client=client,
            images_by_block_id={"document/b-0002": "data:image/png;base64,AA=="},
        )

        self.assertEqual(units[0].block_ids, ["document/b-0002"])
        self.assertEqual(units[0].definition_mode, "dynamic")
        self.assertEqual(
            units[0].description,
            "Regulatory approval timing and feasibility.",
        )
        self.assertEqual(units[0].document_target, "Approval is targeted for 2030.")
        self.assertEqual(units[0].evidence_domain, "regulatory")
        self.assertEqual(units[0].entities[0].name, "RTS,S")
        self.assertEqual(units[0].entities[0].entity_type, "vaccine")
        self.assertTrue(units[0].target_resolved)
        self.assertEqual(
            client.image_calls[0],
            [
                {
                    "block_id": "document/b-0002",
                    "data_url": "data:image/png;base64,AA==",
                }
            ],
        )

    def test_fixed_and_dynamic_units_converge_to_the_same_bound_shape(self) -> None:
        fixed_client = StaticClient(
            {
                "document_target": "Complete Phase 2 by 2028.",
                "block_ids": ["document/b-0002", "invented/b-9999"],
            }
        )
        fixed = resolve_document_target(
            Attribute(
                name="clinical_development_timeline",
                description="Timing and feasibility of clinical development milestones.",
                definition_mode="fixed",
            ),
            "[block:document/b-0002]\nComplete Phase 2 by 2028.",
            fixed_client,
        )
        dynamic_client = StaticClient({"unexpected": True})
        dynamic = resolve_document_target(
            Attribute(
                name="clinical_development_timeline",
                description="Timing and feasibility of clinical development milestones.",
                block_ids=["document/b-0002"],
                document_target="Complete Phase 2 by 2028.",
                definition_mode="dynamic",
                target_resolved=True,
            ),
            "[block:document/b-0002]\nComplete Phase 2 by 2028.",
            dynamic_client,
        )

        for unit in (fixed, dynamic):
            self.assertEqual(unit.name, "clinical_development_timeline")
            self.assertEqual(
                unit.description,
                "Timing and feasibility of clinical development milestones.",
            )
            self.assertEqual(unit.document_target, "Complete Phase 2 by 2028.")
            self.assertEqual(unit.block_ids, ["document/b-0002"])
            self.assertTrue(unit.target_resolved)
        self.assertEqual(fixed.definition_mode, "fixed")
        self.assertEqual(dynamic.definition_mode, "dynamic")
        self.assertEqual(fixed_client.calls, 1)
        self.assertEqual(dynamic_client.calls, 0)

    def test_extracted_unit_origin_survives_bounded_selection(self) -> None:
        blocks = [block(i, "generic content " * 15) for i in range(20)]
        attribute = Attribute(
            name="timeline",
            description="A milestone date",
            block_ids=["document/b-0012"],
        )

        context = select_attribute_context(blocks, attribute, max_chars=1_200)

        self.assertIn("[block:document/b-0012]", context)

    def test_unit_extraction_chunks_preserve_all_annotated_text(self) -> None:
        document = "\n\n".join(
            f"[block:document/b-{i:04d}]\n{'x' * 120_000}" for i in range(4)
        )

        chunks = _document_chunks(document)

        self.assertGreater(len(chunks), 1)
        self.assertEqual("\n\n".join(chunks), document)

    def test_ask_can_find_and_page_text_beyond_old_inline_limit(self) -> None:
        content = "x" * 130_000 + "tail-only milestone"
        document = [
            {
                "id": "document/b-0001",
                "doc_id": "document",
                "content": content,
                "heading_stack": ["Timeline"],
            }
        ]

        hits = document_reader.find(document, "tail-only milestone")
        tail = document_reader.get(
            document,
            ["document/b-0001"],
            start_char=120_000,
        )

        self.assertIn("document/b-0001", hits)
        self.assertIn("tail-only milestone", tail)

    def test_ask_can_page_an_ordered_document_without_guessing_ids(self) -> None:
        document = [
            {
                "id": f"document/b-{i:04d}",
                "doc_id": "document",
                "content": f"content {i}",
                "heading_stack": [],
            }
            for i in range(30)
        ]

        page = document_reader.get_range(document, "document", start=25, count=5)

        self.assertIn("content 25", page)
        self.assertIn("content 29", page)


class ReasoningLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = Insight(
            statement="The trial met its endpoint.",
            supporting_findings=[finding("https://example.test/used")],
            attribute_ref="efficacy",
        )
        self.second = Insight(
            statement="A registry lists an adjacent trial.",
            supporting_findings=[finding("https://example.test/unused")],
            attribute_ref="efficacy",
        )
        self.document = "[block:document/b-0003]\nTarget efficacy is at least 80%."
        self.attribute = Attribute("efficacy", "Target product efficacy")

    def test_assessment_keeps_only_selected_insight_sources(self) -> None:
        client = StaticClient(
            {
                "strength": "partial",
                "doc_target": "at least 80% efficacy",
                "doc_block_ids": ["document/b-0003", "invented/b-9999"],
                "supporting_insight_indices": [0],
                "reason": "Direct evidence supports the target with remaining uncertainty.",
            }
        )

        result = assess_evidence(
            self.attribute,
            self.document,
            [self.first, self.second],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(result.supporting_insight_ids, [self.first.id])
        self.assertEqual(
            [source.url for source in result.supporting_findings],
            ["https://example.test/used"],
        )
        self.assertEqual(result.doc_block_ids, ["document/b-0003"])

    def test_assessment_preserves_document_target_without_web_evidence(self) -> None:
        client = StaticClient(
            {
                "strength": "unknown",
                "doc_target": "at least 80% efficacy",
                "doc_block_ids": ["document/b-0003"],
                "supporting_insight_indices": [],
                "reason": "No web evidence was found for this target.",
            }
        )

        result = assess_evidence(
            self.attribute,
            self.document,
            [],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(result.strength, "unknown")
        self.assertEqual(result.doc_target, "at least 80% efficacy")
        self.assertEqual(result.doc_block_ids, ["document/b-0003"])

    def test_reasoning_cannot_rewrite_a_resolved_document_target(self) -> None:
        attribute = Attribute(
            name="efficacy",
            description="Target product efficacy",
            block_ids=["document/b-0003"],
            document_target="at least 80% efficacy",
            definition_mode="dynamic",
            target_resolved=True,
        )
        client = StaticClient(
            {
                "strength": "partial",
                "doc_target": "a different invented target",
                "doc_block_ids": ["invented/b-9999"],
                "supporting_insight_indices": [0],
                "reason": "Some directly comparable evidence is available.",
            }
        )

        result = assess_evidence(
            attribute,
            self.document,
            [self.first],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(result.doc_target, "at least 80% efficacy")
        self.assertEqual(result.doc_block_ids, ["document/b-0003"])

    def test_drift_discards_hallucinated_document_block_ids(self) -> None:
        client = StaticClient(
            [
                {
                    "index": 0,
                    "relation": "confirms",
                    "reason": "The endpoint supports the stated target.",
                    "doc_block_ids": ["document/b-0003", "invented/b-9999"],
                }
            ]
        )

        result = classify_drift(
            [self.document],
            [self.first],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(result[0].doc_block_ids, ["document/b-0003"])

    def test_conformity_rejects_url_not_owned_by_selected_insight(self) -> None:
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [
                    {
                        "value": 81,
                        "unit": "%",
                        "evidence_form": "randomized_trial",
                        "development_phase": "phase_3",
                        "source_record_type": "peer_reviewed",
                        "insight_index": 0,
                        "url": "https://example.test/unused",
                    },
                    {
                        "value": 82,
                        "unit": "%",
                        "evidence_form": "randomized_trial",
                        "development_phase": "phase_3",
                        "source_record_type": "peer_reviewed",
                        "insight_index": 0,
                        "url": "https://example.test/used",
                    },
                ],
            }
        )

        result = score_conformity(
            self.attribute,
            self.document,
            [self.first, self.second],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result.measurements), 1)
        self.assertEqual(result.measurements[0].url, "https://example.test/used")
        self.assertEqual(result.measurements[0].insight_id, self.first.id)
        self.assertEqual(result.measurements[0].evidence_form, "randomized_trial")
        self.assertEqual(result.measurements[0].development_phase, "phase_3")
        self.assertEqual(result.measurements[0].source_record_type, "peer_reviewed")

    def test_conformity_rejects_incompatible_units_without_conversion(self) -> None:
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [
                    {
                        "value": 0.82,
                        "unit": "fraction",
                        "evidence_form": "randomized_trial",
                        "development_phase": "phase_3",
                        "source_record_type": "peer_reviewed",
                        "insight_index": 0,
                        "url": "https://example.test/used",
                    }
                ],
            }
        )

        result = score_conformity(
            self.attribute,
            self.document,
            [self.first],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNone(result)

    def test_precedent_keeps_coverage_and_outcome_separate(self) -> None:
        client = StaticClient(
            {
                "precedent": "direct",
                "outcome": "unfavorable",
                "reason": "A comparable prior program was terminated.",
                "doc_block_ids": ["document/b-0003"],
                "coverage_insight_indices": [0],
                "outcome_insight_indices": [0],
            }
        )

        result = classify_precedent(
            self.attribute,
            self.document,
            [self.first],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.precedent, "direct")
        self.assertEqual(result.outcome, "unfavorable")
        self.assertEqual(result.coverage_insight_ids, [self.first.id])
        self.assertEqual(result.outcome_insight_ids, [self.first.id])


if __name__ == "__main__":
    unittest.main()
