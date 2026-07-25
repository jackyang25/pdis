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
from services.scout.context import (
    render_canonical_binding,
    select_binding_context,
    validated_block_ids,
)
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
    Measurement,
    NumericExpression,
    SemanticSlot,
    load_attributes,
    load_config,
)
from services.scout.stages.conformity import (
    _document_ledger_system_prompt,
    _measurement_system_prompt,
    _expression_supported,
    _meets_target,
    _partition_cohort,
    _validated_targets,
    _validated_measurement_semantic_assessment,
    _value_unit_supported,
    score_conformity as _score_conformity_ledgers,
)
from services.scout.stages.context_validator import (
    mismatch_message,
    validate_document_context,
)
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.evidence_assessor import assess_evidence
from services.scout.stages.insight_extractor import _system_prompt as insight_system_prompt
from services.scout.stages.precedent_classifier import classify_precedent
from services.scout.stages.query_extractor import (
    _parse_queries,
    _target_retrieval_descriptor,
    _target_retrieval_text,
    extract_queries_for_variable,
)
from services.scout.stages.intent_builder import build_retrieval_intents
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
    if "complete numeric-statement ledger" in system_prompt.lower():
        if "targets" in response:
            return {
                **response,
                "status_reason": response.get("status_reason", "Fixture contains targets."),
                "excluded_statements": response.get("excluded_statements", []),
                "targets": [
                    {
                        **target,
                        "expression": target.get("expression") or {
                            "kind": "bound",
                            "value": target.get("value"),
                            "lower": None,
                            "upper": None,
                            "comparator": target.get("comparator", ""),
                            "unit": target.get("unit", ""),
                        },
                        "semantic_profile": target.get(
                            "semantic_profile",
                            semantic_profile(str(target.get("label", "numeric measure"))),
                        ),
                        "comparison_dimensions": target.get("comparison_dimensions") or [
                            field_name
                            for field_name, slot in target.get(
                                "semantic_profile",
                                semantic_profile(str(target.get("label", "numeric measure"))),
                            ).items()
                            if slot["state"] in {"specified", "other"}
                        ],
                        "semantic_provenance": target.get("semantic_provenance")
                        or semantic_provenance(
                            target.get(
                                "semantic_profile",
                                semantic_profile(str(target.get("label", "numeric measure"))),
                            ),
                            target.get("quote", ""),
                            target.get("doc_block_ids", []),
                        ),
                        "provenance_spans": target.get("provenance_spans") or [{
                            "quote": target.get("quote", ""),
                            "block_ids": target.get("doc_block_ids", []),
                        }],
                    }
                    for target in response.get("targets", [])
                    if isinstance(target, dict)
                ],
            }
        if not response.get("is_quantitative"):
            return {
                "status_reason": "Fixture has no numeric target.",
                "targets": [],
                "excluded_statements": response.get("excluded_statements", []),
            }
        return {
            "status_reason": "Fixture contains a numeric target.",
            "excluded_statements": [],
            "targets": [
                {
                    "expression": {
                        "kind": "bound",
                        "value": response.get("target_value"),
                        "lower": None,
                        "upper": None,
                        "comparator": response.get("comparator"),
                        "unit": response.get("unit"),
                    },
                    "role": "threshold",
                    "comparison_dimensions": [
                        field_name
                        for field_name, slot in (
                            response.get("semantic_profile")
                            or semantic_profile(str(response.get("target_label", "numeric measure")))
                        ).items()
                        if slot["state"] in {"specified", "other"}
                    ],
                    "quote": response.get("target_quote"),
                    "doc_block_ids": response.get("doc_block_ids", []),
                    "semantic_profile": response.get("semantic_profile") or semantic_profile(
                        str(response.get("target_label", "numeric measure"))
                    ),
                    "semantic_provenance": semantic_provenance(
                        response.get("semantic_profile") or semantic_profile(
                            str(response.get("target_label", "numeric measure"))
                        ),
                        str(response.get("target_quote", "")),
                        response.get("doc_block_ids", []),
                    ),
                    "provenance_spans": [{
                        "quote": response.get("target_quote", ""),
                        "block_ids": response.get("doc_block_ids", []),
                    }],
                }
            ]
        }
    if "extract complete numeric measurements" not in system_prompt.lower():
        return response
    if "sources" in response:
        return response
    sources = re.findall(r"\[source:(sp-[a-f0-9]+)\] url=([^ |]+)", user_message)
    decisions = []
    for source_id, url in sources:
        source_measurements = [
            item for item in response.get("measurements", [])
            if isinstance(item, dict) and item.get("url") == url
        ]
        normalized = []
        for item in source_measurements:
            normalized.append({
                "quote": item.get("source_quote", ""),
                "expression": {
                    "kind": item.get("expression_kind", "point_estimate"),
                    "unit": item.get("unit", ""),
                    "value": item.get("value"),
                    "lower": item.get("lower"),
                    "upper": item.get("upper"),
                    "comparator": item.get("comparator", ""),
                },
                "semantic_assessment": item.get("semantic_assessment") or semantic_assessment(
                    source_profile=item.get("semantic_profile"),
                    comparability=item.get("comparability"),
                    ownership=item.get("source_ownership"),
                ),
            })
        decisions.append({
            "source_id": source_id,
            "status": "measurements_found" if normalized else "no_relevant_measurement",
            "reason": "Fixture source reviewed.",
            "measurements": normalized,
        })
    return {"sources": decisions}


def semantic_profile(measure: str = "numeric measure") -> dict:
    return {
        field: {
            "state": "specified" if field == "measure" else "not_specified",
            "value": measure if field == "measure" else "",
            "other": "",
        }
        for field in (
            "measure", "endpoint", "intervention", "population", "regimen",
            "time_horizon", "statistic", "conditions",
        )
    }


def semantic_provenance(profile: dict, quote: str, block_ids: list[str]) -> dict:
    span = {"quote": quote, "block_ids": block_ids}
    return {
        field_name: [span] if slot["state"] in {"specified", "other"} else []
        for field_name, slot in profile.items()
    }


def extract_quantitative_targets(
    attribute,
    document,
    client,
    *,
    semantic_context="",
    **_kwargs,
):
    """Exercise the shared deterministic validator with historical fixtures."""
    parsed = json.loads(
        client.call(
            "complete numeric-statement ledger",
            document,
            16_000,
        )
    )
    return _validated_targets(
        parsed.get("targets") if isinstance(parsed, dict) else None,
        attribute=attribute,
        doc_text=document,
        semantic_context=semantic_context or document,
    )


def extract_quantitative_target_set(*args, **kwargs):
    targets = extract_quantitative_targets(*args, **kwargs)
    return type(
        "TargetFixtureResult",
        (),
        {
            "status": "present" if targets else "uncertain",
            "targets": targets,
            "dispositions": [],
        },
    )()


def score_conformity_ledgers(attribute, document, insights, client, **kwargs):
    # Production calibration receives a resolved binding whose text/blocks agree
    # with the supplied document context. Keep historical fixtures at that same
    # boundary even when an individual test swaps the numeric document text.
    binding_text = re.sub(r"\[block:[^\]]+\][^\n]*\n", "", document).strip()
    binding_ids = re.findall(r"\[block:([^\]]+)\]", document)
    attribute = replace(
        attribute,
        document_target=binding_text,
        block_ids=binding_ids,
        target_resolved=True,
    )
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
        axis: {"state": "yes", "reason": f"compatible {axis.replace('_', ' ')}"}
        for axis in (
            "measure", "endpoint",
            "population",
            "intervention",
            "regimen",
            "time_horizon",
            "statistic",
            "conditions",
        )
    }


def semantic_assessment(
    *,
    source_profile: dict | None = None,
    comparability: dict | None = None,
    ownership: dict | None = None,
) -> dict:
    profile = source_profile or semantic_profile()
    decisions = comparability or same_comparability()
    return {
        "source_ownership": ownership or {
            "state": "yes",
            "reason": "",
        },
        "dimensions": {
            field_name: {
                "source": profile[field_name],
                "compatibility": decisions[field_name],
            }
            for field_name in profile
        },
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

    def test_tracking_parameters_do_not_create_distinct_source_identity(self) -> None:
        first = finding(
            "https://example.test/paper?id=4&utm_source=web",
            query="first",
            source="web",
        )
        second = finding(
            "https://example.test/paper?id=4&utm_campaign=test",
            query="second",
            source="pubmed",
        )

        self.assertEqual(first.url, "https://example.test/paper?id=4")
        self.assertEqual(second.url, first.url)

    def test_reference_excerpt_cannot_leak_into_merged_evidence(self) -> None:
        evidence = finding(
            "https://example.test/shared",
            source="pubmed",
            excerpt="Evidence-owned passage.",
        )
        reference = finding(
            "https://example.test/shared",
            source="chembl",
            excerpt="Reference catalog description that is much longer than the evidence passage.",
        )
        reference.evidence_role = "reference"

        merged = merge_findings(evidence, reference)
        self.assertEqual(merged.evidence_role, "evidence")
        self.assertEqual(merged.excerpt, "Evidence-owned passage.")
        self.assertEqual(merged.excerpt_source_lane, "pubmed")

        reference_first = finding(
            "https://example.test/shared-2",
            source="chembl",
            excerpt="Long reference-only catalog description.",
        )
        reference_first.evidence_role = "reference"
        evidence_second = finding(
            "https://example.test/shared-2",
            source="pubmed",
            excerpt="Short evidence passage.",
        )
        merged_reversed = merge_findings(reference_first, evidence_second)
        self.assertEqual(merged_reversed.excerpt, "Short evidence passage.")
        self.assertEqual(merged_reversed.excerpt_source_lane, "pubmed")

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
            self.assertTrue(config.quantitative_target_framing, path.name)
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
        raw = [
            {
                "query": "malaria vaccine dose target",
                "doc_block_ids": ["doc/b-0002", "invented/b-9999"],
                "target_ids": [],
            }
        ]

        intents = _parse_queries(raw, {"doc/b-0002"})

        self.assertEqual(intents[0].doc_block_ids, ["doc/b-0002"])

    def test_each_canonical_numeric_target_gets_retrieval_coverage_and_lineage(self) -> None:
        targets = []
        for value, role, quote, block_id, time_horizon in (
            (80, "threshold", "At least 80% at 6 months.", "doc/b-0002", "6 months"),
            (90, "optimal", "At least 90% at 12 months.", "doc/b-0003", "12 months"),
        ):
            profile = semantic_profile("protective efficacy")
            profile.update({
                "endpoint": {
                    "state": "specified",
                    "value": "malaria infection",
                    "other": "",
                },
                "intervention": {
                    "state": "specified",
                    "value": "malaria vaccine",
                    "other": "",
                },
                "population": {
                    "state": "specified",
                    "value": "children",
                    "other": "",
                },
                "regimen": {
                    "state": "specified",
                    "value": "primary immunization series",
                    "other": "",
                },
                "time_horizon": {
                    "state": "specified",
                    "value": time_horizon,
                    "other": "",
                },
                "statistic": {
                    "state": "specified",
                    "value": "efficacy point estimate",
                    "other": "",
                },
            })
            targets.append(QuantitativeTarget(
                attribute_ref="efficacy",
                expression=NumericExpression(
                    kind="bound", value=value, comparator=">=", unit="%"
                ),
                role=role,
                quote=quote,
                doc_block_ids=[block_id],
                semantic_profile=profile,
            ))
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
        target_queries = [query for query in queries if query.target_ids]
        self.assertTrue(
            all("protective efficacy" in query.text for query in target_queries)
        )
        self.assertTrue(all("malaria infection" in query.text for query in target_queries))
        self.assertTrue(
            all("reported numeric results" in query.text for query in target_queries)
        )
        self.assertFalse(
            any("80" in query.text or "90" in query.text for query in target_queries)
        )
        self.assertFalse(
            any(
                "threshold" in query.text or "optimal" in query.text
                for query in target_queries
            )
        )
        descriptors = [_target_retrieval_descriptor(target) for target in targets]
        self.assertEqual(descriptors[0]["dimensions"]["time_horizon"], "6 months")
        self.assertNotIn("value", descriptors[0])
        self.assertNotIn("comparator", descriptors[0])
        self.assertNotIn("role", descriptors[0])
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

    def test_query_projection_removes_only_the_target_magnitude(self) -> None:
        profile = semantic_profile("storage temperature tolerance")
        profile["endpoint"] = {
            "state": "specified",
            "value": "stability at temperatures greater than +8°C",
            "other": "",
        }
        profile["time_horizon"] = {
            "state": "specified",
            "value": "extended storage period",
            "other": "",
        }
        target = QuantitativeTarget(
            attribute_ref="device.storage",
            expression=NumericExpression(kind="bound", value=8, comparator=">", unit="°C"),
            role="optimal",
            quote="stable for extended periods at temperatures greater than +8°C",
            doc_block_ids=["document/b-0004"],
            semantic_profile=profile,
        )

        descriptor = _target_retrieval_descriptor(target)
        query_text = _target_retrieval_text(target)

        self.assertNotIn("endpoint", descriptor["dimensions"])
        self.assertEqual(
            descriptor["dimensions"]["time_horizon"], "extended storage period"
        )
        self.assertNotIn("8", query_text)
        self.assertIn("storage temperature tolerance", query_text)

        dose_profile = semantic_profile("dose volume below 0.5 mL/dose")
        dose_target = QuantitativeTarget(
            attribute_ref="device.dose_volume",
            expression=NumericExpression(
                kind="bound", value=0.5, comparator="<", unit="mL/dose"
            ),
            role="optimal",
            quote="Dose volume below 0.5 mL/dose.",
            doc_block_ids=["document/b-0005"],
            semantic_profile=dose_profile,
        )
        self.assertNotIn(
            "measure", _target_retrieval_descriptor(dose_target)["dimensions"]
        )

    def test_generated_query_that_restates_target_magnitude_is_replaced(self) -> None:
        profile = semantic_profile("storage temperature tolerance")
        target = QuantitativeTarget(
            attribute_ref="device.storage",
            expression=NumericExpression(
                kind="bound", value=8, comparator=">", unit="°C"
            ),
            role="optimal",
            quote="Temperature tolerance greater than 8°C.",
            doc_block_ids=["document/b-0004"],
            semantic_profile=profile,
        )
        attribute = Attribute(
            "device.storage",
            "Storage temperature tolerance",
            document_target=target.quote,
            block_ids=target.doc_block_ids,
            target_resolved=True,
            quantitative_targets=[target],
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
        invalid = [{
            "query": "device stability above 8°C reported results",
            "doc_block_ids": ["document/b-0004"],
            "target_ids": [target.id],
        }]

        queries = extract_queries_for_variable(
            attribute,
            config,
            SequenceClient([
                invalid,
                [{
                    "query": "device stability above eight degrees Celsius reported results",
                    "doc_block_ids": ["document/b-0004"],
                    "target_ids": [],
                }],
            ]),
            indication="example condition",
            queries_per_variable=1,
            document_context="[block:document/b-0004]\nTemperature tolerance greater than 8°C.",
        )

        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].target_ids, [target.id])
        self.assertNotIn("8", queries[0].text)
        self.assertIn("reported numeric results", queries[0].text)

    def test_target_query_rejects_locale_decimal_magnitude(self) -> None:
        target = QuantitativeTarget(
            attribute_ref="device.dose_volume",
            expression=NumericExpression(
                kind="bound", value=0.5, comparator="<", unit="mL/dose"
            ),
            role="optimal",
            quote="Dose volume below 0.5 mL/dose.",
            doc_block_ids=["document/b-0005"],
            semantic_profile=semantic_profile("dose volume"),
        )
        attribute = Attribute(
            "device.dose_volume",
            "Volume per dose",
            document_target=target.quote,
            block_ids=target.doc_block_ids,
            target_resolved=True,
            quantitative_targets=[target],
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
        invalid = [{
            "query": "dose volume below 0,5 mL reported results",
            "doc_block_ids": ["document/b-0005"],
            "target_ids": [target.id],
        }]

        queries = extract_queries_for_variable(
            attribute,
            config,
            SequenceClient([invalid, invalid]),
            indication="example condition",
            queries_per_variable=1,
            document_context="[block:document/b-0005]\nDose volume below 0.5 mL/dose.",
        )

        self.assertEqual(len(queries), 1)
        self.assertNotIn("0.5", queries[0].text)
        self.assertNotIn("0,5", queries[0].text)

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
                    "spans": [
                        {
                            "quote": "RTS,S approval is targeted for 2030.",
                            "block_ids": ["document/b-0002"],
                        }
                    ],
                    "entities": [
                        {
                            "name": "RTS,S",
                            "entity_type": "vaccine",
                            "identifier": "",
                        }
                    ],
                }
            ]
        )

        units = extract_units(
            "[block:document/b-0002]\nRTS,S approval is targeted for 2030.",
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
        self.assertEqual(
            units[0].document_target,
            "RTS,S approval is targeted for 2030.",
        )
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

    def test_reasoning_binding_excludes_adjacent_table_cell_content(self) -> None:
        blocks = [
            block(
                3,
                "Dose volume: <0.5 mL/dose. Schedule: three annual doses.",
            )
        ]
        attribute = Attribute(
            name="vaccine.dose_volume",
            description="Volume per dose in mL",
            block_ids=["document/b-0003"],
            document_target="Dose volume: <0.5 mL/dose.",
            target_resolved=True,
        )

        raw = select_binding_context(blocks, attribute)
        canonical = render_canonical_binding(attribute)

        self.assertIn("three annual doses", raw)
        self.assertNotIn("three annual doses", canonical)
        self.assertIn("[block:document/b-0003]", canonical)
        self.assertIn(attribute.document_target, canonical)

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
        self.attribute = Attribute(
            "efficacy",
            "Target product efficacy",
            block_ids=["document/b-0003"],
            document_target="Target efficacy is at least 80%.",
            target_resolved=True,
        )

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
        self.assertEqual(result.doc_target, "Target efficacy is at least 80%.")
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

    def test_drift_fails_closed_without_valid_document_lineage(self) -> None:
        client = StaticClient(
            [
                {
                    "index": 0,
                    "relation": "confirms",
                    "reason": "The endpoint supports the stated target.",
                    "doc_block_ids": ["invented/b-9999"],
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

        self.assertEqual(result[0].relation, "unrelated")
        self.assertEqual(result[0].doc_block_ids, [])
        self.assertIn("lineage", result[0].reason)

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
        self.assertEqual(result.measurements[0].expression.kind, "point_estimate")
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
                    "source_quote": "The reported efficacy was 82% in the target population.",
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

    def test_numeric_expression_verification_couples_values_to_their_unit(self) -> None:
        efficacy = (
            "In 4577 participants, vaccine efficacy was 50·3% "
            "(95% CI, 34·6% to 62·3%) at 12 months."
        )
        self.assertFalse(_value_unit_supported(4577, "%", efficacy))
        self.assertTrue(_value_unit_supported(50.3, "%", efficacy))
        self.assertTrue(_expression_supported(
            NumericExpression(
                kind="confidence_interval", unit="%", lower=34.6, upper=62.3
            ),
            efficacy,
        ))
        self.assertTrue(_value_unit_supported(0.5, "mL/dose", "Dose volume: <0.5 mL/dose."))
        self.assertTrue(_meets_target(0.49, 0.5, "<"))
        self.assertFalse(_meets_target(0.5, 0.5, "<"))
        self.assertTrue(_meets_target(2, 2, "="))
        self.assertFalse(_meets_target(3, 2, "="))

    def test_range_is_one_expression_not_two_point_candidates(self) -> None:
        expression = NumericExpression(kind="range", unit="%", lower=36, upper=50)
        self.assertTrue(_expression_supported(
            expression, "Observed efficacy ranged from 36-50% across sites."
        ))

    def test_irrelevant_numbers_resolve_at_passage_level_without_fragment_noise(self) -> None:
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        attribute = replace(self.attribute, quantitative_targets=[target])
        insight = Insight(
            statement="The study enrolled participants.",
            supporting_findings=[finding(
                "https://example.test/enrollment",
                source="pubmed",
                excerpt="The trial enrolled 4,577 participants and followed them for 12 months.",
            )],
            attribute_ref="efficacy",
        )

        class NoMeasurementClient:
            def call(self, system_prompt, user_message, max_tokens, *, images=None):
                source = re.search(r"\[source:(sp-[a-f0-9]+)\]", user_message)
                assert source is not None
                return json.dumps({"sources": [{
                    "source_id": source.group(1),
                    "status": "no_relevant_measurement",
                    "reason": "Only enrollment and follow-up duration are reported.",
                    "measurements": [],
                }]})

        result = _score_conformity_ledgers(
            attribute,
            [insight],
            NoMeasurementClient(),
            indication="malaria",
            intervention_class="vaccine",
        )[0]
        self.assertEqual(result.measurements, [])
        self.assertEqual(result.excluded_measurements, [])
        self.assertEqual(result.source_dispositions[0].status, "no_relevant_measurement")

    def test_below_target_point_estimate_remains_comparable(self) -> None:
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=50.3, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=semantic_profile("protective efficacy")
            ),
            candidate_id="qc-below",
            source_record_id="doi:10.1/example",
            semantic_status="comparable",
            semantic_reason="Same efficacy endpoint, population, and time horizon.",
        )
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="threshold",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        included, excluded = _partition_cohort([measurement], target)
        self.assertEqual(included, [measurement])
        self.assertEqual(excluded, [])
        self.assertFalse(_meets_target(measurement.value, 80, ">"))

    def test_comparable_rate_is_an_atomic_scalar(self) -> None:
        measurement = Measurement(
            expression=NumericExpression(
                kind="rate", value=2.4, unit="per 100 person-years"
            ),
            semantic_assessment=semantic_assessment(
                source_profile=semantic_profile("incidence rate")
            ),
            candidate_id="qm-rate",
            source_record_id="doi:10.1/rate",
            semantic_status="comparable",
            semantic_reason="Same incidence rate and population.",
        )
        target = QuantitativeTarget(
            attribute_ref="incidence",
            expression=NumericExpression(
                kind="bound", value=3, comparator="<=", unit="per 100 person-years"
            ),
            role="threshold",
            quote="Incidence should be no more than 3 per 100 person-years.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("incidence rate"),
        )
        included, excluded = _partition_cohort([measurement], target)
        self.assertEqual(included, [measurement])
        self.assertEqual(excluded, [])

    def test_endpoint_mismatch_is_context_not_a_comparator(self) -> None:
        target_profile = semantic_profile("protective efficacy")
        target_profile["endpoint"] = {
            "state": "specified",
            "value": "prevention of infection",
            "other": "",
        }
        source_profile = semantic_profile("protective efficacy")
        source_profile["endpoint"] = {
            "state": "specified",
            "value": "clinical malaria",
            "other": "",
        }
        decisions = same_comparability()
        decisions["endpoint"] = {
            "state": "no",
            "reason": "Clinical disease is not infection or parasitemia.",
        }
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=77, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=source_profile,
                comparability=decisions,
            ),
            candidate_id="qm-endpoint-mismatch",
            source_record_id="clinical_trial:nct-example",
        )
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=target_profile,
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [])
        self.assertEqual(excluded, [measurement])
        self.assertEqual(measurement.semantic_status, "contextual")

    def test_background_claim_is_context_even_when_dimensions_match(self) -> None:
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=77, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=semantic_profile("protective efficacy"),
                ownership={
                    "state": "no",
                    "reason": "The registry passage summarizes an earlier study.",
                },
            ),
            candidate_id="qm-background",
            source_record_id="clinical_trial:nct-example",
        )
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [])
        self.assertEqual(excluded, [measurement])
        self.assertEqual(measurement.semantic_status, "contextual")

    def test_unknown_source_ownership_fails_closed(self) -> None:
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=77, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=semantic_profile("protective efficacy"),
                ownership={
                    "state": "unknown",
                    "reason": "The retained passage does not identify who produced the result.",
                },
            ),
            candidate_id="qm-unknown-owner",
            source_record_id="clinical_trial:nct-example",
        )
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [])
        self.assertEqual(excluded, [measurement])
        self.assertEqual(measurement.semantic_status, "unknown")

    def test_unconstrained_dimension_does_not_exclude_a_comparator(self) -> None:
        source_profile = semantic_profile("protective efficacy")
        source_profile["population"] = {
            "state": "specified",
            "value": "adults",
            "other": "",
        }
        decisions = same_comparability()
        decisions["population"] = {
            "state": "no",
            "reason": "The source population is adults.",
        }
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=77, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=source_profile,
                comparability=decisions,
            ),
            source_record_id="doi:10.1/unconstrained-population",
        )
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [measurement])
        self.assertEqual(excluded, [])

    def test_ambiguous_target_dimension_fails_closed(self) -> None:
        target_profile = semantic_profile("protective efficacy")
        target_profile["endpoint"] = {
            "state": "unknown",
            "value": "",
            "other": "",
        }
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=77, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=semantic_profile("protective efficacy")
            ),
            source_record_id="doi:10.1/ambiguous-target",
        )
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=target_profile,
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [])
        self.assertEqual(excluded, [measurement])
        self.assertEqual(measurement.semantic_status, "unknown")

    def test_target_condition_is_part_of_admission(self) -> None:
        source_profile = semantic_profile("protective efficacy")
        source_profile["conditions"] = {
            "state": "specified",
            "value": "controlled human infection",
            "other": "",
        }
        comparability = same_comparability()
        comparability["conditions"] = {
            "state": "no",
            "reason": "The estimate comes from CHMI rather than a field trial.",
        }
        measurement = Measurement(
            expression=NumericExpression(kind="point_estimate", value=80, unit="%"),
            semantic_assessment=semantic_assessment(
                source_profile=source_profile,
                comparability=comparability,
            ),
            source_record_id="doi:10.1/chmi",
        )
        target_profile = semantic_profile("protective efficacy")
        target_profile["conditions"] = {
            "state": "specified",
            "value": "field trial rather than CHMI",
            "other": "",
        }
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(kind="bound", value=80, comparator=">", unit="%"),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=target_profile,
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [])
        self.assertEqual(excluded, [measurement])
        self.assertEqual(measurement.semantic_status, "contextual")

    def test_repeated_target_statements_merge_provenance_not_ledgers(self) -> None:
        document = (
            "[block:document/b-0003]\nTarget efficacy is at least 80%.\n\n"
            "[block:document/b-0004]\nThe efficacy target is at least 80%."
        )
        attribute = replace(
            self.attribute,
            document_target=(
                "Target efficacy is at least 80%. The efficacy target is at least 80%."
            ),
            block_ids=["document/b-0003", "document/b-0004"],
        )
        profile = semantic_profile("protective efficacy")
        targets = extract_quantitative_targets(
            attribute,
            document,
            StaticClient({
                "targets": [
                    {
                        "value": 80, "comparator": ">=", "unit": "%",
                        "label": "efficacy threshold", "role": "threshold",
                        "quote": "Target efficacy is at least 80%.",
                        "doc_block_ids": ["document/b-0003"],
                        "semantic_profile": profile,
                    },
                    {
                        "value": 80, "comparator": ">=", "unit": "%",
                        "label": "efficacy threshold", "role": "threshold",
                        "quote": "The efficacy target is at least 80%.",
                        "doc_block_ids": ["document/b-0004"],
                        "semantic_profile": profile,
                    },
                ]
            }),
            indication="malaria",
            intervention_class="vaccine",
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(len(targets[0].provenance_spans), 2)
        self.assertEqual(len(targets[0].semantic_provenance["measure"]), 2)

    def test_target_meaning_can_use_cited_bounded_definition_context(self) -> None:
        binding = "[block:document/b-0004]\nTarget response is at least 80% at 12 months."
        semantic_context = (
            "[block:document/b-0002]\nResponse means confirmed biomarker clearance.\n\n"
            + binding
        )
        attribute = replace(
            self.attribute,
            name="drug.response",
            description="Document-defined treatment response",
            document_target="Target response is at least 80% at 12 months.",
            block_ids=["document/b-0004"],
        )
        profile = semantic_profile("response rate")
        profile["endpoint"] = {
            "state": "specified",
            "value": "confirmed biomarker clearance",
            "other": "",
        }
        profile["time_horizon"] = {
            "state": "specified",
            "value": "12 months",
            "other": "",
        }
        provenance = semantic_provenance(
            profile,
            "Target response is at least 80% at 12 months.",
            ["document/b-0004"],
        )
        provenance["endpoint"] = [{
            "quote": "Response means confirmed biomarker clearance.",
            "block_ids": ["document/b-0002"],
        }]

        targets = extract_quantitative_targets(
            attribute,
            binding,
            StaticClient({
                "targets": [{
                    "expression": {
                        "kind": "bound",
                        "value": 80,
                        "comparator": ">=",
                        "unit": "%",
                    },
                    "role": "threshold",
                    "quote": "Target response is at least 80% at 12 months.",
                    "doc_block_ids": ["document/b-0004"],
                    "semantic_profile": profile,
                    "semantic_provenance": provenance,
                }]
            }),
            indication="example condition",
            intervention_class="drug",
            semantic_context=semantic_context,
        )

        self.assertEqual(len(targets), 1)
        self.assertEqual(
            targets[0].semantic_profile["endpoint"].value,
            "confirmed biomarker clearance",
        )
        self.assertEqual(
            targets[0].semantic_provenance["endpoint"][0].block_ids,
            ["document/b-0002"],
        )

    def test_target_with_uncited_specified_semantics_fails_closed(self) -> None:
        document = "[block:document/b-0003]\nTarget response is at least 80%."
        attribute = replace(
            self.attribute,
            name="diagnostic.response",
            document_target="Target response is at least 80%.",
            block_ids=["document/b-0003"],
        )
        profile = semantic_profile("response rate")
        profile["population"] = {
            "state": "specified",
            "value": "adults",
            "other": "",
        }
        provenance = semantic_provenance(
            profile,
            "Target response is at least 80%.",
            ["document/b-0003"],
        )
        provenance["population"] = []

        targets = extract_quantitative_targets(
            attribute,
            document,
            StaticClient({
                "targets": [{
                    "expression": {
                        "kind": "bound",
                        "value": 80,
                        "comparator": ">=",
                        "unit": "%",
                    },
                    "role": "threshold",
                    "quote": "Target response is at least 80%.",
                    "doc_block_ids": ["document/b-0003"],
                    "semantic_profile": profile,
                    "semantic_provenance": provenance,
                }]
            }),
            indication="example condition",
            intervention_class="diagnostic",
        )

        self.assertEqual(targets, [])

    def test_insight_prompt_preserves_source_claim_ownership(self) -> None:
        prompt = insight_system_prompt(
            indication="example condition",
            intervention_class="drug",
            attribute_ref="efficacy",
            attribute_description="Treatment effect",
        )

        self.assertIn("background from a prior study", prompt)
        self.assertIn("not observed results", prompt)

    def test_exact_scalar_target_accepts_written_number_with_exact_provenance(self) -> None:
        document = "[block:document/b-0003]\nOptimal primary series: two doses."
        attribute = replace(
            self.attribute,
            name="drug.dose_count",
            description="Number of doses in the primary series",
            document_target="Optimal primary series: two doses.",
            block_ids=["document/b-0003"],
        )
        targets = extract_quantitative_targets(
            attribute,
            document,
            StaticClient({
                "targets": [{
                    "expression": {
                        "kind": "bound",
                        "value": 2,
                        "comparator": "=",
                        "unit": "doses",
                    },
                    "role": "optimal",
                    "quote": "Optimal primary series: two doses.",
                    "doc_block_ids": ["document/b-0003"],
                    "semantic_profile": semantic_profile("primary-series dose count"),
                }]
            }),
            indication="example condition",
            intervention_class="drug",
        )

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].comparator, "=")
        self.assertEqual(targets[0].value, 2)

    def test_target_range_cannot_be_collapsed_into_one_scalar(self) -> None:
        document = "[block:document/b-0003]\nDuration is 2 to 3 years."
        attribute = replace(
            self.attribute,
            name="drug.duration",
            document_target="Duration is 2 to 3 years.",
            block_ids=["document/b-0003"],
        )
        extraction = extract_quantitative_target_set(
            attribute,
            document,
            StaticClient({
                "targets": [{
                    "expression": {
                        "kind": "bound",
                        "value": 3,
                        "comparator": "=",
                        "unit": "years",
                    },
                    "role": "other",
                    "quote": "Duration is 2 to 3 years.",
                    "doc_block_ids": ["document/b-0003"],
                    "semantic_profile": semantic_profile("duration"),
                }],
            }),
            indication="example condition",
            intervention_class="drug",
        )

        self.assertEqual(extraction.status, "uncertain")
        self.assertEqual(extraction.targets, [])

    def test_hyphenated_positive_range_cannot_become_negative_scalar(self) -> None:
        document = "[block:document/b-0003]\nObserved efficacy was 36-50%."
        attribute = replace(
            self.attribute,
            document_target="Observed efficacy was 36-50%.",
            block_ids=["document/b-0003"],
        )
        targets = extract_quantitative_targets(
            attribute,
            document,
            StaticClient({
                "targets": [{
                    "expression": {
                        "kind": "bound",
                        "value": -50,
                        "comparator": "=",
                        "unit": "%",
                    },
                    "role": "other",
                    "quote": "Observed efficacy was 36-50%.",
                    "doc_block_ids": ["document/b-0003"],
                    "semantic_profile": semantic_profile("efficacy"),
                }],
            }),
            indication="example condition",
            intervention_class="vaccine",
        )

        self.assertEqual(targets, [])

    def test_target_contract_separates_unit_from_conditions(self) -> None:
        attribute = replace(
            self.attribute,
            name="diagnostic.stability",
            document_target="Stable for at least 6 hours at 37°C.",
            block_ids=["document/b-0003"],
        )
        prompt = _document_ledger_system_prompt(
            [attribute],
            indication="example condition",
            intervention_class="diagnostic",
            framing="",
        )

        self.assertIn("canonical fields", prompt.lower())
        self.assertIn("exact substring", prompt)
        self.assertIn("Conditions includes only settings", prompt)
        self.assertIn("change numeric interpretation", prompt)
        self.assertIn("unknown and comparison-required", prompt)

    def test_identical_scalar_under_multiple_roles_preserves_both_roles(self) -> None:
        document = (
            "[block:document/b-0003]\nOptimal: at most 2 products.\n\n"
            "[block:document/b-0004]\nThreshold: at most 2 products."
        )
        attribute = replace(
            self.attribute,
            name="vaccine.presentation",
            document_target="Optimal and threshold are at most 2 products.",
            block_ids=["document/b-0003", "document/b-0004"],
        )
        profile = semantic_profile("number of products")
        targets = []
        for role, block_id, quote in (
            ("optimal", "document/b-0003", "Optimal: at most 2 products."),
            ("threshold", "document/b-0004", "Threshold: at most 2 products."),
        ):
            targets.append({
                "expression": {
                    "kind": "bound",
                    "value": 2,
                    "comparator": "<=",
                    "unit": "products",
                },
                "role": role,
                "quote": quote,
                "doc_block_ids": [block_id],
                "semantic_profile": profile,
                "semantic_provenance": semantic_provenance(
                    profile, quote, [block_id]
                ),
            })

        extracted = extract_quantitative_targets(
            attribute,
            document,
            StaticClient({
                "status": "present",
                "status_reason": "The repeated scalar has two document labels.",
                "targets": targets,
            }),
            indication="example condition",
            intervention_class="vaccine",
        )

        self.assertEqual(len(extracted), 2)
        self.assertEqual(
            {target.role for target in extracted}, {"optimal", "threshold"}
        )

    def test_semantic_slot_preserves_other_without_guessing(self) -> None:
        slot = SemanticSlot(state="other", other="Composite endpoint not in the core schema")
        self.assertEqual(slot.state, "other")
        self.assertIn("Composite endpoint", slot.other)

    def test_coverage_classifier_receives_the_exact_document_target(self) -> None:
        target = QuantitativeTarget(
            attribute_ref=self.attribute.name,
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80% at six months.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        prompt = _measurement_system_prompt(
            self.attribute,
            target=target,
            indication="malaria",
            intervention_class="vaccine",
        )
        self.assertIn('target-constrained fields: ["measure"]', prompt)
        self.assertIn("source-stated measure", prompt)
        self.assertNotIn("source-stated endpoint", prompt)
        self.assertIn("Target semantic profile", prompt)
        self.assertNotIn(target.quote, prompt)
        self.assertNotIn("80", prompt)
        self.assertIn("self-contained exact quote", prompt)
        self.assertIn("storage temperature", prompt)
        self.assertIn("return uncertain rather than a measurement", prompt)

    def test_measurement_contract_accepts_only_target_constrained_dimensions(self) -> None:
        assessment = _validated_measurement_semantic_assessment(
            {
                "source_ownership": {"state": "yes", "reason": ""},
                "dimensions": {
                    "measure": {
                        "source": {
                            "state": "specified",
                            "value": "protective efficacy",
                            "other": "",
                        },
                        "compatibility": {"state": "yes", "reason": ""},
                    }
                },
            },
            required_fields={"measure"},
        )

        self.assertIsNotNone(assessment)
        assert assessment is not None
        self.assertEqual(
            set(assessment.dimensions),
            {
                "measure",
                "endpoint",
                "intervention",
                "population",
                "regimen",
                "time_horizon",
                "statistic",
                "conditions",
            },
        )
        self.assertEqual(
            assessment.dimensions["endpoint"].source.state, "not_specified"
        )
        self.assertEqual(
            assessment.dimensions["endpoint"].compatibility.state, "yes"
        )

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

    def test_conformity_does_not_retry_and_rank_an_omitted_numeric_target(self) -> None:
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

        self.assertIsNone(result)
        self.assertEqual(client.calls, 1)

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
        target_profile = semantic_profile("protective efficacy")
        target_profile["population"] = {
            "state": "specified",
            "value": "infants",
            "other": "",
        }
        infant_profile = semantic_profile("protective efficacy")
        infant_profile["population"] = target_profile["population"]
        adult_profile = semantic_profile("protective efficacy")
        adult_profile["population"] = {
            "state": "specified",
            "value": "adults",
            "other": "",
        }
        mismatched = same_comparability()
        mismatched["population"] = {
            "state": "no",
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
                "semantic_profile": target_profile,
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
                        "semantic_profile": infant_profile,
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
                        "semantic_profile": adult_profile,
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
        self.assertIn("semantic status: contextual", result.excluded_measurements[0].exclusion_reasons[0])

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
        self.assertEqual(len(result.excluded_measurements), 1)
        self.assertIn(
            "unit is incompatible",
            result.excluded_measurements[0].exclusion_reasons[0],
        )

    def test_conflicting_values_from_one_study_fail_closed(self) -> None:
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
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(len(result.excluded_measurements), 2)
        self.assertTrue(all(
            "no primary estimate was deterministically identifiable" in item.exclusion_reasons[0]
            for item in result.excluded_measurements
        ))

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
                    "required_comparison_axes": [
                        "endpoint", "intervention", "time_horizon", "statistic"
                    ],
                },
                {
                    "value": 90,
                    "comparator": ">=",
                    "unit": "%",
                    "label": "optimal >=90% at 12 months",
                    "role": "optimal",
                    "quote": "Optimal efficacy is at least 90% at 12 months.",
                    "doc_block_ids": ["document/b-0004"],
                    "required_comparison_axes": [
                        "endpoint", "intervention", "time_horizon", "statistic"
                    ],
                },
            ]
        }
        decisions = {
            "measurements": [
                {
                    "value": 82,
                    "unit": "%",
                    "url": "https://example.test/used",
                    "source_quote": "The reported efficacy was 82% in the target population.",
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
        self.assertEqual(ledgers[0].measurements[0].semantic_status, "comparable")

    def test_invalid_semantic_conversion_cannot_enter_the_numeric_cohort(self) -> None:
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
                    "required_comparison_axes": [
                        "endpoint", "intervention", "statistic"
                    ],
                }
            ]
        }

        class WrongSpanClient(StaticClient):
            def call(self, system_prompt, user_message, max_tokens, *, images=None):
                self.calls += 1
                if "complete numeric-statement ledger" in system_prompt.lower():
                    return json.dumps(normalize_conformity_fixture(
                        target_response, system_prompt, user_message
                    ))
                source = re.search(r"\[source:(sp-[a-f0-9]+)\]", user_message)
                assert source is not None
                return json.dumps(
                    {
                        "sources": [
                            {
                                "source_id": source.group(1),
                                "status": "measurements_found",
                                "reason": "Claims a measurement.",
                                "measurements": [{
                                    "quote": "The reported efficacy was 82 percent in the target population.",
                                    "expression": {"kind": "point_estimate", "value": 82, "unit": "%"},
                                    "semantic_status": "comparable",
                                    "semantic_reason": "Claims a match but omits the typed profile.",
                                }],
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
        self.assertEqual(ledgers[0].excluded_measurements, [])
        self.assertEqual(ledgers[0].source_dispositions[0].status, "uncertain")

    def test_missing_candidate_relevance_fails_closed_after_retry(self) -> None:
        target = QuantitativeTarget(
            attribute_ref="efficacy",
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        attribute = replace(self.attribute, quantitative_targets=[target])

        class MissingRelevanceClient:
            def __init__(self) -> None:
                self.calls = 0

            def call(self, system_prompt, user_message, max_tokens, *, images=None):
                self.calls += 1
                source = re.search(r"\[source:(sp-[a-f0-9]+)\]", user_message)
                assert source is not None
                return json.dumps(
                    {
                        "sources": [
                            {
                                "source_id": source.group(1),
                                "status": "measurements_found",
                                "reason": "Incomplete fixture decision.",
                                "measurements": [],
                            }
                        ]
                    }
                )

        client = MissingRelevanceClient()
        ledgers = _score_conformity_ledgers(
            attribute,
            [self.first],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(ledgers[0].benchmark_count, 0)
        self.assertEqual(ledgers[0].excluded_measurements, [])
        self.assertEqual(ledgers[0].source_dispositions[0].status, "uncertain")

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
