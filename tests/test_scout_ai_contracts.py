from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from services.scout.ai import request_structured
from services.scout.ai_contracts import (
    announcement_record,
    context_validation,
    drift_relation,
    document_quantitative_ledger_batch,
    evidence_review,
    evidence_assessment,
    insight_batch,
    insight_reconciliation,
    precedent_assessment,
    projection_reconciliation,
    quantitative_claim_reconciliation,
    query_batch,
    run_scope_value,
    source_measurement_batch,
    target_binding_batch,
    target_review_batch,
    unit_batch,
    unit_reconciliation,
)
from services.scout.ai_wire import (
    EvidenceUnitPartitionWire,
    NumericExpressionWire,
    inline_json_schema,
)
from shared.openai_client import OpenAIClient


def branch(schema: dict, key: str, value: str) -> dict:
    """The properties of the variant whose ``key`` takes ``value``."""
    for option in schema["anyOf"]:
        if value in option["properties"][key]["enum"]:
            return option["properties"]
    raise AssertionError(f"no branch with {key}={value}")


class _StructuredFixtureClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.schema_name = ""

    def call_structured(self, *_args, schema_name, **_kwargs):
        self.schema_name = schema_name
        return self.payload


class _ChatCompletions:
    def __init__(self, content: str):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content=self.content, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=None,
        )


class ScoutAIContractTests(unittest.TestCase):
    def test_numeric_provider_schema_is_generated_from_runtime_wire_model(self) -> None:
        contract = source_measurement_batch({"measure"}, ["source-1"])
        source = branch(contract.schema["properties"]["sources"]["items"], "status", "measurements_found")
        expression_schema = source["measurements"]["items"]["properties"]["expression"]

        self.assertEqual(expression_schema, inline_json_schema(NumericExpressionWire))
        partition_schema = source["evidence_unit_partition"]
        self.assertEqual(
            partition_schema,
            inline_json_schema(EvidenceUnitPartitionWire),
        )
        with self.assertRaises(ValidationError):
            NumericExpressionWire.model_validate({
                "kind": "point_estimate",
                "unit": "%",
                "value": 50,
                "lower": None,
                "upper": None,
                "comparator": "",
                "unexpected": "drift",
            })

    def test_claim_schema_allows_only_complete_canonical_block_ids(self) -> None:
        allowed = ["DRAFT AIV iTPP v1 13July2016/b-0084"]
        contract = target_binding_batch(allowed)
        block_id_schema = (
            branch(contract.schema["properties"]["bindings"]["items"], "status", "present")
            ["spans"]["items"]["properties"]["block_id"]
        )

        self.assertEqual(block_id_schema["enum"], allowed)
        self.assertNotIn("b-0084", block_id_schema["enum"])

    def test_context_schema_allows_only_visible_canonical_block_ids(self) -> None:
        allowed = ["DRAFT AIV iTPP v1 13July2016/b-0001"]
        contract = context_validation(allowed)
        block_id_schema = branch(
            contract.schema["properties"]["validation"], "status", "match",
        )["block_ids"]["items"]

        self.assertEqual(block_id_schema["enum"], allowed)
        self.assertNotIn("b-0001", block_id_schema["enum"])

    def test_target_review_schema_can_only_select_existing_proposals(self) -> None:
        allowed = ["qt-one", "qt-two"]
        contract = target_review_batch(allowed)
        item = contract.schema["properties"]["reviews"]["items"]

        self.assertEqual(item["properties"]["target_id"]["enum"], allowed)
        self.assertEqual(
            item["properties"]["decision"]["enum"],
            ["confirm", "exclude", "flag"],
        )

    def test_claim_reconciliation_can_only_partition_existing_targets(self) -> None:
        allowed = ["qt-one", "qt-two"]
        contract = quantitative_claim_reconciliation(allowed)
        item = contract.schema["properties"]["groups"]["items"]["properties"]

        self.assertEqual(item["representative_target_id"]["enum"], allowed)
        self.assertEqual(item["member_target_ids"]["items"]["enum"], allowed)

    def test_evidence_review_schema_can_only_select_existing_candidates(self) -> None:
        contract = evidence_review(["candidate-one"])
        decisions = contract.schema["properties"]["decisions"]

        self.assertEqual((decisions["minItems"], decisions["maxItems"]), (1, 1))
        decision = decisions["items"]["properties"]
        self.assertEqual(decision["candidate_id"]["enum"], ["candidate-one"])
        self.assertEqual(decision["decision"]["enum"], ["admit", "reject", "flag"])

    def test_dynamic_unit_schema_allows_only_chunk_block_ids(self) -> None:
        allowed = ["IPDP Development Plan/b-0042"]
        contract = unit_batch(allowed)
        block_id_schema = (
            contract.schema["properties"]["units"]["items"]["properties"]
            ["spans"]["items"]["properties"]["block_id"]
        )

        self.assertEqual(block_id_schema["enum"], allowed)
        self.assertNotIn("b-0042", block_id_schema["enum"])

    def test_numeric_ledger_schema_allows_only_canonical_context_refs(self) -> None:
        contract = document_quantitative_ledger_batch(
            ["binding-0001", "binding-0002"],
            ["unit-0001"],
            ["field.one"],
        )
        review = branch(contract.schema["properties"]["reviews"]["items"], "classification", "target")
        source_ref_schema = (
            review["targets"]["items"]["properties"]["semantic_profile"]
            ["properties"]["population"]["anyOf"][0]["properties"]["source_refs"]["items"]
        )

        self.assertEqual(
            source_ref_schema["enum"],
            ["statement", "binding-0001", "binding-0002"],
        )
        self.assertNotIn("binding-9999", source_ref_schema["enum"])

        self.assertEqual(review["targets"]["minItems"], 1)
        self.assertEqual(
            branch(contract.schema["properties"]["reviews"]["items"], "classification", "uncertain")
            ["targets"]["maxItems"],
            0,
        )
        self.assertEqual(review["unit_id"]["enum"], ["unit-0001"])
        self.assertEqual(
            review["attribute_refs"]["items"]["enum"],
            ["field.one"],
        )
        self.assertEqual(
            review["targets"]["items"]["properties"]["field_links"]
            ["items"]["properties"]["attribute_ref"]["enum"],
            ["field.one"],
        )
        target_properties = review["targets"]["items"]["properties"]
        self.assertIn("quote", target_properties)
        self.assertIn("comparison_contract", target_properties)
        self.assertNotIn("comparison_dimensions", target_properties)
        comparison_contract = target_properties["comparison_contract"]
        self.assertEqual(
            set(comparison_contract["properties"]),
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
        for rule in comparison_contract["properties"].values():
            self.assertEqual(
                [option["properties"]["mode"]["enum"][0] for option in rule["anyOf"]],
                ["compatible", "exact", "unconstrained", "unknown"],
            )
            for option in rule["anyOf"]:
                self.assertEqual(set(option["required"]), {"mode", "scope", "reason"})
        self.assertNotIn("source_syntax", target_properties)

        measurement_properties = branch(
            source_measurement_batch({"measure"}, ["source-1"])
            .schema["properties"]["sources"]["items"],
            "status", "measurements_found",
        )["measurements"]["items"]["properties"]
        self.assertNotIn("source_syntax", measurement_properties)

    def test_request_local_lineage_is_closed_in_every_stage(self) -> None:
        query = query_batch(["doc/b-0001"], ["target-1"], 3)
        queries = query.schema["properties"]["queries"]
        query_item = queries["items"]["properties"]
        self.assertEqual(query_item["doc_block_ids"]["items"]["enum"], ["doc/b-0001"])
        self.assertEqual(query_item["target_ids"]["items"]["enum"], ["target-1"])
        # The track's budget is the array's length, so no reply is trimmed afterwards.
        self.assertEqual((queries["minItems"], queries["maxItems"]), (3, 3))

        insight = insight_batch(["pubmed:123"])
        keys = (
            insight.schema["properties"]["insights"]["items"]["properties"]
            ["supporting_record_keys"]
        )
        self.assertEqual(keys["items"]["enum"], ["pubmed:123"])
        self.assertEqual(keys["minItems"], 1)

        drift = drift_relation(["doc/b-0001"])
        bearing = branch(drift.schema["properties"]["match"], "relation", "confirms")
        self.assertEqual(bearing["doc_block_ids"]["items"]["enum"], ["doc/b-0001"])
        self.assertEqual(bearing["doc_block_ids"]["minItems"], 1)
        self.assertNotIn(
            "minItems",
            branch(drift.schema["properties"]["match"], "relation", "unrelated")["doc_block_ids"],
        )

        source = source_measurement_batch({"endpoint"}, ["source-1"])
        source_id = branch(
            source.schema["properties"]["sources"]["items"], "status", "uncertain",
        )["source_id"]
        self.assertEqual(source_id["enum"], ["source-1"])

    def test_conditional_requirements_are_stated_in_the_schema(self) -> None:
        """A validator never refuses what its schema permits (AGENTS)."""
        scope = run_scope_value(["doc/b-0001"]).schema["properties"]["reading"]
        self.assertEqual(branch(scope, "found", "yes")["block_ids"]["minItems"], 1)
        self.assertEqual(branch(scope, "found", "yes")["value"]["pattern"], "\\S")
        self.assertEqual(branch(scope, "found", "no")["value"]["enum"], [""])
        self.assertNotIn("reason", branch(scope, "found", "yes"))

        announcement = announcement_record().schema["properties"]["reading"]
        self.assertEqual(branch(announcement, "names_program", "yes")["program_name"]["pattern"], "\\S")
        self.assertEqual(branch(announcement, "names_program", "no")["program_name"]["enum"], [""])

        evidence = evidence_assessment(3).schema["properties"]["assessment"]
        self.assertEqual(branch(evidence, "strength", "partial")["supporting_insight_indices"]["minItems"], 1)
        self.assertNotIn("minItems", branch(evidence, "strength", "unknown")["supporting_insight_indices"])

        precedent = precedent_assessment(3).schema["properties"]["assessment"]
        self.assertEqual(len(precedent["anyOf"]), 4)

        for contract, key in (
            (quantitative_claim_reconciliation(["a", "b"]), "member_target_ids"),
            (insight_reconciliation(["a", "b"]), "member_insight_ids"),
            (projection_reconciliation(["a", "b"]), "member_name_ids"),
        ):
            group = contract.schema["properties"]["groups"]["items"]["properties"]
            self.assertEqual(group[key]["minItems"], 1)
            self.assertNotIn("reason", group)

    def test_all_schema_objects_are_closed_and_fully_required(self) -> None:
        contracts = [
            context_validation(["document/b-0001"]),
            drift_relation(["document/b-0001"]),
            evidence_assessment(1),
            evidence_review(["candidate-1"]),
            insight_batch(["pubmed:1"]),
            precedent_assessment(1),
            query_batch(["document/b-0001"], ["target-1"], 2),
            run_scope_value(["document/b-0001"]),
            announcement_record(),
            projection_reconciliation(["name-0", "name-1"]),
            document_quantitative_ledger_batch(
                ["binding-0001"], ["unit-1"], ["field.one"]
            ),
            target_binding_batch(
                ["document/b-0001", "document/b-0002"], ["field.one"]
            ),
            unit_batch(["document/b-0001"]),
            unit_reconciliation(["unit-0", "unit-1"]),
            source_measurement_batch(
                {"measure", "endpoint"}, ["source-1"]
            ),
        ]

        def assert_closed(schema: object) -> None:
            if not isinstance(schema, dict):
                return
            if schema.get("type") == "object":
                self.assertFalse(schema.get("additionalProperties"))
                self.assertEqual(
                    set(schema.get("properties", {})),
                    set(schema.get("required", [])),
                )
            for value in schema.values():
                if isinstance(value, dict):
                    assert_closed(value)
                elif isinstance(value, list):
                    for item in value:
                        assert_closed(item)

        for contract in contracts:
            self.assertEqual(contract.schema.get("type"), "object")
            assert_closed(contract.schema)

    def test_structured_gateway_unwraps_stage_payload(self) -> None:
        contract = drift_relation(["document/b-0001"])
        client = _StructuredFixtureClient({"match": {"relation": "unrelated"}})
        result = request_structured(
            client,
            contract,
            "system",
            "user",
            max_tokens=100,
        )
        self.assertEqual(result, {"relation": "unrelated"})
        self.assertEqual(client.schema_name, contract.name)

    def test_openai_wrapper_sends_strict_json_schema(self) -> None:
        completions = _ChatCompletions(
            json.dumps(
                {"validation": {
                    "status": "match",
                    "document_indication": "malaria",
                    "reason": "The document names malaria.",
                    "block_ids": ["doc/b-0001"],
                }}
            )
        )
        client = OpenAIClient.__new__(OpenAIClient)
        client.models = {"fast": "test-model", "reasoning": "test-model"}
        client.client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        contract = context_validation(["doc/b-0001"])
        result = client.call_structured(
            "system",
            "user",
            500,
            schema_name=contract.name,
            schema=contract.schema,
        )

        self.assertEqual(result["validation"]["status"], "match")
        response_format = completions.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()
