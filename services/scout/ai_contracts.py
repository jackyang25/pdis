"""Strict AI wire contracts for Scout.

These schemas describe only what one model stage may decide.  They are not the
public Scout result model: stage code still maps them into canonical dataclasses
and deterministically verifies IDs, quotations, provenance, units, lineage,
deduplication, and rollups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ai_wire import (
    NumericExpressionWire,
    SemanticSlotWire,
    SourceNumericSyntaxWire,
    TargetExpressionWire,
    TernaryDecisionWire,
    inline_json_schema,
)
from .models import (
    EVIDENCE_DOMAINS,
    ENTITY_TYPES,
    QUANTITATIVE_SEMANTIC_FIELDS,
    SEMANTIC_SLOT_STATES,
    VALID_EVIDENCE_STRENGTHS,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
    VALID_RELATIONS,
)


JsonSchema = dict[str, Any]


@dataclass(frozen=True)
class AIContract:
    """One provider-level schema plus its service-facing payload key."""

    name: str
    schema: JsonSchema
    payload_key: str | None = None


def _object(properties: dict[str, JsonSchema]) -> JsonSchema:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _array(items: JsonSchema) -> JsonSchema:
    return {"type": "array", "items": items}


def _string(*, enum: list[str] | None = None) -> JsonSchema:
    schema: JsonSchema = {"type": "string"}
    if enum is not None:
        schema["enum"] = enum
    return schema


def _integer(*, minimum: int | None = None) -> JsonSchema:
    schema: JsonSchema = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = minimum
    return schema


def _wrapped(name: str, key: str, item: JsonSchema) -> AIContract:
    return AIContract(name=name, schema=_object({key: _array(item)}), payload_key=key)


_ENTITY = _object(
    {
        "name": _string(),
        "entity_type": _string(enum=sorted(ENTITY_TYPES - {"other"})),
        "identifier": _string(),
    }
)
_SEMANTIC_SLOT = inline_json_schema(SemanticSlotWire)
_NUMERIC_EXPRESSION = inline_json_schema(NumericExpressionWire)
_TARGET_EXPRESSION = inline_json_schema(TargetExpressionWire)
_SOURCE_NUMERIC_SYNTAX = inline_json_schema(SourceNumericSyntaxWire)
_TERNARY = inline_json_schema(TernaryDecisionWire)


def context_validation(allowed_block_ids: list[str]) -> AIContract:
    """Constrain the document-indication citation to IDs in its exact input."""
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    return AIContract(
        "scout_context_validation",
        _object(
            {
                "status": _string(enum=["match", "mismatch", "uncertain"]),
                "document_indication": _string(),
                "reason": _string(),
                "block_ids": _array(_string(enum=exact_ids)),
            }
        ),
    )

def target_binding_batch(
    allowed_block_ids: list[str],
    allowed_attribute_refs: list[str] | None = None,
) -> AIContract:
    """Constrain claim citations to source-addressable lines in one chunk."""
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    span = _object(
        {
            "block_id": _string(enum=exact_ids),
            "start_line": _integer(minimum=1),
            "end_line": _integer(minimum=1),
        }
    )
    return _wrapped(
        "scout_document_claim_ledger",
        "bindings",
        _object(
            {
                "attribute_ref": _string(enum=allowed_attribute_refs),
                "status": _string(enum=["present", "absent", "uncertain"]),
                "reason": _string(),
                "spans": _array(span),
                "entities": _array(_ENTITY),
            }
        ),
    )

def unit_batch(allowed_block_ids: list[str]) -> AIContract:
    """Constrain dynamic-unit citations to source-addressable lines in one chunk."""
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    span = _object(
        {
            "block_id": _string(enum=exact_ids),
            "start_line": _integer(minimum=1),
            "end_line": _integer(minimum=1),
        }
    )
    return _wrapped(
        "scout_unit_batch",
        "units",
        _object(
            {
                "name": _string(),
                "description": _string(),
                "evidence_domain": _string(enum=sorted(EVIDENCE_DOMAINS)),
                "spans": _array(span),
                "entities": _array(_ENTITY),
            }
        ),
    )

def query_batch(
    allowed_block_ids: list[str],
    allowed_target_ids: list[str],
) -> AIContract:
    """Constrain query lineage to canonical document and target identities."""
    return _wrapped(
        "scout_query_batch",
        "queries",
        _object(
            {
                "query": _string(),
                "doc_block_ids": _array(_string(enum=allowed_block_ids)),
                "target_ids": _array(_string(enum=allowed_target_ids or None)),
            }
        ),
    )


def insight_batch(allowed_urls: list[str]) -> AIContract:
    """Constrain insight citations to Findings present in the request."""
    return _wrapped(
        "scout_insight_batch",
        "insights",
        _object(
            {
                "statement": _string(),
                "supporting_finding_urls": _array(_string(enum=allowed_urls)),
            }
        ),
    )


def _indices(count: int) -> JsonSchema:
    if count <= 0:
        return _array({"type": "integer"})
    return _array({"type": "integer", "minimum": 0, "maximum": count - 1})


def drift_batch(insight_count: int, allowed_block_ids: list[str]) -> AIContract:
    """Constrain drift decisions to supplied insight indices and document blocks."""
    return _wrapped(
        "scout_drift_batch",
        "matches",
        _object(
            {
                "index": (
                    {"type": "integer", "minimum": 0, "maximum": insight_count - 1}
                    if insight_count > 0
                    else {"type": "integer"}
                ),
                "relation": _string(enum=sorted(VALID_RELATIONS)),
                "reason": _string(),
                "doc_block_ids": _array(_string(enum=allowed_block_ids)),
            }
        ),
    )


def evidence_assessment(insight_count: int) -> AIContract:
    """Return only the terminal grounding judgment and selected evidence."""
    return AIContract(
        "scout_evidence_assessment",
        _object(
            {
                "strength": _string(enum=sorted(VALID_EVIDENCE_STRENGTHS)),
                "supporting_insight_indices": _indices(insight_count),
                "reason": _string(),
            }
        ),
    )


def precedent_assessment(insight_count: int) -> AIContract:
    """Return only terminal precedent axes and their selected evidence."""
    return AIContract(
        "scout_precedent_assessment",
        _object(
            {
                "precedent": _string(enum=sorted(VALID_PRECEDENT)),
                "outcome": _string(enum=sorted(VALID_PRECEDENT_OUTCOMES)),
                "reason": _string(),
                "coverage_insight_indices": _indices(insight_count),
                "outcome_insight_indices": _indices(insight_count),
            }
        ),
    )

def document_quantitative_ledger_batch(
    allowed_context_refs: list[str],
    allowed_unit_ids: list[str] | None = None,
    allowed_attribute_refs: list[str] | None = None,
) -> AIContract:
    """Constrain semantic provenance to exact canonical document bindings.

    ``statement`` refers to the statement unit currently being reviewed. Every
    other reference is an opaque ID rendered beside one already-validated
    upstream document binding. The model therefore selects semantic sources
    without copying quotations or block IDs back across the model boundary.
    """
    context_refs = list(dict.fromkeys(["statement", *allowed_context_refs]))
    document_semantic_slot = _object(
        {
            "state": _string(enum=sorted(SEMANTIC_SLOT_STATES)),
            "value": _string(),
            "other": _string(),
            "source_refs": _array(_string(enum=context_refs)),
        }
    )
    document_semantic_profile = _object(
        {
            field_name: document_semantic_slot
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
    )
    document_target = _object(
        {
            "expression": _TARGET_EXPRESSION,
            "source_syntax": _SOURCE_NUMERIC_SYNTAX,
            "role": _string(enum=["threshold", "optimal", "other"]),
            "comparison_dimensions": _array(
                _string(enum=list(QUANTITATIVE_SEMANTIC_FIELDS))
            ),
            "semantic_profile": document_semantic_profile,
            "ownership_reason": _string(),
        }
    )
    return AIContract(
        "scout_document_quantitative_ledger_batch",
        _object(
            {
                "reviews": _array(
                    _object(
                        {
                            "unit_id": _string(enum=allowed_unit_ids),
                            "classification": _string(
                                enum=[
                                    "target",
                                    "context_only",
                                    "non_scalar",
                                    "range_or_set",
                                    "non_numeric",
                                    "uncertain",
                                ]
                            ),
                            "attribute_ref": _string(enum=allowed_attribute_refs),
                            "reason": _string(),
                            "targets": _array(
                                _object(
                                    {
                                        "attribute_ref": _string(
                                            enum=allowed_attribute_refs
                                        ),
                                        **document_target["properties"],
                                    }
                                )
                            ),
                        }
                    )
                )
            }
        ),
    )

def source_measurement_batch(
    required_fields: set[str],
    allowed_source_ids: list[str] | None = None,
) -> AIContract:
    """Build the smallest source-mapping schema required by one target.

    Target-constrained dimensions are decided by AI. Unconstrained dimensions
    are deterministically filled as neutral after validation, so the model is
    not asked to produce irrelevant comparison metadata.
    """
    dimensions = _object(
        {
            field_name: _object(
                {
                    "source": _SEMANTIC_SLOT,
                    "compatibility": _TERNARY,
                }
            )
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
            if field_name in required_fields
        }
    )
    measurement = _object(
        {
            "quote": _string(),
            "expression": _NUMERIC_EXPRESSION,
            "source_syntax": _SOURCE_NUMERIC_SYNTAX,
            "semantic_assessment": _object(
                {
                    "source_ownership": _TERNARY,
                    "dimensions": dimensions,
                }
            ),
        }
    )
    source = _object(
        {
            "source_id": _string(enum=allowed_source_ids),
            "status": _string(
                enum=[
                    "measurements_found",
                    "no_relevant_measurement",
                    "uncertain",
                ]
            ),
            "reason": _string(),
            "measurements": _array(measurement),
        }
    )
    return AIContract(
        "scout_source_measurement_batch",
        _object({"sources": _array(source)}),
    )
