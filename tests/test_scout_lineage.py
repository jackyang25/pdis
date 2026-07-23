from __future__ import annotations

import json
import re
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from services.chunker import ContentBlock
from api.schemas import ConformityOut
from services.assistant import document as document_reader
from services.scout.context import select_attribute_context, validated_block_ids
from services.scout.projections import (
    build_development_landscape,
    build_safety_signals,
)
from services.scout.models import (
    EVIDENCE_DOMAINS,
    Attribute,
    Insight,
    QueryIntent,
    QuantitativeTarget,
    load_attributes,
    load_config,
)
from services.scout.stages.conformity import (
    _measurement_system_prompt,
    _meets_target,
    _numeric_spans_for_unit,
    _value_unit_supported,
    extract_quantitative_targets,
    score_conformity as _score_conformity_ledgers,
)
from services.scout.stages.context_validator import (
    mismatch_message,
    validate_document_context,
)
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.evidence_assessor import assess_evidence
from services.scout.stages.precedent_classifier import classify_precedent
from services.scout.stages.query_extractor import (
    _parse_queries,
    extract_queries_for_variable,
)
from services.scout.stages.intent_builder import build_retrieval_intents
from services.scout.stages.target_resolver import (
    DEFAULT_MAX_TOKENS as TARGET_RESOLVER_MAX_TOKENS,
    resolve_document_target,
)
from services.scout.stages.unit_extractor import _document_chunks, extract_units
from services.searcher import (
    DevelopmentRecord,
    Finding,
    SafetyRecord,
    merge_findings,
    plan_requests,
    source_keys,
)
from services.searcher.stages.searcher import _parse_response_to_findings


class StaticClient:
    def __init__(self, response: object):
        self.response = response
        self.calls = 0
        self.image_calls: list[list[dict[str, str]]] = []
        self.token_budgets: list[int] = []

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
        self.token_budgets.append(max_tokens)
        return json.dumps(
            normalize_conformity_fixture(self.response, system_prompt, user_message)
        )


class SequenceClient(StaticClient):
    def __init__(self, responses: list[object]):
        super().__init__({})
        self.responses = list(responses)

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
        self.token_budgets.append(max_tokens)
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        return json.dumps(
            normalize_conformity_fixture(
                self.responses.pop(0), system_prompt, user_message
            )
        )


def normalize_conformity_fixture(
    response: object, system_prompt: str, user_message: str
) -> object:
    """Adapt historical fixtures at the test boundary to the current wire contract."""
    if not isinstance(response, dict):
        return response
    if "enumerate exact quantitative document targets" in system_prompt.lower():
        if "targets" in response:
            return response
        if not response.get("is_quantitative"):
            return {"targets": []}
        return {
            "targets": [
                {
                    "value": response.get("target_value"),
                    "comparator": response.get("comparator"),
                    "unit": response.get("unit"),
                    "label": response.get("target_label"),
                    "role": "threshold",
                    "quote": response.get("target_quote"),
                    "doc_block_ids": response.get("doc_block_ids", []),
                }
            ]
        }
    if "classify immutable numeric source candidates" not in system_prompt.lower():
        return response
    if "decisions" in response:
        return response
    target_match = re.search(r"Document target ID: (qt-[a-f0-9]+)", system_prompt)
    target_id = target_match.group(1) if target_match else ""
    candidates: list[tuple[str, float, str]] = []
    for candidate_id, value, url in re.findall(
        r"\[candidate:(qc-[a-f0-9]+)\] value=([-+0-9.eE]+) [^|]+\| url=([^ |]+)",
        user_message,
    ):
        candidates.append((candidate_id, float(value), url))
    decisions = []
    for item in response.get("measurements", []):
        if not isinstance(item, dict):
            continue
        candidate_id = next(
            (
                candidate
                for candidate, value, url in candidates
                if url == item.get("url")
                and abs(value - float(item.get("value", float("inf")))) < 1e-9
            ),
            "",
        )
        if not candidate_id:
            continue
        comparability = {}
        for axis, axis_item in (item.get("comparability") or {}).items():
            relation = axis_item.get("relation", "unknown")
            comparability[axis] = {
                **axis_item,
                "target_span_ids": [target_id]
                if relation in {"same", "compatible", "different", "not_applicable"}
                else [],
                "source_span_ids": [candidate_id]
                if relation in {"same", "compatible", "different"}
                else [],
            }
        decisions.append(
            {
                "candidate_id": candidate_id,
                "evidence_form": item.get("evidence_form", "other"),
                "development_phase": item.get("development_phase", "unknown"),
                "source_record_type": item.get("source_record_type", "unknown"),
                "comparability": comparability,
            }
        )
    return {"decisions": decisions}


def score_conformity_ledgers(attribute, document, insights, client, **kwargs):
    targets = extract_quantitative_targets(
        attribute,
        document,
        client,
        indication=kwargs["indication"],
        intervention_class=kwargs["intervention_class"],
    )
    return _score_conformity_ledgers(
        replace(attribute, quantitative_targets=targets),
        insights,
        client,
        indication=kwargs["indication"],
        intervention_class=kwargs["intervention_class"],
    )


def score_conformity(*args, **kwargs):
    """Legacy single-ledger convenience for tests not exercising multi-target output."""
    ledgers = score_conformity_ledgers(*args, **kwargs)
    return ledgers[0] if ledgers else None


def finding(
    url: str,
    *,
    query: str = "query",
    source: str = "web",
    excerpt: str = "The reported efficacy was 82% in the target population.",
) -> Finding:
    return Finding(
        url=url,
        title=url,
        query=query,
        retrieved_at=datetime.now(timezone.utc),
        excerpt=excerpt,
        source=source,
    )


def same_comparability() -> dict[str, dict[str, str]]:
    return {
        axis: {"relation": "same", "reason": f"same {axis.replace('_', ' ')}"}
        for axis in (
            "endpoint",
            "population",
            "intervention",
            "regimen",
            "time_horizon",
            "statistic",
        )
    }


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


class DocumentContextValidationTests(unittest.TestCase):
    def test_cited_indication_match_is_retained(self) -> None:
        client = StaticClient(
            {
                "status": "match",
                "document_indication": "malaria",
                "reason": "The document develops a malaria vaccine.",
                "block_ids": ["[block:document/b-0001]"],
            }
        )

        validation = validate_document_context(
            "[block:document/b-0001]\nMalaria vaccine target product profile.",
            client,
            indication="malaria",
        )

        self.assertEqual(validation.status, "match")
        self.assertEqual(validation.doc_block_ids, ["document/b-0001"])

    def test_block_reference_validation_is_exact_and_never_fuzzy(self) -> None:
        allowed = {"document name/b-0001", "document name/b-0002"}

        self.assertEqual(
            validated_block_ids(
                [
                    "document name/b-0001",
                    "[block:document name/b-0002]",
                    "[block:document name/b-0001]",
                    "b-0001",
                    "[block:document name/b-9999]",
                    "[block:document name/b-0002] trailing text",
                    42,
                ],
                allowed,
            ),
            ["document name/b-0001", "document name/b-0002"],
        )

    def test_uncited_mismatch_cannot_block_a_run(self) -> None:
        client = StaticClient(
            {
                "status": "mismatch",
                "document_indication": "malaria",
                "reason": "The document concerns malaria.",
                "block_ids": ["invented/b-9999"],
            }
        )

        validation = validate_document_context(
            "[block:document/b-0001]\nMalaria vaccine target product profile.",
            client,
            indication="HIV",
        )

        self.assertEqual(validation.status, "uncertain")
        self.assertEqual(validation.doc_block_ids, [])

    def test_cited_mismatch_has_actionable_error(self) -> None:
        client = StaticClient(
            {
                "status": "mismatch",
                "document_indication": "malaria",
                "reason": "The document concerns malaria rather than HIV.",
                "block_ids": ["document/b-0001"],
            }
        )

        validation = validate_document_context(
            "[block:document/b-0001]\nMalaria vaccine target product profile.",
            client,
            indication="HIV",
        )

        self.assertEqual(validation.status, "mismatch")
        self.assertIn('Configured indication "HIV"', mismatch_message(validation))
        self.assertIn('"malaria"', mismatch_message(validation))


class SearchProvenanceTests(unittest.TestCase):
    def test_web_citation_excerpt_keeps_claim_context_not_only_link(self) -> None:
        citation = "([source](https://example.test/paper))"
        text = f"R21 efficacy was 75% at 12 months. {citation}"
        start = text.index(citation)
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "text": text,
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.test/paper",
                                    "title": "Paper",
                                    "start_index": start,
                                    "end_index": start + len(citation),
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        findings = _parse_response_to_findings(
            response,
            query="malaria efficacy",
            retrieved_at=datetime.now(timezone.utc),
        )

        self.assertEqual(len(findings), 1)
        self.assertIn("R21 efficacy was 75% at 12 months", findings[0].excerpt or "")
        self.assertEqual(findings[0].excerpt_source_lane, "web")

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

    def test_structured_projections_group_records_without_inference(self) -> None:
        first = finding("https://example.test/trial", source="clinicaltrials")
        first.development_records = [
            DevelopmentRecord(
                program_name="Candidate A",
                record_type="clinical_trial",
                record_id="NCT1",
                sponsor="Sponsor One",
                phase="Phase 2",
                status="Recruiting",
            )
        ]
        first.safety_records = [
            SafetyRecord(
                product_name="Candidate A",
                signal_type="reported_event",
                signal="Headache",
                count=12,
                qualification="Reports do not establish causation.",
            )
        ]
        duplicate = finding("https://example.test/trial", source="clinicaltrials")
        duplicate.development_records = list(first.development_records)
        duplicate.safety_records = list(first.safety_records)

        landscape = build_development_landscape(
            {"clinical_efficacy": [first], "safety": [duplicate]}
        )
        signals = build_safety_signals(
            {"clinical_efficacy": [first], "safety": [duplicate]}
        )

        self.assertEqual(len(landscape), 1)
        self.assertEqual(landscape[0].name, "Candidate A")
        self.assertEqual(landscape[0].attribute_refs, ["clinical_efficacy", "safety"])
        self.assertEqual(len(landscape[0].supporting_findings), 1)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].count, 12)
        self.assertEqual(signals[0].attribute_refs, ["clinical_efficacy", "safety"])


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

    def test_molecular_sources_are_enabled_only_for_relevant_interventions(self) -> None:
        drug = load_config(
            str(
                Path(__file__).resolve().parents[1]
                / "services/scout/configs/bmgf_itpp_drug.yaml"
            )
        )
        vaccine = load_config(
            str(
                Path(__file__).resolve().parents[1]
                / "services/scout/configs/bmgf_itpp_vaccine.yaml"
            )
        )
        device = load_config(
            str(
                Path(__file__).resolve().parents[1]
                / "services/scout/configs/bmgf_itpp_device.yaml"
            )
        )

        self.assertTrue({"open_targets", "chembl", "uniprot"}.issubset(drug.sources))
        self.assertNotIn("open_targets", vaccine.sources)
        self.assertNotIn("chembl", vaccine.sources)
        self.assertIn("uniprot", vaccine.sources)
        self.assertTrue(
            {"open_targets", "chembl", "uniprot"}.isdisjoint(device.sources)
        )
        self.assertIn("fda_safety", drug.sources)
        self.assertIn("fda_safety", vaccine.sources)
        self.assertIn("fda_safety", device.sources)

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
        self.assertEqual(sum(task.source == "clinicaltrials" for task in tasks), 1)
        literature = next(
            task
            for task in tasks
            if task.source == "pubmed" and task.tracks == ("general",)
        )
        self.assertEqual(
            literature.query,
            "(malaria) AND (vaccine) AND (dose OR regimen) AND (Number OR timing OR doses)",
        )
        self.assertNotIn("site:", literature.query)
        registry = next(task for task in tasks if task.source == "clinicaltrials")
        self.assertEqual(registry.query, "condition:malaria AND intervention:vaccine")
        self.assertEqual(registry.tracks, ("general", "counterfactual"))
        self.assertEqual(len(registry.intent_ids), 3)
        self.assertEqual(
            registry.document_refs,
            ("doc/b-0002", "doc/b-0003"),
        )
        self.assertEqual(registry.option("ranking"), "all_input_queries")
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
        self.assertIn("(failure OR limitation OR adverse)", counterfactual_literature.query)
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

    def test_each_canonical_numeric_target_gets_retrieval_coverage_and_lineage(self) -> None:
        targets = [
            QuantitativeTarget(
                attribute_ref="efficacy",
                value=value,
                comparator=">=",
                unit="%",
                label=label,
                role=role,
                quote=quote,
                doc_block_ids=[block_id],
            )
            for value, label, role, quote, block_id in (
                (80, "threshold >=80% at 6 months", "threshold", "At least 80% at 6 months.", "doc/b-0002"),
                (90, "optimal >=90% at 12 months", "optimal", "At least 90% at 12 months.", "doc/b-0003"),
            )
        ]
        attribute = Attribute(
            "efficacy",
            "Protective efficacy",
            document_target="Threshold and optimal efficacy targets.",
            block_ids=["doc/b-0002", "doc/b-0003"],
            target_resolved=True,
            evidence_domain="clinical",
            quantitative_targets=targets,
        )
        config = replace(
            load_config(
                str(
                    Path(__file__).resolve().parents[1]
                    / "services/scout/configs/bmgf_itpp_vaccine.yaml"
                )
            ),
            geographic_queries_per_variable=0,
            counterfactual_queries_per_variable=0,
            precedent_queries_per_variable=0,
        )
        queries = extract_queries_for_variable(
            attribute,
            config,
            StaticClient([{"query": "general efficacy evidence", "doc_block_ids": []}]),
            indication="malaria",
            queries_per_variable=1,
            document_context=(
                "[block:doc/b-0002]\nAt least 80% at 6 months.\n\n"
                "[block:doc/b-0003]\nAt least 90% at 12 months."
            ),
        )

        self.assertEqual(len(queries), 2)
        self.assertEqual(
            {target_id for query in queries for target_id in query.target_ids},
            {target.id for target in targets},
        )
        requests = plan_requests(
            build_retrieval_intents(
                {attribute.name: queries},
                [attribute],
                indication="malaria",
                intervention_class="vaccine",
            ),
            sources=("semantic_scholar",),
        )
        self.assertEqual(set(requests[0].target_refs), {target.id for target in targets})

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
        self.assertEqual(
            requests[0].query,
            "malaria vaccine durability Duration protection",
        )
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
                "block_ids": ["[block:document/b-0002]", "invented/b-9999"],
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
        self.assertEqual(
            fixed_client.token_budgets,
            [TARGET_RESOLVER_MAX_TOKENS],
        )
        self.assertEqual(dynamic_client.calls, 0)

    def test_fixed_target_without_exact_lineage_fails_closed_after_retry(self) -> None:
        client = StaticClient(
            {
                "document_target": "Complete Phase 2 by 2028.",
                "block_ids": ["b-0002"],
            }
        )

        resolved = resolve_document_target(
            Attribute(
                name="clinical_development_timeline",
                description="Timing and feasibility of clinical development milestones.",
                definition_mode="fixed",
            ),
            "[block:document/b-0002]\nComplete Phase 2 by 2028.",
            client,
        )

        self.assertEqual(client.calls, 2)
        self.assertTrue(resolved.target_resolved)
        self.assertEqual(resolved.document_target, "")
        self.assertEqual(resolved.block_ids, [])

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
            supporting_findings=[finding("https://example.test/used", source="pubmed")],
            attribute_ref="efficacy",
        )
        self.second = Insight(
            statement="A registry lists an adjacent trial.",
            supporting_findings=[
                finding(
                    "https://example.test/unused",
                    source="pubmed",
                    excerpt="The reported efficacy was 90% in the target population.",
                )
            ],
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
                "target_quote": "Target efficacy is at least 80%.",
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
                        "source_quote": "The reported efficacy was 90% in the target population.",
                        "comparability": same_comparability(),
                    },
                    {
                        "value": 82,
                        "unit": "%",
                        "evidence_form": "randomized_trial",
                        "development_phase": "phase_3",
                        "source_record_type": "peer_reviewed",
                        "insight_index": 0,
                        "url": "https://example.test/used",
                        "source_quote": "The reported efficacy was 82% in the target population.",
                        "comparability": same_comparability(),
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
        self.assertEqual(result.benchmark_count, 1)
        self.assertEqual(result.benchmark_median, 82)
        self.assertEqual(result.calibration_status, "insufficient")

    def test_conformity_coverage_pass_recovers_omitted_exact_source_value(self) -> None:
        target = {
            "is_quantitative": True,
            "target_value": 80,
            "comparator": ">=",
            "unit": "%",
            "target_label": "threshold >=80%",
            "target_quote": "Target efficacy is at least 80%.",
            "doc_block_ids": ["document/b-0003"],
            "measurements": [],
        }
        recovered = {
            "measurements": [
                {
                    "value": 82,
                    "unit": "%",
                    "evidence_form": "randomized_trial",
                    "development_phase": "phase_3",
                    "source_record_type": "peer_reviewed",
                    "insight_index": 82.0,
                    "url": "https://example.test/used",
                    "source_quote": "The reported efficacy was 82 percent in the target population.",
                    "comparability": same_comparability(),
                }
            ]
        }
        client = SequenceClient([target, recovered])

        result = score_conformity(
            self.attribute,
            self.document,
            [self.first],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(client.calls, 2)
        self.assertEqual(result.benchmark_count, 1)
        self.assertEqual(result.measurements[0].value, 82)

    def test_numeric_candidates_couple_each_value_to_its_actual_unit(self) -> None:
        efficacy = (
            "In 4577 participants, vaccine efficacy was 50·3% "
            "(95% CI, 34·6% to 62·3%) at 12 months."
        )
        values = [value for value, _ in _numeric_spans_for_unit(efficacy, "%")]
        self.assertEqual(values, [50.3, 95.0, 34.6, 62.3])
        self.assertNotIn(4577.0, values)
        self.assertNotIn(12.0, values)
        self.assertFalse(_value_unit_supported(4577, "%", efficacy))
        self.assertTrue(_value_unit_supported(50.3, "%", efficacy))

        unrelated = "5 randomly selected malarial adhesins were analysed."
        self.assertEqual(_numeric_spans_for_unit(unrelated, "mL/dose"), [])
        self.assertTrue(_value_unit_supported(0.5, "mL/dose", "Dose volume: <0.5 mL/dose."))
        self.assertTrue(_meets_target(0.49, 0.5, "<"))
        self.assertFalse(_meets_target(0.5, 0.5, "<"))

    def test_coverage_classifier_receives_the_exact_document_target(self) -> None:
        target = QuantitativeTarget(
            attribute_ref=self.attribute.name,
            value=80,
            comparator=">=",
            unit="%",
            label="threshold >=80% at six months",
            role="threshold",
            quote="Target efficacy is at least 80% at six months.",
            doc_block_ids=["document/b-0003"],
        )
        prompt = _measurement_system_prompt(
            self.attribute,
            target=target,
            indication="malaria",
            intervention_class="vaccine",
        )
        self.assertIn(
            "Exact target span",
            prompt,
        )
        self.assertIn(target.quote, prompt)

    def test_conformity_never_treats_web_citation_context_as_source_quote(self) -> None:
        web_insight = Insight(
            statement="The cited result reported 75% efficacy.",
            supporting_findings=[
                finding(
                    "https://example.test/web-result",
                    source="web",
                    excerpt="The cited result reported 75% efficacy at 12 months.",
                )
            ],
            attribute_ref="efficacy",
        )
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [
                    {
                        "value": 75,
                        "unit": "%",
                        "insight_index": 0,
                        "url": "https://example.test/web-result",
                        "source_quote": "The cited result reported 75% efficacy at 12 months.",
                        "comparability": same_comparability(),
                    }
                ],
            }
        )

        result = score_conformity(
            self.attribute,
            self.document,
            [web_insight],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(result.measurements, [])
        self.assertEqual(result.excluded_measurements, [])

    def test_conformity_retains_verified_target_when_retrieval_is_empty(self) -> None:
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [],
            }
        )

        result = score_conformity(
            self.attribute,
            self.document,
            [],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.target_value, 80)
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(result.verdict, "No validated claim-compatible comparators")

    def test_conformity_retries_an_apparently_numeric_target_that_was_missed(self) -> None:
        attribute = Attribute(
            name="efficacy",
            description="Target product efficacy",
            document_target="Target efficacy is at least 80%.",
            block_ids=["document/b-0003"],
            target_resolved=True,
        )
        client = SequenceClient(
            [
                {"is_quantitative": False},
                {
                    "is_quantitative": True,
                    "target_value": 80,
                    "comparator": ">=",
                    "unit": "%",
                    "target_label": "threshold >=80%",
                    "target_quote": "Target efficacy is at least 80%.",
                    "doc_block_ids": ["document/b-0003"],
                    "measurements": [],
                },
            ]
        )

        result = score_conformity(
            attribute,
            self.document,
            [],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        self.assertEqual(client.calls, 2)

    def test_conformity_calibrates_target_against_validated_benchmarks(self) -> None:
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 85,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=85%",
                "target_quote": "Target efficacy is at least 85%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [
                    {
                        "value": 82,
                        "unit": "%",
                        "evidence_form": "randomized_trial",
                        "development_phase": "phase_3",
                        "source_record_type": "peer_reviewed",
                        "insight_index": 0,
                        "url": "https://example.test/used",
                        "source_quote": "The reported efficacy was 82% in the target population.",
                        "comparability": same_comparability(),
                    },
                    {
                        "value": 90,
                        "unit": "%",
                        "evidence_form": "registry_record",
                        "development_phase": "phase_2",
                        "source_record_type": "registry",
                        "insight_index": 1,
                        "url": "https://example.test/unused",
                        "source_quote": "The reported efficacy was 90% in the target population.",
                        "comparability": same_comparability(),
                    },
                ],
            }
        )

        result = score_conformity(
            self.attribute,
            "[block:document/b-0003]\nTarget efficacy is at least 85%.",
            [self.first, self.second],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.benchmark_count, 2)
        self.assertEqual(result.benchmark_median, 86)
        self.assertEqual(result.benchmark_lower_quartile, 84)
        self.assertEqual(result.benchmark_upper_quartile, 88)
        self.assertEqual(result.target_percentile, 0.5)
        self.assertEqual(result.ambition_percentile, 0.5)
        self.assertEqual(result.calibration_status, "limited")
        self.assertEqual(result.target_meeting_count, 1)
        self.assertEqual(result.target_meeting_rate, 0.5)
        self.assertEqual(result.benchmark_mean, 86)
        self.assertAlmostEqual(result.benchmark_standard_deviation or 0, 5.657, places=3)
        wire = ConformityOut(**asdict(result))
        self.assertEqual(wire.benchmark_count, 2)
        self.assertEqual(len(wire.measurements), 2)

    def test_conformity_rejects_unquoted_numeric_claims(self) -> None:
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Invented minimum efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [],
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

    def test_conformity_retains_semantic_exclusions_outside_statistics(self) -> None:
        mismatched = same_comparability()
        mismatched["population"] = {
            "relation": "different",
            "reason": "adult evidence versus infant target",
        }
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [
                    {
                        "value": 82,
                        "unit": "%",
                        "evidence_form": "randomized_trial",
                        "development_phase": "phase_3",
                        "source_record_type": "peer_reviewed",
                        "insight_index": 0,
                        "url": "https://example.test/used",
                        "source_quote": "The reported efficacy was 82% in the target population.",
                        "comparability": same_comparability(),
                    },
                    {
                        "value": 90,
                        "unit": "%",
                        "evidence_form": "registry_record",
                        "development_phase": "phase_2",
                        "source_record_type": "registry",
                        "insight_index": 1,
                        "url": "https://example.test/unused",
                        "source_quote": "The reported efficacy was 90% in the target population.",
                        "comparability": mismatched,
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
        self.assertEqual(result.benchmark_count, 1)
        self.assertEqual(len(result.excluded_measurements), 1)
        self.assertIn("population: different", result.excluded_measurements[0].exclusion_reasons[0])

    def test_conformity_rejects_incompatible_units_without_conversion(self) -> None:
        fraction_insight = Insight(
            statement="The reported efficacy was 0.82 as a fraction.",
            supporting_findings=[
                finding(
                    "https://example.test/used",
                    source="pubmed",
                    excerpt="The reported efficacy was 0.82 fraction in the target population.",
                )
            ],
            attribute_ref="efficacy",
        )
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
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
                        "source_quote": "The reported efficacy was 0.82 fraction in the target population.",
                        "comparability": same_comparability(),
                    }
                ],
            }
        )

        result = score_conformity(
            self.attribute,
            self.document,
            [fraction_insight],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(result.measurements, [])
        self.assertEqual(result.excluded_measurements, [])

    def test_conformity_deduplicates_canonical_study_records(self) -> None:
        first_url = "https://clinicaltrials.gov/study/NCT12345678"
        mirror_url = "https://example.test/trial/NCT12345678"
        insights = [
            Insight(
                statement="The study reported efficacy of 82%.",
                supporting_findings=[finding(first_url, source="clinicaltrials")],
                attribute_ref="efficacy",
            ),
            Insight(
                statement="A mirror reports efficacy of 90%.",
                supporting_findings=[
                    finding(
                        mirror_url,
                        source="pubmed",
                        excerpt="The reported efficacy was 90% in the target population.",
                    )
                ],
                attribute_ref="efficacy",
            ),
        ]
        client = StaticClient(
            {
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [
                    {
                        "value": 82,
                        "unit": "%",
                        "insight_index": 0,
                        "url": first_url,
                        "source_quote": "The reported efficacy was 82% in the target population.",
                        "comparability": same_comparability(),
                    },
                    {
                        "value": 90,
                        "unit": "%",
                        "insight_index": 1,
                        "url": mirror_url,
                        "source_quote": "The reported efficacy was 90% in the target population.",
                        "comparability": same_comparability(),
                    },
                ],
            }
        )

        result = score_conformity(
            self.attribute,
            self.document,
            insights,
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.benchmark_count, 1)
        self.assertEqual(result.measurements[0].source_record_id, "nct:nct12345678")
        self.assertIn("duplicate source record", result.excluded_measurements[0].exclusion_reasons[0])

    def test_conformity_keeps_distinct_document_targets_separate(self) -> None:
        document = (
            "[block:document/b-0003]\n"
            "Threshold efficacy is at least 80% at 6 months.\n\n"
            "[block:document/b-0004]\n"
            "Optimal efficacy is at least 90% at 12 months."
        )
        targets = {
            "targets": [
                {
                    "value": 80,
                    "comparator": ">=",
                    "unit": "%",
                    "label": "threshold >=80% at 6 months",
                    "role": "threshold",
                    "quote": "Threshold efficacy is at least 80% at 6 months.",
                    "doc_block_ids": ["document/b-0003"],
                },
                {
                    "value": 90,
                    "comparator": ">=",
                    "unit": "%",
                    "label": "optimal >=90% at 12 months",
                    "role": "optimal",
                    "quote": "Optimal efficacy is at least 90% at 12 months.",
                    "doc_block_ids": ["document/b-0004"],
                },
            ]
        }
        decisions = {
            "measurements": [
                {
                    "value": 82,
                    "url": "https://example.test/used",
                    "comparability": same_comparability(),
                }
            ]
        }
        ledgers = score_conformity_ledgers(
            self.attribute,
            document,
            [self.first],
            SequenceClient([targets, decisions, decisions]),
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual([ledger.target_role for ledger in ledgers], ["threshold", "optimal"])
        self.assertEqual([ledger.target_value for ledger in ledgers], [80, 90])
        self.assertEqual([ledger.target_meeting_count for ledger in ledgers], [1, 0])
        self.assertNotEqual(ledgers[0].target_id, ledgers[1].target_id)

    def test_invalid_axis_span_ids_cannot_enter_the_numeric_cohort(self) -> None:
        target_response = {
            "targets": [
                {
                    "value": 80,
                    "comparator": ">=",
                    "unit": "%",
                    "label": "threshold >=80%",
                    "role": "threshold",
                    "quote": "Target efficacy is at least 80%.",
                    "doc_block_ids": ["document/b-0003"],
                }
            ]
        }

        class WrongSpanClient(StaticClient):
            def call(self, system_prompt, user_message, max_tokens, *, images=None):
                self.calls += 1
                if "enumerate exact quantitative" in system_prompt.lower():
                    return json.dumps(target_response)
                candidate = re.search(r"\[candidate:(qc-[a-f0-9]+)\]", user_message)
                assert candidate is not None
                axis_payload = {
                    axis: {
                        "relation": "same",
                        "reason": "claimed match",
                        "target_span_ids": ["qt-invented"],
                        "source_span_ids": ["qc-invented"],
                    }
                    for axis in same_comparability()
                }
                return json.dumps(
                    {
                        "decisions": [
                            {
                                "candidate_id": candidate.group(1),
                                "comparability": axis_payload,
                            }
                        ]
                    }
                )

        ledgers = score_conformity_ledgers(
            self.attribute,
            self.document,
            [self.first],
            WrongSpanClient({}),
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(ledgers[0].benchmark_count, 0)
        self.assertEqual(len(ledgers[0].excluded_measurements), 1)
        self.assertTrue(
            all(
                evidence.relation == "unknown"
                for evidence in ledgers[0].excluded_measurements[0].axis_evidence.values()
            )
        )

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
