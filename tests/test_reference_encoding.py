"""Reference transport must not change evidence, judgments, or canonical citations."""

from copy import deepcopy

import pytest

from services.chunker import ContentBlock, ImageAsset
from services.screener import QuestionSpec
from services.screener.stages.assessor import assess_question
from shared.ai import request_structured


def blocks(count):
    return [ContentBlock(
        id=f"document-{i % 4}/b-{i}", doc_id=f"document-{i % 4}", ordinal=i,
        block_type="paragraph", content=f"Exact evidence {i}",
        heading_stack=[], structural_meta={}, style_hint="",
    ) for i in range(count)]


def enum_count(value):
    if isinstance(value, dict):
        return len(value.get("enum", [])) + sum(enum_count(v) for v in value.values())
    if isinstance(value, list):
        return sum(enum_count(v) for v in value)
    return 0


def test_screener_large_set_retains_every_document_and_resolves_exact_image_citations():
    evidence = blocks(2293)  # The reported 2296 enums includes three decisions.
    evidence[-1].image = ImageAsset("image/png", "AA==", "hash", "image/png")
    original = deepcopy(evidence)

    class Client:
        calls = 0

        def call_structured(self, system, message, max_tokens, *, schema, images, **kwargs):
            self.calls += 1
            assert enum_count(schema) <= 1000
            assert schema["properties"]["decision"]["enum"] == [
                "answered", "partly_answered", "not_found",
            ]
            for block in evidence:
                assert block.id in message
                assert block.content in message
            assert images == [{"block_id": "document-0/b-2292", "data_url": "data:image/png;base64,AA=="}]
            assert schema["properties"]["block_ids"]["items"]["maximum"] == 2292
            return {"decision": "partly_answered", "statement": "The target is stated.",
                    "missing": "Supporting study results", "block_ids": [0, 2292]}

    client = Client()
    result = assess_question(QuestionSpec(id="Q1", text="Is the target supported?", requirement="required"),
                             blocks=evidence, llm_client=client, max_tokens=1000)
    assert client.calls == 1
    assert result.state == "partly_answered"
    assert result.statement == "The target is stated."
    assert result.missing == "Supporting study results"
    assert result.cited_block_ids == ["document-0/b-0", "document-0/b-2292"]
    assert evidence == original


def request(schema, response, *, message="Evidence is unchanged", system="Judge the evidence."):
    class Client:
        def call_structured(self, sent_system, sent_message, max_tokens, **kwargs):
            self.sent = (sent_system, sent_message, kwargs)
            return response
    client = Client()
    result = request_structured(client, system, message, schema_name="test",
                                schema=schema, max_tokens=1000)
    return result, client.sent


def test_small_screener_request_keeps_its_schema_prompt_and_response():
    from services.screener.stages.assessor import assessment_schema
    schema = assessment_schema(blocks(2))
    original = deepcopy(schema)
    response = {"decision": "answered", "statement": "Done", "missing": "",
                "block_ids": ["document-1/b-1"]}
    result, (system, message, sent) = request(schema, response)
    assert result == response
    assert system == "Judge the evidence."
    assert message == "Evidence is unchanged"
    assert sent["schema"] == original
    assert schema == original


@pytest.mark.parametrize("invalid", [-1, 2293, True, 1.5, "1", "document-0/b-0", None])
def test_large_request_refuses_invalid_reference_without_publishing_partial_citations(invalid):
    from services.screener.stages.assessor import assessment_schema
    result, _ = request(assessment_schema(blocks(2293)),
                        {"decision": "answered", "statement": "Done", "missing": "",
                         "block_ids": [0, invalid]})
    assert result is None


def test_combined_text_and_image_domains_are_bounded_separately():
    from services.aligner.context import citation_properties, read_spans, read_visual_ids
    evidence = blocks(1100)
    evidence[-1].block_type = "image"
    evidence[-1].image = ImageAsset("image/png", "AA==", "hash", "image/png")
    properties = citation_properties(evidence)
    schema = {"type": "object", "properties": properties,
              "required": list(properties), "additionalProperties": False}
    original = deepcopy(schema)
    response = {"spans": [{"block_id": 1098, "start_line": 1, "end_line": 1}],
                "visual_block_ids": [0]}
    result, (_, message, sent) = request(schema, response)
    fields = sent["schema"]["properties"]
    assert fields["spans"]["items"]["properties"]["block_id"]["maximum"] == 1098
    assert fields["visual_block_ids"]["items"]["maximum"] == 0
    assert result["spans"][0] == {"block_id": "document-2/b-1098", "start_line": 1, "end_line": 1}
    assert read_spans(result["spans"], evidence)[0].quote == "Exact evidence 1098"
    assert read_visual_ids(result["visual_block_ids"], evidence) == ["document-3/b-1099"]
    assert '"1098": "document-2/b-1098"' in message
    assert '"0": "document-3/b-1099"' in message
    assert schema == original
    assert response["visual_block_ids"] == [0]


def test_multiple_reference_fields_share_the_total_schema_budget():
    from shared.spans import line_span_schema
    ids = [f"doc/{i}" for i in range(600)]
    schema = {"type": "object", "properties": {
        "first": line_span_schema(ids), "second": line_span_schema(ids),
    }, "required": ["first", "second"], "additionalProperties": False}
    result, (_, message, sent) = request(schema, {
        "first": {"block_id": 0, "start_line": 1, "end_line": 1},
        "second": {"block_id": 599, "start_line": 2, "end_line": 2},
    })
    assert enum_count(sent["schema"]) == 0
    assert result["first"]["block_id"] == "doc/0"
    assert result["second"]["block_id"] == "doc/599"
    assert message.count('"599": "doc/599"') == 1


@pytest.mark.parametrize("count,length", [(251, 70), (2, 65000)])
def test_long_ids_trigger_encoding_even_below_enum_count_limit(count, length):
    from services.screener.stages.assessor import assessment_schema
    evidence = blocks(count)
    for item in evidence:
        item.id = "x" * length + item.id
    result, (_, _, sent) = request(assessment_schema(evidence),
                                   {"decision": "answered", "statement": "Done", "missing": "",
                                    "block_ids": [0, count - 1]})
    assert enum_count(sent["schema"]) == 3
    assert result["block_ids"] == [evidence[0].id, evidence[-1].id]


def test_unmarked_contracts_are_outside_reference_transport():
    """Other providers/contracts do not inherit a new OpenAI preflight policy."""
    schema = {"type": "object", "properties": {
        "choice": {"type": "string", "enum": [str(i) for i in range(1200)]},
    }}
    result, (system, message, sent) = request(schema, {"choice": "1199"})
    assert result == {"choice": "1199"}
    assert sent["schema"] == schema
    assert system == "Judge the evidence."
    assert message == "Evidence is unchanged"


@pytest.mark.parametrize("count,compact", [(997, False), (998, True)])
def test_exact_aggregate_enum_boundary(count, compact):
    from services.screener.stages.assessor import assessment_schema
    from shared.references import prepare_references
    evidence = blocks(count)
    for index, block in enumerate(evidence):
        block.id = f"b{index}"  # Isolate count from the independent string budget.
    encoding = prepare_references(assessment_schema(evidence))
    assert bool(encoding.tables) is compact
    assert enum_count(encoding.schema) <= 1000


def test_other_document_consumers_restore_their_canonical_contracts():
    from services.inspector.stages.assessor import assessment_schema, cross_section_schema
    from services.scout.ai_contracts import context_validation, unit_batch
    from services.assistant.priorities import digest_schema
    ids = [block.id for block in blocks(1100)]
    cases = [
        (assessment_schema(blocks(1100)),
         {"verdict": "vague", "statement": "Ambiguous", "block_ids": [1099]},
         {"verdict": "vague", "statement": "Ambiguous", "block_ids": [ids[-1]]}),
        (cross_section_schema({"a": blocks(1100)}),
         {"findings": [{"statement": "Conflict", "block_ids": [0, 1099]}]},
         {"findings": [{"statement": "Conflict", "block_ids": [ids[0], ids[-1]]}]}),
        (context_validation(ids).schema,
         {"status": "match", "document_indication": "hiv", "reason": "Stated", "block_ids": [1099]},
         {"status": "match", "document_indication": "hiv", "reason": "Stated", "block_ids": [ids[-1]]}),
        (unit_batch(ids).schema,
         {"units": [{"name": "Target", "description": "A target", "evidence_domain": "clinical",
                     "spans": [{"block_id": 1099, "start_line": 2, "end_line": 3}], "entities": []}]},
         {"units": [{"name": "Target", "description": "A target", "evidence_domain": "clinical",
                     "spans": [{"block_id": ids[-1], "start_line": 2, "end_line": 3}], "entities": []}]}),
        (digest_schema(ids),
         {"digest": "Summary", "nominations": [{"label": "Target", "statement": "Inspect", "cited_block_ids": [1099]}]},
         {"digest": "Summary", "nominations": [{"label": "Target", "statement": "Inspect", "cited_block_ids": [ids[-1]]}]}),
    ]
    for schema, response, expected in cases:
        result, (_, _, sent) = request(schema, response)
        assert result == expected
        assert enum_count(sent["schema"]) <= 1000


def test_empty_domain_and_empty_evidence_answer_remain_empty():
    from shared.references import reference_array, prepare_references
    from services.screener.stages.assessor import assessment_schema
    assert reference_array([]) == {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    encoding = prepare_references(assessment_schema(blocks(1100)))
    response = {"decision": "not_found", "statement": "", "missing": "", "block_ids": []}
    assert encoding.decode(response) == response


def test_concurrent_requests_do_not_share_reference_tables():
    from concurrent.futures import ThreadPoolExecutor
    from shared.references import reference_array

    def run(prefix):
        ids = [f"{prefix}/{i}" for i in range(1100)]
        schema = {"type": "object", "properties": {"ids": reference_array(ids)}}
        result, _ = request(schema, {"ids": [0, 1099]})
        return result["ids"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, ["a", "b", "c", "d"]))
    assert results == [[f"{prefix}/0", f"{prefix}/1099"] for prefix in ["a", "b", "c", "d"]]
