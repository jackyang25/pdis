from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from services.scout.ai import request_structured
from services.scout.ai_contracts import (
    CONTEXT_VALIDATION,
    DRIFT_BATCH,
    QUANTITATIVE_TARGET_SET,
    source_measurement_batch,
)
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
    def test_all_schema_objects_are_closed_and_fully_required(self) -> None:
        contracts = [
            CONTEXT_VALIDATION,
            DRIFT_BATCH,
            QUANTITATIVE_TARGET_SET,
            source_measurement_batch({"measure", "endpoint"}),
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
        client = _StructuredFixtureClient({"matches": [{"index": 0}]})
        result = request_structured(
            client,
            DRIFT_BATCH,
            "system",
            "user",
            max_tokens=100,
        )
        self.assertEqual(result, [{"index": 0}])
        self.assertEqual(client.schema_name, DRIFT_BATCH.name)

    def test_text_fixture_compatibility_is_centralized(self) -> None:
        result = request_structured(
            _TextFixtureClient([{"index": 0}]),
            DRIFT_BATCH,
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

        result = client.call_structured(
            "system",
            "user",
            500,
            schema_name=CONTEXT_VALIDATION.name,
            schema=CONTEXT_VALIDATION.schema,
        )

        self.assertEqual(result["status"], "match")
        response_format = completions.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()
