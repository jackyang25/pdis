"""Strict AI wire contracts for Scout.

These schemas describe only what one model stage may decide.  They are not the
public Scout result model: stage code still maps them into canonical dataclasses
and deterministically verifies IDs, quotations, provenance, units, lineage,
deduplication, and rollups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    EVIDENCE_DOMAINS,
    ENTITY_TYPES,
    MEASUREMENT_KINDS,
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


def _nullable_number() -> JsonSchema:
    return {"type": ["number", "null"]}


def _wrapped(name: str, key: str, item: JsonSchema) -> AIContract:
    return AIContract(name=name, schema=_object({key: _array(item)}), payload_key=key)


_BLOCK_IDS = _array(_string())
_INDICES = _array({"type": "integer"})
_ENTITY = _object(
    {
        "name": _string(),
        "entity_type": _string(enum=sorted(ENTITY_TYPES - {"other"})),
        "identifier": _string(),
    }
)
_SPAN = _object({"quote": _string(), "block_ids": _BLOCK_IDS})
_SEMANTIC_SLOT = _object(
    {
        "state": _string(enum=sorted(SEMANTIC_SLOT_STATES)),
        "value": _string(),
        "other": _string(),
    }
)
_SEMANTIC_PROFILE = _object(
    {field_name: _SEMANTIC_SLOT for field_name in QUANTITATIVE_SEMANTIC_FIELDS}
)
_SEMANTIC_PROVENANCE = _object(
    {field_name: _array(_SPAN) for field_name in QUANTITATIVE_SEMANTIC_FIELDS}
)
_NUMERIC_EXPRESSION = _object(
    {
        "kind": _string(enum=sorted(MEASUREMENT_KINDS)),
        "unit": _string(),
        "value": _nullable_number(),
        "lower": _nullable_number(),
        "upper": _nullable_number(),
        "comparator": _string(),
    }
)
_TARGET_EXPRESSION = _object(
    {
        "kind": _string(enum=["bound"]),
        "unit": _string(),
        "value": {"type": "number"},
        "lower": {"type": "null"},
        "upper": {"type": "null"},
        "comparator": _string(enum=["=", "<", "<=", ">", ">="]),
    }
)
_TERNARY = _object(
    {
        "state": _string(enum=["yes", "no", "unknown"]),
        "reason": _string(),
    }
)


CONTEXT_VALIDATION = AIContract(
    "scout_context_validation",
    _object(
        {
            "status": _string(enum=["match", "mismatch", "uncertain"]),
            "document_indication": _string(),
            "reason": _string(),
            "block_ids": _BLOCK_IDS,
        }
    ),
)

TARGET_BINDING = AIContract(
    "scout_target_binding",
    _object(
        {
            "document_target": _string(),
            "block_ids": _BLOCK_IDS,
            "entities": _array(_ENTITY),
        }
    ),
)

UNIT_BATCH = _wrapped(
    "scout_unit_batch",
    "units",
    _object(
        {
            "name": _string(),
            "description": _string(),
            "evidence_domain": _string(enum=sorted(EVIDENCE_DOMAINS)),
            "document_target": _string(),
            "block_ids": _BLOCK_IDS,
            "entities": _array(_ENTITY),
        }
    ),
)

QUERY_BATCH = _wrapped(
    "scout_query_batch",
    "queries",
    _object(
        {
            "query": _string(),
            "doc_block_ids": _BLOCK_IDS,
            "target_ids": _array(_string()),
        }
    ),
)

INSIGHT_BATCH = _wrapped(
    "scout_insight_batch",
    "insights",
    _object(
        {
            "statement": _string(),
            "supporting_finding_urls": _array(_string()),
        }
    ),
)

DRIFT_BATCH = _wrapped(
    "scout_drift_batch",
    "matches",
    _object(
        {
            "index": {"type": "integer"},
            "relation": _string(enum=sorted(VALID_RELATIONS)),
            "reason": _string(),
            "doc_block_ids": _BLOCK_IDS,
        }
    ),
)

EVIDENCE_ASSESSMENT = AIContract(
    "scout_evidence_assessment",
    _object(
        {
            "strength": _string(enum=sorted(VALID_EVIDENCE_STRENGTHS)),
            "doc_target": _string(),
            "doc_block_ids": _BLOCK_IDS,
            "supporting_insight_indices": _INDICES,
            "reason": _string(),
        }
    ),
)

PRECEDENT_ASSESSMENT = AIContract(
    "scout_precedent_assessment",
    _object(
        {
            "precedent": _string(enum=sorted(VALID_PRECEDENT)),
            "outcome": _string(enum=sorted(VALID_PRECEDENT_OUTCOMES)),
            "reason": _string(),
            "doc_block_ids": _BLOCK_IDS,
            "coverage_insight_indices": _INDICES,
            "outcome_insight_indices": _INDICES,
        }
    ),
)

QUANTITATIVE_TARGET_SET = AIContract(
    "scout_quantitative_target_set",
    _object(
        {
            "status": _string(enum=["present", "not_applicable", "uncertain"]),
            "status_reason": _string(),
            "targets": _array(
                _object(
                    {
                        "expression": _TARGET_EXPRESSION,
                        "role": _string(enum=["threshold", "optimal", "other"]),
                        "semantic_profile": _SEMANTIC_PROFILE,
                        "semantic_provenance": _SEMANTIC_PROVENANCE,
                        "provenance_spans": _array(_SPAN),
                        "ownership_reason": _string(),
                    }
                )
            ),
        }
    ),
)

TARGET_OWNERSHIP = AIContract(
    "scout_target_ownership",
    _object(
        {
            "owners": _array(
                _object(
                    {
                        "group_id": _string(),
                        "attribute_ref": _string(),
                        "reason": _string(),
                    }
                )
            )
        }
    ),
)


def source_measurement_batch(required_fields: set[str]) -> AIContract:
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
            "source_id": _string(),
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
