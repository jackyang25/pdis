"""Strict AI wire contracts for Scout.

These schemas describe only what one model stage may decide.  They are not the
public Scout result model: stage code still maps them into canonical dataclasses
and deterministically verifies typed shape, IDs, cited quotations, provenance,
lineage, calculation compatibility, deduplication, and rollups. Models own
semantic interpretation and prose-to-normalized-value conversion.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from shared.references import reference_array, reference_schema
from shared.schemas import blank_text, non_empty_text

from .ai_wire import (
    EvidenceUnitIdentityWire,
    EvidenceUnitPartitionWire,
    NumericExpressionWire,
    SemanticSlotWire,
    TargetExpressionWire,
    TernaryDecisionWire,
    inline_json_schema,
)
from .models import (
    COMPARISON_MATCH_MODES,
    EVIDENCE_DOMAINS,
    ENTITY_TYPES,
    QUANTITATIVE_SEMANTIC_FIELDS,
    QUANTITATIVE_FIELD_LINK_RELATIONS,
    VALID_EVIDENCE_STRENGTHS,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
    VALID_RELATIONS,
    TARGET_RELATIONSHIPS,
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


def _array(
    items: JsonSchema, *, exact_items: int | None = None, min_items: int | None = None,
) -> JsonSchema:
    schema: JsonSchema = {"type": "array", "items": items}
    if min_items is not None:
        schema["minItems"] = min_items
    if exact_items is not None:
        schema["minItems"] = exact_items
        schema["maxItems"] = exact_items
    return schema


def _string(*, enum: list[str] | None = None, required_text: bool = False) -> JsonSchema:
    """Describe one string slot.

    ``required_text`` states in the schema that blank is not an acceptable answer,
    blank meaning whitespace too, because every receiving parser strips before it
    checks. A constraint the receiving code enforces but the schema omits is a
    contract the model can satisfy and still fail, so both layers must state it.
    """
    if required_text:
        return non_empty_text(**({"enum": enum} if enum is not None else {}))
    schema: JsonSchema = {"type": "string"}
    if enum is not None:
        schema["enum"] = enum
    return schema


def _variants(
    properties: dict[str, JsonSchema],
    key: str,
    branches: list[tuple[list[str], dict[str, JsonSchema]]],
) -> JsonSchema:
    """One object per value group of ``key``, each stating what that value requires.

    The shape for a conditional rule - "a citation is required unless the verdict is
    unrelated" - so the schema states the same requirement the parser enforces. Each
    branch fixes ``key`` to its values and overrides the properties that value
    changes; the shared reference encoding resolves a reply by that field.
    """
    return {"anyOf": [
        _object({**properties, key: _string(enum=values), **changes})
        for values, changes in branches
    ]}


def _cited(ids: list[str]) -> JsonSchema:
    """At least one reference from ``ids``; an empty domain permits none."""
    schema = reference_array(ids)
    if ids:
        schema["minItems"] = 1
    return schema


def _uncited() -> JsonSchema:
    return {"type": "array", "items": {"type": "string"}, "maxItems": 0}


def _integer(*, minimum: int | None = None) -> JsonSchema:
    schema: JsonSchema = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = minimum
    return schema


def _rooted(name: str, key: str, answer: JsonSchema) -> AIContract:
    """One answer under one key: a provider's root schema must be a plain object."""
    return AIContract(name=name, schema=_object({key: answer}), payload_key=key)


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
_TERNARY = inline_json_schema(TernaryDecisionWire)
_EVIDENCE_UNIT = inline_json_schema(EvidenceUnitIdentityWire)
_EVIDENCE_UNIT_PARTITION = inline_json_schema(EvidenceUnitPartitionWire)


def context_validation(allowed_block_ids: list[str]) -> AIContract:
    """Constrain the document-indication citation to IDs in its exact input.

    A match or a mismatch must cite the blocks that establish the document's
    indication; only ``uncertain`` may cite none.
    """
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    properties = {
        "status": _string(),
        "document_indication": _string(),
        "reason": _string(required_text=True),
        "block_ids": reference_array(exact_ids),
    }
    return _rooted("scout_context_validation", "validation", _variants(properties, "status", [
        (["match", "mismatch"], {"block_ids": _cited(exact_ids)}),
        (["uncertain"], {}),
    ]))


def run_scope_value(allowed_block_ids: list[str]) -> AIContract:
    """Constrain one run-scope value to a phrase a provider field could index.

    `found` is separate from `value` because "the document does not narrow this" is a
    real answer and the only safe one when a document speaks generally. A stage that
    read a blank value as absence could not tell it from a failed reading, and a stage
    that demanded a value would get an invented country. So the two answers are two
    shapes: a found value is a phrase with its blocks, and "no" carries neither.
    """
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    properties = {"found": _string(), "value": _string(), "block_ids": reference_array(exact_ids)}
    return _rooted("scout_run_scope_value", "reading", _variants(properties, "found", [
        (["yes"], {"value": _string(required_text=True), "block_ids": _cited(exact_ids)}),
        (["no"], {"value": blank_text(), "block_ids": _uncited()}),
    ]))


def announcement_record() -> AIContract:
    """Constrain one announcement to the program it names, and nothing more.

    `names_program` is separate from `program_name` because "this announcement is about a
    pipeline, a quarter, or a company" is the common answer and a correct one. A schema
    demanding a name gets an invented one, and a stage reading a blank name as absence
    could not tell it from a failed reading. So "yes" requires the name and "no" carries
    no fields at all.

    Sponsor, phase and status are optional in the same way the record is: a development
    record may not infer a missing one, so the schema asks for them and accepts blank
    rather than pressing for a guess.
    """
    properties = {
        "names_program": _string(),
        "program_name": _string(),
        "sponsor": _string(),
        "phase": _string(),
        "status": _string(),
    }
    return _rooted("scout_announcement_record", "reading", _variants(properties, "names_program", [
        (["yes"], {"program_name": _string(required_text=True)}),
        (["no"], {name: blank_text() for name in ("program_name", "sponsor", "phase", "status")}),
    ]))


def target_binding_batch(
    allowed_block_ids: list[str],
    allowed_attribute_refs: list[str] | None = None,
) -> AIContract:
    """Constrain claim citations to source-addressable lines in one chunk.

    One binding per requested field. A present binding cites at least one span; an
    absent or uncertain one carries no spans and no entities, because it states no
    document fact.
    """
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    span = _object(
        {
            "block_id": reference_schema(exact_ids),
            "start_line": _integer(minimum=1),
            "end_line": _integer(minimum=1),
        }
    )
    properties = {
        "attribute_ref": _string(enum=allowed_attribute_refs),
        "status": _string(),
        "reason": _string(required_text=True),
        "spans": _array(span),
        "entities": _array(_ENTITY),
    }
    binding = _variants(properties, "status", [
        (["present"], {"spans": _array(span, min_items=1)}),
        (["absent", "uncertain"], {"spans": _array(span, exact_items=0),
                                    "entities": _array(_ENTITY, exact_items=0)}),
    ])
    return AIContract(
        "scout_document_claim_ledger",
        _object({"bindings": _array(
            binding,
            exact_items=len(allowed_attribute_refs) if allowed_attribute_refs else None,
        )}),
        payload_key="bindings",
    )


def unit_batch(allowed_block_ids: list[str]) -> AIContract:
    """Constrain dynamic-unit citations to source-addressable lines in one chunk."""
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    span = _object(
        {
            "block_id": reference_schema(exact_ids),
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
                "description": _string(required_text=True),
                "evidence_domain": _string(enum=sorted(EVIDENCE_DOMAINS)),
                "spans": _array(span, min_items=1),
                "entities": _array(_ENTITY),
            }
        ),
    )

def query_batch(
    allowed_block_ids: list[str],
    allowed_target_ids: list[str],
    count: int,
) -> AIContract:
    """Constrain query lineage to canonical document and target identities.

    ``count`` is the track's budget, stated as the array's exact length so a reply
    is never trimmed afterwards - trimming could cut the query that covered a target.

    ``facets`` asks for the parts of the query that field-addressed sources can
    use natively. Stating them here keeps one authority for query meaning: no
    downstream adapter has to recover them from the finished text.
    """
    return AIContract(
        "scout_query_batch",
        _object({"queries": _array(
            _object(
                {
                    "query": _string(required_text=True),
                    "facets": _object(
                        {
                            "condition": _string(),
                            "intervention": _string(),
                            "population": _string(),
                            "outcome": _string(),
                        }
                    ),
                    "doc_block_ids": reference_array(allowed_block_ids),
                    "target_ids": _array(_string(enum=allowed_target_ids or None))
                    if allowed_target_ids else _array(_string(), exact_items=0),
                }
            ),
            exact_items=count,
        )}),
        payload_key="queries",
    )


def insight_batch(allowed_record_keys: list[str]) -> AIContract:
    """Constrain insight citations to the records present in the request.

    Records are cited by their identity (`Finding.record_key`), not their URL:
    two records can share a page - FAERS counts for two reactions, a label and its
    warnings - and a URL citation could not say which one a fact came from.
    """
    return _wrapped(
        "scout_insight_batch",
        "insights",
        _object(
            {
                "statement": _string(required_text=True),
                "supporting_record_keys": _cited(list(dict.fromkeys(allowed_record_keys))),
            }
        ),
    )


def unit_reconciliation(allowed_unit_ids: list[str]) -> AIContract:
    """Partition extracted document units without authoring new claims or citations."""
    ids = list(dict.fromkeys(allowed_unit_ids))
    members = _array(_string(enum=ids))
    members["minItems"] = 1
    members["description"] = (
        "Include the representative. Every supplied unit ID must occur exactly once "
        "across all groups, including singleton groups."
    )
    return _wrapped(
        "scout_unit_reconciliation",
        "groups",
        _object({
            "representative_unit_id": _string(enum=ids),
            "member_unit_ids": members,
        }),
    )


def insight_reconciliation(allowed_insight_ids: list[str]) -> AIContract:
    """Partition duplicate insight IDs without rewriting any statement."""
    insight_ids = list(dict.fromkeys(allowed_insight_ids))
    return _wrapped(
        "scout_insight_reconciliation",
        "groups",
        _object(
            {
                "representative_insight_id": _string(enum=insight_ids),
                "member_insight_ids": _array(_string(enum=insight_ids), min_items=1),
            }
        ),
    )


def projection_reconciliation(allowed_name_ids: list[str]) -> AIContract:
    """Partition program and product names without renaming any of them."""
    name_ids = list(dict.fromkeys(allowed_name_ids))
    return _wrapped(
        "scout_projection_reconciliation",
        "groups",
        _object(
            {
                "representative_name_id": reference_schema(name_ids),
                "member_name_ids": _array(reference_schema(name_ids), min_items=1),
            }
        ),
    )


def _indices(count: int, *, cited: bool) -> JsonSchema:
    """Indices into the numbered insights; ``cited`` requires at least one."""
    if count <= 0:
        return _array({"type": "integer"}, exact_items=0)
    return _array(
        {"type": "integer", "minimum": 0, "maximum": count - 1},
        min_items=1 if cited else None,
    )


def drift_relation(allowed_block_ids: list[str]) -> AIContract:
    """One relation for one insight, citing the document blocks it compares against.

    Every relation but ``unrelated`` compares the insight with the document, so it
    cites at least one block of the binding; ``unrelated`` may cite none.
    """
    exact_ids = list(dict.fromkeys(allowed_block_ids))
    properties = {
        "relation": _string(),
        "reason": _string(required_text=True),
        "doc_block_ids": reference_array(exact_ids),
    }
    bearing = sorted(VALID_RELATIONS - {"unrelated"})
    return _rooted("scout_drift_relation", "match", _variants(properties, "relation", [
        (bearing, {"doc_block_ids": _cited(exact_ids)}),
        (["unrelated"], {}),
    ]))


def evidence_assessment(insight_count: int) -> AIContract:
    """Return only the terminal grounding judgment and selected evidence.

    Any strength but ``unknown`` rests on evidence, so it cites the insights used.
    """
    properties = {
        "strength": _string(),
        "supporting_insight_indices": _indices(insight_count, cited=False),
        "reason": _string(required_text=True),
    }
    judged = sorted(VALID_EVIDENCE_STRENGTHS - {"unknown"})
    return _rooted("scout_evidence_assessment", "assessment", _variants(properties, "strength", [
        (judged, {"supporting_insight_indices": _indices(insight_count, cited=True)}),
        (["unknown"], {}),
    ]))


def precedent_assessment(insight_count: int) -> AIContract:
    """Return only terminal precedent axes and their selected evidence.

    Each axis cites the insights behind it unless it is ``unknown``; the two are
    independent, so the schema states the four combinations.
    """
    coverage = sorted(VALID_PRECEDENT - {"unknown"})
    outcomes = sorted(VALID_PRECEDENT_OUTCOMES - {"unknown"})
    branches = []
    for precedents, coverage_cited in ((coverage, True), (["unknown"], False)):
        for outcome_values, outcome_cited in ((outcomes, True), (["unknown"], False)):
            branches.append(_object({
                "precedent": _string(enum=precedents),
                "outcome": _string(enum=outcome_values),
                "reason": _string(required_text=True),
                "coverage_insight_indices": _indices(insight_count, cited=coverage_cited),
                "outcome_insight_indices": _indices(insight_count, cited=outcome_cited),
            }))
    return _rooted("scout_precedent_assessment", "assessment", {"anyOf": branches})


def projection_relationship_batch(allowed_projection_ids: list[str]) -> AIContract:
    """Constrain display-only relationship judgments to grouped projections."""
    projection_ids = list(dict.fromkeys(allowed_projection_ids))
    decision = _object(
        {
            "projection_id": _string(enum=projection_ids),
            "target_relationship": _string(enum=sorted(TARGET_RELATIONSHIPS)),
            "reason": _string(required_text=True),
        }
    )
    return AIContract(
        name="scout_projection_relationship_batch",
        schema=_object(
            {"relationships": _array(decision, exact_items=len(projection_ids))}
        ),
        payload_key="relationships",
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
    attribute_refs = list(dict.fromkeys(allowed_attribute_refs or []))
    document_semantic_slot = deepcopy(_SEMANTIC_SLOT)
    for branch in document_semantic_slot["anyOf"]:
        asserted = branch["properties"]["state"]["enum"][0] in {"specified", "other"}
        branch["properties"]["source_refs"] = {
            **_array(_string(enum=context_refs)),
            **({"minItems": 1} if asserted else {"maxItems": 0}),
        }
        branch["required"].append("source_refs")
    document_semantic_profile = _object(
        {
            field_name: document_semantic_slot
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
    )
    comparison_contract = _object(
        {
            field_name: {"anyOf": [
                _object({
                    "mode": _string(enum=[mode]),
                    "scope": _string(required_text=mode in {"exact", "compatible"}, enum=[""] if mode == "unconstrained" else None),
                    "reason": _string(required_text=mode == "unknown"),
                })
                for mode in sorted(COMPARISON_MATCH_MODES)
            ]}
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
    )
    document_target = _object(
        {
            "quote": {"type": "string", "minLength": 1, "maxLength": 800},
            "expression": _TARGET_EXPRESSION,
            "role": _string(enum=["threshold", "optimal", "other"]),
            "semantic_profile": document_semantic_profile,
            "comparison_contract": comparison_contract,
            "field_links": _array(
                _object(
                    {
                        "attribute_ref": _string(enum=attribute_refs),
                        "relation": _string(
                            enum=sorted(QUANTITATIVE_FIELD_LINK_RELATIONS)
                        ),
                        "reason": _string(),
                    }
                )
            ),
        }
    )
    review_properties = {
        "unit_id": _string(enum=allowed_unit_ids),
        "classification": _string(),
        "attribute_refs": _array(_string(enum=attribute_refs)),
        "reason": _string(required_text=True),
        "targets": _array(document_target),
    }
    # A target review proposes at least one target; every other classification
    # proposes none, and a reply mixing the two is one the parser must refuse.
    review = _variants(review_properties, "classification", [
        (["target"], {"targets": _array(document_target, min_items=1)}),
        (
            ["context_only", "non_scalar", "range_or_set", "non_numeric", "uncertain"],
            {"targets": {"type": "array", "items": {"type": "object"}, "maxItems": 0}},
        ),
    ])
    return AIContract(
        "scout_document_quantitative_ledger_batch",
        _object(
            {
                "reviews": _array(
                    review,
                    exact_items=(
                        len(list(dict.fromkeys(allowed_unit_ids)))
                        if allowed_unit_ids is not None
                        else None
                    ),
                )
            }
        ),
    )


def quantitative_claim_reconciliation(allowed_target_ids: list[str]) -> AIContract:
    """Partition potentially duplicate claim IDs without rewriting claim data."""
    target_ids = list(dict.fromkeys(allowed_target_ids))
    return _wrapped(
        "scout_quantitative_claim_reconciliation",
        "groups",
        _object(
            {
                "representative_target_id": _string(enum=target_ids),
                "member_target_ids": _array(_string(enum=target_ids), min_items=1),
            }
        ),
    )


def target_review_batch(allowed_target_ids: list[str]) -> AIContract:
    """Constrain independent target triage to existing proposal identities."""
    target_ids = list(dict.fromkeys(allowed_target_ids))
    return AIContract(
        "scout_document_target_review",
        _object({"reviews": _array(
            _object(
                {
                    "target_id": _string(enum=target_ids),
                    "decision": _string(enum=["confirm", "exclude", "flag"]),
                    "reason": _string(required_text=True),
                }
            ),
            exact_items=len(target_ids),
        )}),
        payload_key="reviews",
    )


def evidence_review(allowed_candidate_ids: list[str]) -> AIContract:
    """One closed recommendation for every candidate of one source record."""
    candidate_ids = list(dict.fromkeys(allowed_candidate_ids))
    return AIContract(
        "scout_quantitative_evidence_review",
        _object({"decisions": _array(
            _object({
                "candidate_id": _string(enum=candidate_ids),
                "decision": _string(enum=["admit", "reject", "flag"]),
                "reason": _string(required_text=True),
            }),
            exact_items=len(candidate_ids),
        )}),
        payload_key="decisions",
    )

def source_measurement_batch(
    required_fields: set[str],
    allowed_source_ids: list[str] | None = None,
) -> AIContract:
    """Build the smallest source-mapping schema required by one target.

    Target-constrained dimensions are decided by AI. Unconstrained dimensions
    are deterministically filled as neutral after validation, so the model is
    not asked to produce irrelevant comparison metadata. One decision per
    supplied source; ``measurements_found`` carries at least one measurement and
    the other two verdicts carry none.
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
            "quote": _string(required_text=True),
            "expression": _NUMERIC_EXPRESSION,
            "evidence_unit": _EVIDENCE_UNIT,
            "semantic_assessment": _object(
                {
                    "source_ownership": _TERNARY,
                    "dimensions": dimensions,
                }
            ),
        }
    )
    properties = {
        "source_id": _string(enum=allowed_source_ids),
        "status": _string(),
        "reason": _string(required_text=True),
        "evidence_unit_partition": _EVIDENCE_UNIT_PARTITION,
        "measurements": _array(measurement),
    }
    source = _variants(properties, "status", [
        (["measurements_found"], {"measurements": _array(measurement, min_items=1)}),
        (["no_relevant_measurement", "uncertain"], {"measurements": _array(measurement, exact_items=0)}),
    ])
    return AIContract(
        "scout_source_measurement_batch",
        _object({"sources": _array(
            source,
            exact_items=len(allowed_source_ids) if allowed_source_ids else None,
        )}),
    )
