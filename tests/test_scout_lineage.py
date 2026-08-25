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
    limit_document_context,
    render_canonical_binding,
    select_binding_context,
    validated_block_ids,
)
from services.scout.projections import (
    build_development_landscape,
    build_safety_observations,
)
from services.scout.models import (
    RetrievalScopeLedger,
    EVIDENCE_DOMAINS,
    Attribute,
    ComparisonRule,
    DocumentSpan,
    EvidenceUnitIdentity,
    Insight,
    QueryIntent,
    QuantitativeFieldLink,
    QuantitativeTarget as _QuantitativeTarget,
    Measurement,
    NumericExpression,
    QUANTITATIVE_SEMANTIC_FIELDS,
    SemanticSlot,
    load_attributes,
    load_config,
)
from services.scout.stages.conformity import (
    _SourcePassage,
    build_document_ledger_system_prompt,
    build_measurement_system_prompt,
    _meets_target,
    _partition_cohort,
    _source_passage_batches,
    _validated_numeric_expression,
    _validated_source_decisions,
    _validated_targets_with_issues,
    _validated_measurement_semantic_assessment,
    score_conformity_all,
)
from services.scout.stages.context_validator import (
    mismatch_message,
    validate_document_context,
)
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.evidence_assessor import assess_evidence
from services.scout.stages.insight_extractor import build_system_prompt as insight_system_prompt
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
    SafetyObservationRecord,
    merge_findings,
    plan_requests,
    source_keys,
)
from services.searcher.stages.searcher import _parse_response_to_findings


def structured_fixture(payload: object, schema: dict) -> dict:
    required = list(schema.get("required", []))
    if isinstance(payload, dict) and all(key in payload for key in required):
        return payload
    if len(required) == 1:
        return {required[0]: payload}
    if isinstance(payload, dict):
        return payload
    raise AssertionError("fixture does not match the structured response root")


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

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema: dict,
        images: list[dict[str, str]] | None = None,
        **_kwargs,
    ) -> dict:
        self.calls += 1
        self.image_calls.append(images or [])
        self.token_budgets.append(max_tokens)
        payload = normalize_conformity_fixture(
            self.response, system_prompt, user_message
        )
        return structured_fixture(payload, schema)


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

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema: dict,
        images: list[dict[str, str]] | None = None,
        **_kwargs,
    ) -> dict:
        self.calls += 1
        self.image_calls.append(images or [])
        self.token_budgets.append(max_tokens)
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        payload = normalize_conformity_fixture(
            self.responses.pop(0), system_prompt, user_message
        )
        return structured_fixture(payload, schema)


def complete_expression(expression: dict) -> dict:
    """Complete compact fixtures exactly as the strict provider schema does."""
    return {
        "kind": expression.get("kind", "unknown"),
        "unit": expression.get("unit", ""),
        "value": expression.get("value"),
        "lower": expression.get("lower"),
        "upper": expression.get("upper"),
        "comparator": expression.get("comparator", ""),
    }


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
                        "expression": complete_expression(target.get("expression") or {
                            "kind": "bound",
                            "value": target.get("value"),
                            "lower": None,
                            "upper": None,
                            "comparator": target.get("comparator", ""),
                            "unit": target.get("unit", ""),
                        }),
                        "semantic_profile": target.get(
                            "semantic_profile",
                            semantic_profile(str(target.get("label", "numeric measure"))),
                        ),
                        "comparison_contract": target.get("comparison_contract")
                        or comparison_contract(
                            target.get(
                                "semantic_profile",
                                semantic_profile(str(target.get("label", "numeric measure"))),
                            ),
                            target.get("comparison_dimensions"),
                        ),
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
                    "comparison_contract": comparison_contract(
                        response.get("semantic_profile")
                        or semantic_profile(str(response.get("target_label", "numeric measure")))
                    ),
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
    sources = re.findall(
        r"\[source:(sp-[a-f0-9]+)\][^\n]*\burl=([^ |]+)",
        user_message,
    )
    decisions = []
    for source_id, url in sources:
        source_measurements = [
            item for item in response.get("measurements", [])
            if isinstance(item, dict) and item.get("url") == url
        ]
        normalized = []
        for item in source_measurements:
            expression = {
                "kind": item.get("expression_kind", "point_estimate"),
                "unit": item.get("unit", ""),
                "value": item.get("value"),
                "lower": item.get("lower"),
                "upper": item.get("upper"),
                "comparator": item.get("comparator", ""),
            }
            normalized.append({
                "quote": item.get("source_quote", ""),
                "expression": expression,
                "evidence_unit": item.get("evidence_unit") or {
                    "status": "record_level",
                    "group": {
                        "state": "not_specified",
                        "value": "",
                        "other": "",
                    },
                    "cohort": {
                        "state": "not_specified",
                        "value": "",
                        "other": "",
                    },
                    "reason": "Fixture reports one aggregate record-level group.",
                },
                "semantic_assessment": item.get("semantic_assessment") or semantic_assessment(
                    source_profile=item.get("semantic_profile"),
                    comparability=item.get("comparability"),
                    ownership=item.get("source_ownership"),
                ),
            })
        resolved_units = {
            (
                item["evidence_unit"].get("group", {}).get("value", ""),
                item["evidence_unit"].get("cohort", {}).get("value", ""),
            )
            for item in normalized
            if item["evidence_unit"].get("status") == "resolved"
        }
        explicitly_disjoint = (
            len(normalized) > 1
            and len(resolved_units) == len(normalized)
        )
        decisions.append({
            "source_id": source_id,
            "status": "measurements_found" if normalized else "no_relevant_measurement",
            "reason": "Fixture source reviewed.",
            "evidence_unit_partition": {
                "status": "disjoint_units" if explicitly_disjoint else "single_unit",
                "reason": (
                    "Fixture supplies explicitly distinct resolved comparison units."
                    if explicitly_disjoint
                    else "Fixture treats the source passage as one comparison unit."
                ),
            },
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


def comparison_contract(
    profile: dict,
    dimensions: list[str] | None = None,
) -> dict:
    constrained = set(dimensions or [
        field_name
        for field_name, slot in profile.items()
        if slot["state"] in {"specified", "other"}
    ])
    constrained.add("measure")
    contract = {}
    for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
        slot = profile[field_name]
        scope = str(slot.get("value") or slot.get("other") or field_name)
        if field_name == "measure":
            mode = "exact"
        elif field_name in constrained:
            mode = "compatible"
        else:
            mode = "unconstrained"
        contract[field_name] = {
            "mode": mode,
            "scope": scope if mode != "unconstrained" else "",
            "reason": "Fixture comparison rule.",
        }
    return contract


def QuantitativeTarget(*args, **kwargs):
    """Keep compact historical model fixtures at the current constructor boundary."""
    if "comparison_contract" not in kwargs:
        profile = kwargs.get("semantic_profile") or {
            "measure": SemanticSlot(state="specified", value="numeric measure")
        }
        raw_profile = {}
        dimensions = []
        for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
            slot = profile.get(field_name, SemanticSlot())
            state = getattr(slot, "state", None) or slot.get("state", "not_specified")
            value = getattr(slot, "value", None)
            if value is None and isinstance(slot, dict):
                value = slot.get("value", "")
            other = getattr(slot, "other", None)
            if other is None and isinstance(slot, dict):
                other = slot.get("other", "")
            raw_profile[field_name] = {
                "state": state,
                "value": value or "",
                "other": other or "",
            }
            if state in {"specified", "other", "unknown"}:
                dimensions.append(field_name)
        contract = comparison_contract(raw_profile, dimensions)
        for field_name in dimensions:
            if raw_profile[field_name]["state"] == "unknown":
                contract[field_name] = {
                    "mode": "unknown",
                    "scope": "",
                    "reason": "The fixture leaves this comparison scope unresolved.",
                }
        kwargs["comparison_contract"] = contract
    return _QuantitativeTarget(*args, **kwargs)


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
    items = parsed.get("targets") if isinstance(parsed, dict) else None
    if isinstance(items, list):
        items = [
            {
                **item,
                "field_links": item.get("field_links") or [{
                    "attribute_ref": attribute.name,
                    "relation": "defines",
                    "reason": "Test fixture links the claim to its product field.",
                }],
            }
            for item in items
            if isinstance(item, dict)
        ]
    return _validated_targets_with_issues(
        items,
        doc_text=document,
        semantic_context=semantic_context or document,
    ).targets


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
    # Exercise the entry point the pipeline actually calls. One worker keeps the
    # stub client's response order deterministic without changing the code path.
    return score_conformity_all(
        [attribute],
        targets,
        {attribute.name: insights},
        client,
        indication=kwargs["indication"],
        intervention_class=kwargs["intervention_class"],
        max_workers=1,
    )


def score_conformity(*args, **kwargs):
    """Return the first score for a single-target test scenario."""
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
                "block_ids": ["document/b-0001"],
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
            ["document name/b-0001"],
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

    def test_web_citations_keep_only_their_nearest_claim(self) -> None:
        first = "([first](https://example.test/first))"
        second = "([second](https://example.test/second))"
        text = f"First claim. {first} Second claim. {second}"
        response = {
            "output": [{
                "type": "message",
                "content": [{
                    "text": text,
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://example.test/first",
                            "title": "First",
                            "start_index": text.index(first),
                            "end_index": text.index(first) + len(first),
                        },
                        {
                            "type": "url_citation",
                            "url": "https://example.test/second",
                            "title": "Second",
                            "start_index": text.index(second),
                            "end_index": text.index(second) + len(second),
                        },
                    ],
                }],
            }]
        }

        findings = _parse_response_to_findings(
            response,
            query="two claims",
            retrieved_at=datetime.now(timezone.utc),
        )

        by_url = {finding.url: finding for finding in findings}
        self.assertIn("First claim", by_url["https://example.test/first"].excerpt or "")
        self.assertNotIn("Second claim", by_url["https://example.test/first"].excerpt or "")
        self.assertIn("Second claim", by_url["https://example.test/second"].excerpt or "")
        self.assertNotIn("First claim", by_url["https://example.test/second"].excerpt or "")

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
                source_role="experimental",
            )
        ]
        first.safety_observations = [
            SafetyObservationRecord(
                product_name="Candidate A",
                record_type="reported_event",
                source_system="faers",
                label="Headache",
                report_count=12,
                qualification="Reports do not establish causation.",
                source_role="experimental",
            )
        ]
        duplicate = finding("https://example.test/trial", source="clinicaltrials")
        duplicate.development_records = [
            replace(first.development_records[0], source_role="comparator")
        ]
        duplicate.safety_observations = [
            replace(first.safety_observations[0], report_count=9)
        ]
        label_record = finding("https://example.test/label", source="fda_label")
        label_record.safety_observations = [
            SafetyObservationRecord(
                product_name="Candidate A",
                record_type="label_warning",
                source_system="fda_label",
                label="Headache",
                detail="Headache is described in official product information.",
                source_role="experimental",
            )
        ]

        landscape = build_development_landscape(
            {"clinical_efficacy": [first], "safety": [duplicate]}
        )
        observations = build_safety_observations(
            {
                "clinical_efficacy": [first],
                "safety": [duplicate, label_record],
            }
        )

        self.assertEqual(len(landscape), 1)
        self.assertEqual(landscape[0].name, "Candidate A")
        self.assertEqual(landscape[0].attribute_refs, ["clinical_efficacy", "safety"])
        self.assertEqual(len(landscape[0].supporting_findings), 1)
        self.assertRegex(landscape[0].projection_id, r"^dp-[0-9a-f]{16}$")
        self.assertEqual(landscape[0].source_role, "unknown")
        self.assertEqual(landscape[0].target_relationship, "unknown")
        self.assertEqual(len(observations), 2)
        faers = next(item for item in observations if item.source_system == "faers")
        label = next(
            item for item in observations if item.source_system == "fda_label"
        )
        self.assertEqual(faers.report_count, 12)
        self.assertEqual(
            faers.attribute_refs,
            ["clinical_efficacy", "safety"],
        )
        self.assertEqual(len(faers.supporting_findings), 1)
        self.assertRegex(faers.projection_id, r"^so-[0-9a-f]{16}$")
        self.assertNotEqual(faers.projection_id, label.projection_id)
        self.assertEqual(faers.label, label.label)
        self.assertEqual(faers.source_role, "experimental")
        self.assertEqual(faers.target_relationship, "unknown")

        rebuilt = build_development_landscape(
            {"clinical_efficacy": [first], "safety": [duplicate]}
        )
        self.assertEqual(rebuilt[0].projection_id, landscape[0].projection_id)
        rebuilt_observations = build_safety_observations(
            {
                "clinical_efficacy": [first],
                "safety": [duplicate, label_record],
            }
        )
        self.assertEqual(
            [item.projection_id for item in rebuilt_observations],
            [item.projection_id for item in observations],
        )


class RetrievalPlanningTests(unittest.TestCase):
    def test_every_fixed_attribute_has_an_authored_evidence_domain(self) -> None:
        for intervention_class in ("vaccine", "drug", "diagnostic", "device"):
            attributes = load_attributes(intervention_class)
            self.assertTrue(attributes, intervention_class)
            for attribute in attributes:
                self.assertIn(attribute.evidence_domain, EVIDENCE_DOMAINS)
                self.assertNotEqual(attribute.evidence_domain, "general")

    def test_drug_vocabulary_owns_core_pk_tolerability_and_resistance_rows(self) -> None:
        names = {attribute.name for attribute in load_attributes("drug")}

        self.assertTrue({
            "drug.pharmacokinetic_profile",
            "drug.tolerability",
            "drug.resistance_profile",
        }.issubset(names))

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

        # UniProt is gone: it was `reference`, so insight extraction filtered its
        # findings out, and it built no records, so no projection read them. A lane
        # feeding nothing is now unregistrable - see test_retrieval_coverage.
        self.assertTrue({"open_targets", "chembl"}.issubset(drug.sources))
        self.assertNotIn("open_targets", vaccine.sources)
        self.assertNotIn("chembl", vaccine.sources)
        self.assertTrue({"open_targets", "chembl"}.isdisjoint(device.sources))
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
            scope=RetrievalScopeLedger.of(
                condition=("malaria", "header"),
                intervention=("vaccine", "header"),
            ),
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
        # The authored query survives whole. Previously it was split into content
        # terms, which silently deleted "latest" and the institution name "WHO".
        self.assertEqual(
            literature.query,
            'malaria AND "latest WHO malaria vaccine doses"',
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
        # A track's meaning lives in the queries authored for that track, not in a
        # code-side synonym table appended to every counterfactual request.
        self.assertIn("dosing failure", counterfactual_literature.query)
        self.assertIn("adherence limitations", counterfactual_literature.query)
        self.assertEqual(
            counterfactual_literature.document_refs,
            ("doc/b-0002", "doc/b-0003"),
        )

        literature_only = plan_requests(retrieval_intents, sources=("pubmed",))
        self.assertTrue(literature_only)
        self.assertEqual({task.source for task in literature_only}, {"pubmed"})

    def test_literature_queries_retain_document_specific_drug_concepts(self) -> None:
        attribute = Attribute(
            "drug.pharmacokinetic_profile",
            "Pharmacokinetic and exposure requirements",
            document_target="Long-acting injectable for pulmonary tuberculosis.",
            document_spans=[DocumentSpan(
                quote="Long-acting injectable for pulmonary tuberculosis.",
                block_ids=["doc/b-0034"],
            )],
            target_resolved=True,
            evidence_domain="clinical",
        )
        queries = [QueryIntent(
            "tuberculosis long acting injectable pharmacokinetic target attainment",
            ["general"],
            ["doc/b-0034"],
        )]
        intents = build_retrieval_intents(
            {attribute.name: queries},
            [attribute],
            scope=RetrievalScopeLedger.of(
                condition=("tb", "header"),
                intervention=("drug", "header"),
            ),
        )

        requests = plan_requests(
            intents,
            sources=("pubmed", "semantic_scholar"),
        )

        self.assertTrue(all("tb" in request.query.casefold() for request in requests))
        self.assertTrue(all("injectable" in request.query.casefold() for request in requests))
        self.assertTrue(all("pharmacokinetic" in request.query.casefold() for request in requests))

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
                field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            quantitative_target_ids=[target.id for target in targets],
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
            adjacent_queries_per_variable=0,
        )
        queries = extract_queries_for_variable(
            attribute,
            targets,
            config,
            StaticClient([{"query": "general efficacy evidence", "doc_block_ids": []}]),
            indication="malaria",
            scope=RetrievalScopeLedger.of(condition=("malaria", "header")),
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
                scope=RetrievalScopeLedger.of(
                    condition=("malaria", "header"),
                    intervention=("vaccine", "header"),
                ),
            ),
            sources=("semantic_scholar",),
        )
        self.assertEqual(set(requests[0].target_refs), {target.id for target in targets})

    def test_query_projection_preserves_ai_mapped_semantic_dimensions(self) -> None:
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
            field_links=[QuantitativeFieldLink(attribute_ref="device.storage", relation="defines", reason="Test fixture.")],
            expression=NumericExpression(kind="bound", value=8, comparator=">", unit="°C"),
            role="optimal",
            quote="stable for extended periods at temperatures greater than +8°C",
            doc_block_ids=["document/b-0004"],
            semantic_profile=profile,
        )

        descriptor = _target_retrieval_descriptor(target)
        query_text = _target_retrieval_text(target)

        self.assertEqual(
            descriptor["dimensions"]["endpoint"],
            "stability at temperatures greater than +8°C",
        )
        self.assertEqual(
            descriptor["dimensions"]["time_horizon"], "extended storage period"
        )
        self.assertIn("+8°C", query_text)
        self.assertIn("storage temperature tolerance", query_text)

        dose_profile = semantic_profile("dose volume below 0.5 mL/dose")
        dose_target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="device.dose_volume", relation="defines", reason="Test fixture.")],
            expression=NumericExpression(
                kind="bound", value=0.5, comparator="<", unit="mL/dose"
            ),
            role="optimal",
            quote="Dose volume below 0.5 mL/dose.",
            doc_block_ids=["document/b-0005"],
            semantic_profile=dose_profile,
        )
        self.assertEqual(
            _target_retrieval_descriptor(dose_target)["dimensions"]["measure"],
            "dose volume below 0.5 mL/dose",
        )

    def test_compatible_product_class_does_not_become_exact_candidate_identity(self) -> None:
        profile = semantic_profile("protective efficacy")
        profile["intervention"] = {
            "state": "specified",
            "value": "AIV anti-infective malaria vaccine",
            "other": "",
        }
        contract = comparison_contract(profile, ["measure", "intervention"])
        contract["intervention"] = {
            "mode": "compatible",
            "scope": "anti-infective malaria vaccines",
            "reason": "Different named vaccine candidates are valid class comparators.",
        }
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(
                attribute_ref="vaccine.efficacy",
                relation="defines",
                reason="Test fixture.",
            )],
            expression=NumericExpression(
                kind="bound", value=80, comparator=">", unit="%"
            ),
            role="optimal",
            quote="Target efficacy is more than 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=profile,
            comparison_contract=contract,
        )

        descriptor = _target_retrieval_descriptor(target)
        self.assertEqual(
            descriptor["dimensions"]["intervention"],
            "anti-infective malaria vaccines",
        )
        self.assertNotIn(
            "AIV anti-infective malaria vaccine",
            _target_retrieval_text(target),
        )

        source_profile = semantic_profile("protective efficacy")
        source_profile["intervention"] = {
            "state": "specified",
            "value": "RTS,S/AS01 malaria vaccine",
            "other": "",
        }
        measurement = Measurement(
            expression=NumericExpression(
                kind="point_estimate", value=50.3, unit="%"
            ),
            semantic_assessment=semantic_assessment(
                source_profile=source_profile,
                comparability=same_comparability(),
            ),
            candidate_id="qm-compatible-product",
            source_record_id="doi:10.1/rts-s",
            evidence_mode="structured_fact",
        )

        included, excluded = _partition_cohort([measurement], target)
        self.assertEqual(included, [measurement])
        self.assertEqual(excluded, [])

    def test_generated_query_is_not_reinterpreted_by_string_heuristics(self) -> None:
        profile = semantic_profile("storage temperature tolerance")
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="device.storage", relation="defines", reason="Test fixture.")],
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
            quantitative_target_ids=[target.id],
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
            adjacent_queries_per_variable=0,
        )
        invalid = [{
            "query": "device stability above 8°C reported results",
            "doc_block_ids": ["document/b-0004"],
            "target_ids": [target.id],
        }]

        queries = extract_queries_for_variable(
            attribute,
            [target],
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
            scope=RetrievalScopeLedger.of(condition=("malaria", "header")),
            queries_per_variable=1,
            document_context="[block:document/b-0004]\nTemperature tolerance greater than 8°C.",
        )

        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].target_ids, [target.id])
        self.assertEqual(
            queries[0].text,
            "device stability above 8°C reported results",
        )

    def test_locale_decimal_query_is_preserved_as_ai_authored_intent(self) -> None:
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="device.dose_volume", relation="defines", reason="Test fixture.")],
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
            quantitative_target_ids=[target.id],
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
            adjacent_queries_per_variable=0,
        )
        invalid = [{
            "query": "dose volume below 0,5 mL reported results",
            "doc_block_ids": ["document/b-0005"],
            "target_ids": [target.id],
        }]

        queries = extract_queries_for_variable(
            attribute,
            [target],
            config,
            SequenceClient([invalid, invalid]),
            indication="example condition",
            scope=RetrievalScopeLedger.of(condition=("malaria", "header")),
            queries_per_variable=1,
            document_context="[block:document/b-0005]\nDose volume below 0.5 mL/dose.",
        )

        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].text, "dose volume below 0,5 mL reported results")

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
            scope=RetrievalScopeLedger.of(
                condition=("malaria", "header"),
                intervention=("vaccine", "header"),
            ),
        )

        requests = plan_requests(
            retrieval_intents,
            sources=("semantic_scholar",),
        )

        self.assertEqual(len(requests), 1)
        # Every variant stays in request lineage even though a plain-text engine
        # cannot separate five questions inside one query string.
        self.assertEqual(len(requests[0].intent_ids), 5)
        self.assertEqual(requests[0].input_queries, tuple(item.text for item in variants))
        self.assertEqual(
            requests[0].query,
            "malaria "
            "malaria vaccine durability concept0 "
            "malaria vaccine durability concept1",
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
                            "block_id": "document/b-0002",
                            "start_line": 1,
                            "end_line": 1,
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
            document_spans=[
                DocumentSpan(
                    quote="Dose volume: <0.5 mL/dose.",
                    block_ids=["document/b-0003"],
                )
            ],
            target_resolved=True,
        )

        raw = select_binding_context(blocks, attribute)
        canonical = render_canonical_binding(attribute)

        self.assertIn("three annual doses", raw)
        self.assertNotIn("three annual doses", canonical)
        self.assertIn("[block:document/b-0003]", canonical)
        self.assertIn(attribute.document_target, canonical)

    def test_reasoning_binding_renders_each_exact_span_only_at_its_source(self) -> None:
        attribute = Attribute(
            name="vaccine.efficacy",
            description="Efficacy target",
            document_spans=[
                DocumentSpan(
                    quote="Threshold efficacy is at least 50%.",
                    block_ids=["document/b-0003"],
                ),
                DocumentSpan(
                    quote="Optimal efficacy is at least 80%.",
                    block_ids=["document/b-0004"],
                ),
            ],
            target_resolved=True,
        )

        canonical = render_canonical_binding(attribute)

        self.assertEqual(canonical.count("Threshold efficacy"), 1)
        self.assertEqual(canonical.count("Optimal efficacy"), 1)
        self.assertIn(
            "[block:document/b-0003]\nThreshold efficacy is at least 50%.",
            canonical,
        )
        self.assertIn(
            "[block:document/b-0004]\nOptimal efficacy is at least 80%.",
            canonical,
        )

    def test_bounded_reasoning_context_does_not_split_normal_blocks(self) -> None:
        rendered = "\n\n".join(
            f"[block:document/b-{index:04d}]\n{'x' * 80}"
            for index in range(8)
        )

        bounded = limit_document_context(rendered, max_chars=420)

        self.assertIn("middle document blocks omitted", bounded)
        for rendered_block in bounded.split("\n\n"):
            if rendered_block.startswith("[block:"):
                self.assertRegex(
                    rendered_block,
                    r"^\[block:document/b-\d{4}\]\n(?:x{80})$",
                )

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
        self.assertEqual(client.calls, 0)

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

    def test_each_insight_is_classified_in_its_own_request(self) -> None:
        """A per-insight relation must not be judged alongside unrelated insights."""
        class _RecordingClient(StaticClient):
            def __init__(self) -> None:
                super().__init__([{
                    "index": 0,
                    "relation": "confirms",
                    "reason": "The endpoint supports the stated target.",
                    "doc_block_ids": ["document/b-0003"],
                }])
                self.request_sizes: list[int] = []

            def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
                self.request_sizes.append(
                    kwargs["schema"]["properties"]["matches"]["items"]
                    ["properties"]["index"]["maximum"] + 1
                )
                return super().call_structured(
                    system_prompt, user_message, max_tokens, **kwargs
                )

        client = _RecordingClient()

        result = classify_drift(
            [self.document],
            [self.first, self.second],
            client,
            indication="test",
            intervention_class="vaccine",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(client.request_sizes, [1, 1])

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
                        "url": "https://example.test/not-owned",
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
        self.assertEqual(result.measurements, [])
        pending = [
            item for item in result.excluded_measurements
            if item.admission_status == "needs_review"
        ]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].url, "https://example.test/used")
        self.assertEqual(pending[0].insight_id, self.first.id)
        self.assertEqual(pending[0].expression.kind, "point_estimate")
        self.assertEqual(result.benchmark_count, 0)
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
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(result.excluded_measurements[0].value, 82)
        self.assertEqual(result.excluded_measurements[0].admission_status, "needs_review")

    def test_numeric_expression_schema_accepts_semantic_normalization(self) -> None:
        expressions = [
            {
                "kind": "point_estimate", "unit": "%", "value": 50.3,
                "lower": None, "upper": None, "comparator": "",
            },
            {
                "kind": "count", "unit": "administrations", "value": 120,
                "lower": None, "upper": None, "comparator": "",
            },
            {
                "kind": "bound", "unit": "vials/dose", "value": 2,
                "lower": None, "upper": None, "comparator": "<=",
            },
        ]
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertIsNotNone(_validated_numeric_expression(expression))

        # Calculation semantics remain deterministic after AI normalization.
        self.assertTrue(_meets_target(0.49, 0.5, "<"))
        self.assertFalse(_meets_target(0.5, 0.5, "<"))
        self.assertTrue(_meets_target(2, 2, "="))
        self.assertFalse(_meets_target(3, 2, "="))

    def test_numeric_expression_schema_rejects_malformed_values(self) -> None:
        self.assertIsNone(_validated_numeric_expression({
            "kind": "bound", "unit": "", "value": 2,
            "lower": None, "upper": None, "comparator": "<=",
        }))

    def test_range_is_one_expression_not_two_point_candidates(self) -> None:
        expression = _validated_numeric_expression({
            "kind": "range", "unit": "%", "value": None,
            "lower": 36, "upper": 50, "comparator": "",
        })
        self.assertIsNotNone(expression)

    def test_irrelevant_numbers_resolve_at_passage_level_without_fragment_noise(self) -> None:
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        attribute = replace(self.attribute, quantitative_target_ids=[target.id])
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
            def call_structured(self, system_prompt, user_message, max_tokens, **_kwargs):
                source = re.search(r"\[source:(sp-[a-f0-9]+)\]", user_message)
                assert source is not None
                return {"sources": [{
                    "source_id": source.group(1),
                    "status": "no_relevant_measurement",
                    "reason": "Only enrollment and follow-up duration are reported.",
                    "evidence_unit_partition": {
                        "status": "single_unit",
                        "reason": "No relevant measurement was identified.",
                    },
                    "measurements": [],
                }]}

        result = score_conformity_all(
            [attribute],
            [target],
            {attribute.name: [insight]},
            NoMeasurementClient(),
            indication="malaria",
            intervention_class="vaccine",
            max_workers=1,
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
            evidence_mode="structured_fact",
        )
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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

    def test_distinct_arms_from_one_source_are_independent_evidence_units(self) -> None:
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        measurements = [
            Measurement(
                expression=NumericExpression(kind="point_estimate", value=value, unit="%"),
                semantic_assessment=semantic_assessment(
                    source_profile=semantic_profile("protective efficacy")
                ),
                candidate_id=f"qm-arm-{index}",
                source_record_id="doi:10.1/multi-arm",
                evidence_unit_id=f"doi:10.1/multi-arm/unit:arm-{index}",
                evidence_unit=EvidenceUnitIdentity(
                    status="resolved",
                    group=SemanticSlot(state="specified", value=f"arm {index}"),
                    reason="The source distinguishes this arm from another arm.",
                ),
                evidence_mode="structured_fact",
            )
            for index, value in enumerate((72, 88), start=1)
        ]

        included, excluded = _partition_cohort(measurements, target)

        self.assertEqual(included, measurements)
        self.assertEqual(excluded, [])

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
            evidence_mode="structured_fact",
        )
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="incidence", relation="defines", reason="Test fixture.")],
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

    def test_unit_incompatible_prose_candidate_is_never_reviewable(self) -> None:
        """Unit incompatibility is structural: no review decision can admit it."""
        measurement = Measurement(
            expression=NumericExpression(
                kind="point_estimate", value=820, unit="per 100,000"
            ),
            semantic_assessment=semantic_assessment(
                source_profile=semantic_profile("protective efficacy")
            ),
            candidate_id="qm-unit-mismatch",
            source_record_id="doi:10.1/unit",
        )
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(
                attribute_ref="efficacy", relation="defines", reason="Test fixture."
            )],
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )

        included, excluded = _partition_cohort([measurement], target)

        self.assertEqual(included, [])
        self.assertEqual(excluded, [measurement])
        self.assertEqual(measurement.admission_status, "not_eligible")

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
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            evidence_mode="structured_fact",
        )
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
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

    def test_literal_validator_does_not_reclassify_surrounding_prose(self) -> None:
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

        # The fixture deliberately supplies a semantically wrong AI mapping.
        # Runtime validation checks its typed/literal contract; it does not
        # maintain a second keyword classifier for "to" that can drift from
        # the model contract.
        self.assertEqual(extraction.status, "present")
        self.assertEqual(len(extraction.targets), 1)

    def test_prose_number_normalization_uses_typed_model_contract(self) -> None:
        document = "[block:document/b-0003]\nNo more than two vials per dose."
        attribute = replace(
            self.attribute,
            document_target="No more than two vials per dose.",
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
                        "comparator": "<=",
                        "unit": "vials/dose",
                    },
                    "role": "other",
                    "quote": "No more than two vials per dose.",
                    "doc_block_ids": ["document/b-0003"],
                    "semantic_profile": semantic_profile("vials per dose"),
                }],
            }),
            indication="example condition",
            intervention_class="vaccine",
        )

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].expression.value, 2)
        self.assertEqual(targets[0].expression.comparator, "<=")

    def test_target_contract_separates_unit_from_conditions(self) -> None:
        attribute = replace(
            self.attribute,
            name="diagnostic.stability",
            document_target="Stable for at least 6 hours at 37°C.",
            block_ids=["document/b-0003"],
        )
        prompt = build_document_ledger_system_prompt(
            [attribute],
            indication="example condition",
            intervention_class="diagnostic",
            framing="",
        )

        self.assertIn("canonical fields", prompt.lower())
        self.assertIn("Copy the short exact excerpt", prompt)
        self.assertIn("without reinterpreting its numeric meaning", prompt)
        self.assertIn("Conditions includes only settings", prompt)
        self.assertIn("change numeric interpretation", prompt)
        self.assertIn("mode=unknown preserves genuine ambiguity", prompt)
        self.assertIn("comparison_contract separately", prompt)

    def test_identical_scalar_under_multiple_roles_preserves_both_roles(self) -> None:
        document = (
            "[block:document/b-0003]\nOptimal: at most 2 products.\n\n"
            "[block:document/b-0004]\nThreshold: at most 2 products."
        )
        attribute = replace(
            self.attribute,
            name="vaccine.presentation",
            document_target=(
                "Optimal: at most 2 products. "
                "Threshold: at most 2 products."
            ),
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
            field_links=[QuantitativeFieldLink(attribute_ref=self.attribute.name, relation="defines", reason="Test fixture.")],
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80% at six months.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        prompt = build_measurement_system_prompt(
            (self.attribute,),
            target=target,
            indication="malaria",
            intervention_class="vaccine",
        )
        self.assertIn('target-constrained dimensions: ["measure"]', prompt)
        self.assertIn('"value": "protective efficacy"', prompt)
        self.assertNotIn("sp-123", prompt)
        self.assertIn("Target semantic profile", prompt)
        self.assertNotIn(target.quote, prompt)
        self.assertNotIn("80", prompt)
        self.assertIn("self-contained exact quote", prompt)
        self.assertIn("storage temperature", prompt)
        self.assertIn("return uncertain rather than a measurement", prompt)
        self.assertIn("A parent population and any of its subgroups overlap", prompt)

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

    def test_distinct_source_records_never_share_one_mapping_call(self) -> None:
        """Unrelated sources must not sit in one another's mapping context."""
        def passage_for(url: str, excerpt: str, passage_id: str) -> _SourcePassage:
            record_finding = finding(url, source="pubmed", excerpt=excerpt)
            return _SourcePassage(
                id=passage_id,
                insight=Insight(
                    statement=excerpt,
                    supporting_findings=[record_finding],
                    attribute_ref="efficacy",
                ),
                finding=record_finding,
                text=excerpt,
            )

        first = passage_for(
            "https://doi.org/10.1000/first", "Protective efficacy was 82%.", "sp-first"
        )
        second = passage_for(
            "https://doi.org/10.1000/second", "Protective efficacy was 74%.", "sp-second"
        )
        third = passage_for(
            "https://doi.org/10.1000/third", "Protective efficacy was 65%.", "sp-third"
        )

        batches = _source_passage_batches([first, second, third])

        self.assertEqual(batches, [[first], [second], [third]])

    def test_source_partition_collapses_overlap_and_preserves_disjoint_arms(self) -> None:
        target = QuantitativeTarget(
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
                "measure": SemanticSlot(
                    state="specified", value="protective efficacy"
                )
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
        overall_quote = "Protective efficacy was 55% in the overall population."
        subgroup_quote = "Protective efficacy was 62% in the booster subgroup."
        overall_finding = finding(
            "https://doi.org/10.1000/example",
            source="pubmed",
            excerpt=overall_quote,
        )
        subgroup_finding = finding(
            "https://doi.org/10.1000/example",
            source="pubmed",
            excerpt=subgroup_quote,
        )
        overall_insight = Insight(
            statement="The study reports overall efficacy.",
            supporting_findings=[overall_finding],
            attribute_ref="efficacy",
        )
        subgroup_insight = Insight(
            statement="The study reports subgroup efficacy.",
            supporting_findings=[subgroup_finding],
            attribute_ref="efficacy",
        )
        passages = [
            _SourcePassage(
                id="sp-overall",
                insight=overall_insight,
                finding=overall_finding,
                text=overall_quote,
            ),
            _SourcePassage(
                id="sp-subgroup",
                insight=subgroup_insight,
                finding=subgroup_finding,
                text=subgroup_quote,
            ),
        ]
        unrelated_finding = finding(
            "https://doi.org/10.1000/other",
            source="pubmed",
            excerpt="Protective efficacy was 40%.",
        )
        unrelated_passage = _SourcePassage(
            id="sp-unrelated",
            insight=Insight(
                statement="Another study reports efficacy.",
                supporting_findings=[unrelated_finding],
                attribute_ref="efficacy",
            ),
            finding=unrelated_finding,
            text=unrelated_finding.excerpt,
        )
        # One record's passages travel together; an unrelated record does not
        # join their mapping context.
        self.assertEqual(
            _source_passage_batches([*passages, unrelated_passage]),
            [passages, [unrelated_passage]],
        )

        def raw_measurement(quote: str, value: float, group: str) -> dict:
            return {
                "quote": quote,
                "expression": complete_expression({
                    "kind": "point_estimate",
                    "value": value,
                    "unit": "%",
                }),
                "evidence_unit": {
                    "status": "resolved",
                    "group": {
                        "state": "specified",
                        "value": group,
                        "other": "",
                    },
                    "cohort": {
                        "state": "not_specified",
                        "value": "",
                        "other": "",
                    },
                    "reason": f"The source identifies the {group}.",
                },
                "semantic_assessment": semantic_assessment(
                    source_profile=semantic_profile("protective efficacy")
                ),
            }

        measurements = [
            raw_measurement(overall_quote, 55, "overall population"),
            raw_measurement(subgroup_quote, 62, "booster subgroup"),
        ]
        for partition_status, expected_unit_count, expected_status in (
            ("overlapping_or_uncertain", 1, "uncertain"),
            ("disjoint_units", 2, "resolved"),
        ):
            with self.subTest(partition_status=partition_status):
                decisions = [{
                        "source_id": passage.id,
                        "status": "measurements_found",
                        "reason": "The source passage contains a relevant measurement.",
                        "evidence_unit_partition": {
                            "status": partition_status,
                            "reason": "Source-wide evidence-unit decision.",
                        },
                        "measurements": [measurement],
                    }
                    for passage, measurement in zip(passages, measurements)
                ]
                mapped, dispositions, issues = _validated_source_decisions(
                    decisions,
                    passages={passage.id: passage for passage in passages},
                    target=target,
                )

                self.assertEqual(issues, {})
                self.assertEqual(len(dispositions), 2)
                self.assertEqual(len(mapped), 2)
                self.assertEqual(
                    len({item.evidence_unit_id for item in mapped}),
                    expected_unit_count,
                )
                self.assertTrue(all(
                    item.evidence_unit.status == expected_status for item in mapped
                ))

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
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(result.measurements, [])
        self.assertEqual(len(result.excluded_measurements), 2)
        self.assertTrue(all(
            item.admission_status == "needs_review"
            for item in result.excluded_measurements
        ))
        wire = ConformityOut(**asdict(result))
        self.assertEqual(wire.benchmark_count, 0)
        self.assertEqual(len(wire.excluded_measurements), 2)

    def test_repeated_source_candidate_is_deduplicated_before_review(self) -> None:
        repeated = {
            "value": 82,
            "unit": "%",
            "insight_index": 0,
            "url": "https://example.test/used",
            "source_quote": "The reported efficacy was 82% in the target population.",
            "comparability": same_comparability(),
        }
        result = score_conformity(
            self.attribute,
            self.document,
            [self.first],
            StaticClient({
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": [repeated, dict(repeated)],
            }),
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result.excluded_measurements), 1)
        self.assertEqual(
            result.excluded_measurements[0].admission_status,
            "needs_review",
        )

    def test_distinct_source_candidates_keep_distinct_target_relative_ids(self) -> None:
        url = "https://example.test/multi-result"
        insight = Insight(
            statement="The source reports two arm-level efficacy results.",
            supporting_findings=[finding(
                url,
                source="pubmed",
                excerpt=(
                    "Arm A reported efficacy of 72%. "
                    "Arm B reported efficacy of 88%."
                ),
            )],
            attribute_ref="efficacy",
        )
        measurements = [
            {
                "value": value,
                "unit": "%",
                "url": url,
                "source_quote": quote,
                "comparability": same_comparability(),
                "evidence_unit": {
                    "status": "resolved",
                    "group": {
                        "state": "specified",
                        "value": arm,
                        "other": "",
                    },
                    "cohort": {
                        "state": "not_specified",
                        "value": "",
                        "other": "",
                    },
                    "reason": "The source explicitly distinguishes two arms.",
                },
            }
            for arm, value, quote in (
                ("Arm A", 72, "Arm A reported efficacy of 72%."),
                ("Arm B", 88, "Arm B reported efficacy of 88%."),
            )
        ]
        result = score_conformity(
            self.attribute,
            self.document,
            [insight],
            StaticClient({
                "is_quantitative": True,
                "target_value": 80,
                "comparator": ">=",
                "unit": "%",
                "target_label": "threshold >=80%",
                "target_quote": "Target efficacy is at least 80%.",
                "doc_block_ids": ["document/b-0003"],
                "measurements": measurements,
            }),
            indication="test",
            intervention_class="vaccine",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result.excluded_measurements), 2)
        self.assertEqual(
            len({item.candidate_id for item in result.excluded_measurements}),
            2,
        )

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
        self.assertEqual(result.benchmark_count, 0)
        self.assertEqual(len(result.excluded_measurements), 2)
        self.assertEqual(
            {item.admission_status for item in result.excluded_measurements},
            {"needs_review", "not_eligible"},
        )

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
        # The reason names both units rather than saying "incompatible", because a reader
        # deciding whether the rejection was right needs to see what was compared with what.
        excluded = result.excluded_measurements[0]
        self.assertIn("fraction", excluded.exclusion_reasons[0])
        self.assertIn("%", excluded.exclusion_reasons[0])
        # And it is recorded as a deterministic check, not as a model's reading.
        self.assertIn(excluded.exclusion_reasons[0], excluded.structural_reasons)

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
            item.admission_status == "needs_review"
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
        self.assertEqual([ledger.target_meeting_count for ledger in ledgers], [0, 0])
        self.assertNotEqual(ledgers[0].target_id, ledgers[1].target_id)
        self.assertNotEqual(
            ledgers[0].excluded_measurements[0].candidate_id,
            ledgers[1].excluded_measurements[0].candidate_id,
        )
        self.assertEqual(
            ledgers[0].excluded_measurements[0].admission_status,
            "needs_review",
        )

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
                return json.dumps(
                    normalize_conformity_fixture(
                        target_response, system_prompt, user_message
                    )
                )

            def call_structured(
                self, system_prompt, user_message, max_tokens, *, schema, **_kwargs
            ):
                self.calls += 1
                if "complete numeric-statement ledger" in system_prompt.lower():
                    return structured_fixture(
                        normalize_conformity_fixture(
                            target_response, system_prompt, user_message
                        ),
                        schema,
                    )
                source = re.search(r"\[source:(sp-[a-f0-9]+)\]", user_message)
                assert source is not None
                return {
                    "sources": [
                        {
                            "source_id": source.group(1),
                            "status": "measurements_found",
                            "reason": "Claims a measurement.",
                            "evidence_unit_partition": {
                                "status": "single_unit",
                                "reason": "The source is one aggregate comparison unit.",
                            },
                            "measurements": [{
                                "quote": "The reported efficacy was 82 percent in the target population.",
                                "expression": {"kind": "point_estimate", "value": 82, "unit": "%"},
                                "semantic_status": "comparable",
                                "semantic_reason": "Claims a match but omits the typed profile.",
                            }],
                        }
                    ]
                }

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
        # A rejected mapping is this pipeline's failure, not the model judging
        # the evidence ambiguous.
        self.assertEqual(ledgers[0].source_dispositions[0].status, "not_assessed")
        self.assertEqual(
            ledgers[0].source_dispositions[0].failure_code, "source_quote_not_found"
        )

    def test_missing_candidate_relevance_fails_closed_after_retry(self) -> None:
        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
            expression=NumericExpression(
                kind="bound", value=80, comparator=">=", unit="%"
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=["document/b-0003"],
            semantic_profile=semantic_profile("protective efficacy"),
        )
        attribute = replace(self.attribute, quantitative_target_ids=[target.id])

        class MissingRelevanceClient:
            def __init__(self) -> None:
                self.calls = 0

            def call_structured(self, system_prompt, user_message, max_tokens, **_kwargs):
                self.calls += 1
                source = re.search(r"\[source:(sp-[a-f0-9]+)\]", user_message)
                assert source is not None
                return {
                    "sources": [
                        {
                            "source_id": source.group(1),
                            "status": "measurements_found",
                            "reason": "Incomplete fixture decision.",
                            "evidence_unit_partition": {
                                "status": "single_unit",
                                "reason": "The source is one aggregate comparison unit.",
                            },
                            "measurements": [],
                        }
                    ]
                }

        client = MissingRelevanceClient()
        ledgers = score_conformity_all(
            [attribute],
            [target],
            {attribute.name: [self.first]},
            client,
            indication="test",
            intervention_class="vaccine",
            max_workers=1,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(ledgers[0].benchmark_count, 0)
        self.assertEqual(ledgers[0].excluded_measurements, [])
        self.assertEqual(ledgers[0].source_dispositions[0].status, "not_assessed")
        self.assertTrue(ledgers[0].source_dispositions[0].failure_code)

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
