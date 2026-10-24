"""Compact reference encoding resolves a discriminated union by its closed field.

A schema states a conditional citation rule - "cite at least one block unless the
verdict is X" - as branches keyed by a closed field. Compact encoding refused any
reference under ``anyOf``, so a large document could not carry the rule at all. A
union whose branches a reply names by a fixed value is safe to encode: the decoder
picks the branch the reply states, never a guess.
"""

from __future__ import annotations

import pytest

from shared.references import ReferenceDecodeError, prepare_references, reference_array


def _contract(ids: list[str]) -> dict:
    def branch(statuses: list[str], min_items: int | None) -> dict:
        citations = reference_array(ids)
        if min_items:
            citations["minItems"] = min_items
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "block_ids"],
            "properties": {
                "status": {"type": "string", "enum": statuses},
                "block_ids": citations,
            },
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer"],
        "properties": {"answer": {"anyOf": [branch(["match", "mismatch"], 1), branch(["uncertain"], None)]}},
    }


IDS = [f"document/b-{index:05d}" for index in range(1200)]


def test_a_large_union_is_encoded_and_decoded_by_its_branch():
    encoding = prepare_references(_contract(IDS))
    assert encoding.tables, "1200 IDs must use the compact encoding"
    for option in encoding.schema["properties"]["answer"]["anyOf"]:
        assert option["properties"]["block_ids"]["items"]["type"] == "integer"
    decoded = encoding.decode({"answer": {"status": "match", "block_ids": [0, 1199]}})
    assert decoded == {"answer": {"status": "match", "block_ids": [IDS[0], IDS[1199]]}}


def test_a_reply_naming_no_branch_is_refused():
    encoding = prepare_references(_contract(IDS))
    with pytest.raises(ReferenceDecodeError):
        encoding.decode({"answer": {"status": "invented", "block_ids": [0]}})


def test_a_union_without_a_closed_discriminator_is_still_refused():
    contract = _contract(IDS)
    for option in contract["properties"]["answer"]["anyOf"]:
        option["properties"]["status"] = {"type": "string"}
    with pytest.raises(ValueError):
        prepare_references(contract)


def test_a_small_union_keeps_its_canonical_strings():
    encoding = prepare_references(_contract(IDS[:3]))
    assert encoding.tables == {}
    assert encoding.decode({"answer": {"status": "uncertain", "block_ids": []}}) == {
        "answer": {"status": "uncertain", "block_ids": []},
    }
