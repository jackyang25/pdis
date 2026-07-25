from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from services.scout.ai import request_structured
from services.scout.ai_contracts import (
    context_validation,
    drift_batch,
    document_quantitative_ledger_batch,
    evidence_assessment,
    insight_batch,
    precedent_assessment,
    query_batch,
    source_measurement_batch,
    target_binding_batch,
    unit_batch,
)
from services.scout.ai_wire import NumericExpressionWire, inline_json_schema
from shared.openai_client import OpenAIClient


class _TextFixtureClient:
    def __init__(self, payload: object):
        self.payload = payload

    def call(self, *_args, **_kwargs) -> str:
        return json.dumps(self.payload)


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
        expression_schema = (
            contract.schema["properties"]["sources"]["items"]["properties"]
            ["measurements"]["items"]["properties"]["expression"]
        )

        self.assertEqual(expression_schema, inline_json_schema(NumericExpressionWire))
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
            contract.schema["properties"]["bindings"]["items"]["properties"]
            ["spans"]["items"]["properties"]["block_id"]
        )

        self.assertEqual(block_id_schema["enum"], allowed)
        self.assertNotIn("b-0084", block_id_schema["enum"])

    def test_context_schema_allows_only_visible_canonical_block_ids(self) -> None:
        allowed = ["DRAFT AIV iTPP v1 13July2016/b-0001"]
        contract = context_validation(allowed)
        block_id_schema = contract.schema["properties"]["block_ids"]["items"]

        self.assertEqual(block_id_schema["enum"], allowed)
        self.assertNotIn("b-0001", block_id_schema["enum"])

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
        source_ref_schema = (
            contract.schema["properties"]["reviews"]["items"]["properties"]
            ["targets"]["items"]["properties"]["semantic_profile"]
            ["properties"]["population"]["properties"]["source_refs"]["items"]
        )

        self.assertEqual(
            source_ref_schema["enum"],
            ["statement", "binding-0001", "binding-0002"],
        )
        self.assertNotIn("binding-9999", source_ref_schema["enum"])

        review = contract.schema["properties"]["reviews"]["items"]["properties"]
        self.assertEqual(review["unit_id"]["enum"], ["unit-0001"])
        self.assertEqual(review["attribute_ref"]["enum"], ["field.one"])
        self.assertEqual(
            review["targets"]["items"]["properties"]["attribute_ref"]["enum"],
            ["field.one"],
        )

    def test_request_local_lineage_is_closed_in_every_stage(self) -> None:
        query = query_batch(["doc/b-0001"], ["target-1"])
        query_item = query.schema["properties"]["queries"]["items"]["properties"]
        self.assertEqual(query_item["doc_block_ids"]["items"]["enum"], ["doc/b-0001"])
        self.assertEqual(query_item["target_ids"]["items"]["enum"], ["target-1"])

        insight = insight_batch(["https://example.test/source"])
        urls = (
            insight.schema["properties"]["insights"]["items"]["properties"]
            ["supporting_finding_urls"]["items"]["enum"]
        )
        self.assertEqual(urls, ["https://example.test/source"])

        drift = drift_batch(2, ["doc/b-0001"])
        drift_item = drift.schema["properties"]["matches"]["items"]["properties"]
        self.assertEqual(drift_item["index"]["maximum"], 1)
        self.assertEqual(drift_item["doc_block_ids"]["items"]["enum"], ["doc/b-0001"])

        source = source_measurement_batch({"endpoint"}, ["source-1"])
        source_id = source.schema["properties"]["sources"]["items"]["properties"]["source_id"]
        self.assertEqual(source_id["enum"], ["source-1"])

    def test_terminal_judgments_do_not_echo_canonical_document_facts(self) -> None:
        evidence = evidence_assessment(2).schema["properties"]
        precedent = precedent_assessment(2).schema["properties"]

        self.assertNotIn("doc_target", evidence)
        self.assertNotIn("doc_block_ids", evidence)
        self.assertNotIn("doc_block_ids", precedent)

    def test_all_schema_objects_are_closed_and_fully_required(self) -> None:
        contracts = [
            context_validation(["document/b-0001"]),
            drift_batch(1, ["document/b-0001"]),
            evidence_assessment(1),
            insight_batch(["https://example.test/source"]),
            precedent_assessment(1),
            query_batch(["document/b-0001"], ["target-1"]),
            document_quantitative_ledger_batch(
                ["binding-0001"], ["unit-1"], ["field.one"]
            ),
            target_binding_batch(
                ["document/b-0001", "document/b-0002"], ["field.one"]
            ),
            unit_batch(["document/b-0001"]),
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
        contract = drift_batch(1, ["document/b-0001"])
        client = _StructuredFixtureClient({"matches": [{"index": 0}]})
        result = request_structured(
            client,
            contract,
            "system",
            "user",
            max_tokens=100,
        )
        self.assertEqual(result, [{"index": 0}])
        self.assertEqual(client.schema_name, contract.name)

    def test_text_fixture_compatibility_is_centralized(self) -> None:
        contract = drift_batch(1, ["document/b-0001"])
        result = request_structured(
            _TextFixtureClient([{"index": 0}]),
            contract,
            "system",
            "user",
            max_tokens=100,
        )
        self.assertEqual(result, [{"index": 0}])

    def test_openai_wrapper_sends_strict_json_schema(self) -> None:
        completions = _ChatCompletions(
            json.dumps(
                {
                    "status": "match",
                    "document_indication": "malaria",
                    "reason": "The document names malaria.",
                    "block_ids": ["doc/b-0001"],
                }
            )
        )
        client = OpenAIClient.__new__(OpenAIClient)
        client.model = "test-model"
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

        self.assertEqual(result["status"], "match")
        response_format = completions.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()
