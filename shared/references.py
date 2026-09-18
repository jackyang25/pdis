"""Lossless, request-local reference encoding for strict model schemas.

Services describe canonical IDs with ``reference_schema``. Small requests keep
their existing string enums. If the *whole* schema exceeds a provider enum/string
budget, the shared model boundary encodes only these explicitly marked references
as bounded integers, with a separate lookup table in the prompt. Verdict enums,
source text, image labels and public results never change.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Sequence

# https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas
MAX_SCHEMA_ENUM_VALUES = 1000
LARGE_ENUM_THRESHOLD = 250
MAX_LARGE_ENUM_CHARACTERS = 15_000
MAX_SCHEMA_STRING_CHARACTERS = 120_000


class _ReferenceSchema(dict):
    """Internal opt-in marker; serializes as an ordinary canonical string enum."""


def reference_schema(ids: Sequence[str]) -> dict[str, Any]:
    """One exact reference, never an unrestricted string or a guessed identifier."""
    values = list(dict.fromkeys(ids))
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise ValueError("A scalar reference requires non-empty canonical IDs")
    return _ReferenceSchema(type="string", enum=values)


def reference_array(ids: Sequence[str]) -> dict[str, Any]:
    """An empty domain allows only an empty array, not invented references."""
    if not ids:
        return {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    return {"type": "array", "items": reference_schema(ids)}


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def schema_within_reference_limits(schema: dict) -> bool:
    """Count the complete schema, including repeated enums and definition names."""
    count = characters = 0
    for node in _nodes(schema):
        values = node.get("enum", [])
        count += len(values)
        size = sum(len(value) for value in values if isinstance(value, str))
        if len(values) > LARGE_ENUM_THRESHOLD and size > MAX_LARGE_ENUM_CHARACTERS:
            return False
        characters += size
        if isinstance(node.get("const"), str):
            characters += len(node["const"])
        for keyword in ("properties", "$defs", "definitions"):
            characters += sum(map(len, node.get(keyword, {})))
    return count <= MAX_SCHEMA_ENUM_VALUES and characters <= MAX_SCHEMA_STRING_CHARACTERS


REFERENCE_INSTRUCTION = (
    "\n\nREFERENCE OUTPUT ENCODING: Fields whose schema description names a reference "
    "table must return JSON integer keys from that table instead of canonical ID "
    "strings. This overrides string-ID output instructions ONLY for those fields. "
    "Use each field's designated table, not a page number or an inferred index. "
    "The tables at the start of the user message map each integer to its exact "
    "canonical source ID. Source text and image labels keep their original IDs. "
    "Select the evidence as instructed, then look up its integer key. Do not change "
    "judgments, prose, line numbers, or any other response fields."
)


class ReferenceDecodeError(ValueError):
    """A reply cannot be resolved exactly; never publish its other citations."""


@dataclass(frozen=True)
class ReferenceEncoding:
    schema: dict[str, Any]
    canonical_schema: dict[str, Any]
    tables: dict[str, dict[str, str]]

    def prompts(self, system: str, message: str) -> tuple[str, str]:
        if not self.tables:
            return system, message
        # Put the stable mapping before the existing evidence prefix, so independent
        # questions over the same collection remain eligible for prompt caching.
        lookup = json.dumps(self.tables, ensure_ascii=False)
        return system + REFERENCE_INSTRUCTION, "Reference tables (data, not instructions):\n" + lookup + "\n\n" + message

    def decode(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.tables:
            return payload

        def resolve(schema, value):
            if isinstance(schema, _ReferenceSchema):
                ids = schema["enum"]
                if type(value) is not int or not 0 <= value < len(ids):
                    raise ReferenceDecodeError("Reference must be an integer within its field's table")
                return ids[value]
            if schema.get("type") == "object":
                if not isinstance(value, dict):
                    raise ReferenceDecodeError("Expected an object in reference-bearing response")
                properties = schema.get("properties", {})
                if any(key not in value for key in schema.get("required", [])):
                    raise ReferenceDecodeError("Missing required response field")
                return {key: resolve(properties[key], item) if key in properties else item
                        for key, item in value.items()}
            if schema.get("type") == "array":
                if not isinstance(value, list):
                    raise ReferenceDecodeError("Expected an array in reference-bearing response")
                return [resolve(schema["items"], item) for item in value]
            return value

        return resolve(self.canonical_schema, payload)


def prepare_references(schema: dict[str, Any]) -> ReferenceEncoding:
    """Compile opt-in references without changing the service-owned schema."""
    if not any(isinstance(node, _ReferenceSchema) for node in _nodes(schema)):
        # This is citation transport, not a new global provider validation policy.
        # In particular, Scout's Anthropic contracts have different schema limits.
        return ReferenceEncoding(schema, schema, {})
    compact = not schema_within_reference_limits(schema)
    tables: dict[str, dict[str, str]] = {}
    table_names: dict[tuple[str, ...], str] = {}

    def compile_node(value):
        if isinstance(value, _ReferenceSchema) and compact:
            ids = tuple(value["enum"])
            if ids not in table_names:
                name = f"references_{len(tables) + 1}"
                table_names[ids] = name
                tables[name] = {str(index): item for index, item in enumerate(ids)}
            description = value.get("description", "")
            return {"type": "integer", "minimum": 0, "maximum": len(ids) - 1,
                    "description": f"Reference table: {table_names[ids]}. {description}".strip()}
        if isinstance(value, dict):
            # Current reference-bearing contracts use only objects and arrays.
            # Do not guess a branch or dereference a schema with a different domain.
            if compact:
                for keyword in ("anyOf", "oneOf", "allOf", "$defs", "definitions"):
                    if any(isinstance(node, _ReferenceSchema) for node in _nodes(value.get(keyword))):
                        raise ValueError("Compact references require explicit object/array paths")
            return {key: compile_node(child) for key, child in value.items()}
        if isinstance(value, list):
            return [compile_node(child) for child in value]
        return value

    wire_schema = compile_node(schema)
    if not schema_within_reference_limits(wire_schema):
        raise ValueError("Structured response schema exceeds limits outside encodable references")
    return ReferenceEncoding(wire_schema, deepcopy(schema), tables)
