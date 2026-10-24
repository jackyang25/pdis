"""Display-only relationship classification for structured source projections.

This stage enriches Landscape and Safety views after retrieval normalization.
Its output is never consumed by Scout's evidence, drift, calibration, or
precedent axes, so a failure degrades only these labels - and says so: the
projection is kept as ``not_assessed`` with the failure's code, never filed as
the model's ``unknown``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from shared.ai import RECORDABLE_FAILURES, Effort, ModelTask, failure_code
from shared.batching import fixed_batches, map_ordered

from ..ai import request_validated
from ..ai_contracts import projection_relationship_batch
from ..models import (
    NOT_ASSESSED,
    TARGET_RELATIONSHIPS,
    Attribute,
    DevelopmentProgram,
    LLMClientProtocol,
    SafetyObservation,
)

logger = logging.getLogger(__name__)

# Per-item scope: one relationship per projection, so an unrelated program or
# safety observation can never sit in this decision's prompt.
PROJECTIONS_PER_REQUEST = 1
#: The fast tier at low effort: a display-only label no other axis reads.
TASK: ModelTask = "fast"
EFFORT: Effort = "low"
PROJECTION_WORKERS = 8
MAX_TOKENS = 5000
#: How many of a projection's records are shown. The label is about what the records
#: are about, which the first few state as well as all of them.
CONTEXT_FINDINGS = 4


def classify_projection_relationships(
    attributes: list[Attribute],
    development_programs: list[DevelopmentProgram],
    safety_observations: list[SafetyObservation],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
) -> tuple[list[DevelopmentProgram], list[SafetyObservation]]:
    """Return new projection objects enriched with one independent relationship."""
    items = [
        _program_input(item) for item in development_programs
    ] + [
        _safety_input(item) for item in safety_observations
    ]
    system_prompt = build_system_prompt(
        indication=indication,
        intervention_class=intervention_class,
    )

    claims = _claims_message(attributes)

    def classify_batch(batch: list[dict[str, object]]) -> dict[str, _Decision]:
        projection_ids = [str(item["projection_id"]) for item in batch]
        try:
            return request_validated(
                llm_client,
                projection_relationship_batch(projection_ids),
                system_prompt,
                claims,
                max_tokens=MAX_TOKENS,
                parse=lambda parsed: _validated_decisions(parsed, projection_ids),
                failure="Projection relationship classification failed",
                trailing_text=_projections_message(batch),
                task=TASK,
                effort=EFFORT,
            )
        except RECORDABLE_FAILURES as exc:
            logger.warning("Scout projection relationship mapping skipped: %s", exc)
            return {
                projection_id: (NOT_ASSESSED, str(exc), failure_code(exc))
                for projection_id in projection_ids
            }

    decisions: dict[str, _Decision] = {}
    for batch_decisions in map_ordered(
        fixed_batches(items, PROJECTIONS_PER_REQUEST),
        classify_batch,
        workers=PROJECTION_WORKERS,
    ):
        decisions.update(batch_decisions)

    return (
        [_apply_decision(item, decisions[item.projection_id]) for item in development_programs],
        [_apply_decision(item, decisions[item.projection_id]) for item in safety_observations],
    )


#: relationship, reason, failure code ("" for a model decision).
_Decision = tuple[str, str, str]


def _validated_decisions(parsed: object, projection_ids: list[str]) -> dict[str, _Decision]:
    """Exactly one decision with a closed relationship and a reason per requested ID."""
    if not isinstance(parsed, list):
        raise ValueError("no relationships array was returned")
    decisions: dict[str, _Decision] = {}
    for raw in parsed:
        if not isinstance(raw, dict):
            raise ValueError("every relationship must be an object")
        projection_id = str(raw.get("projection_id") or "").strip()
        if projection_id not in projection_ids or projection_id in decisions:
            raise ValueError("return exactly one decision per supplied projection ID")
        relationship = str(raw.get("target_relationship") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if relationship not in TARGET_RELATIONSHIPS or not reason:
            raise ValueError("a relationship from the closed list and a reason are required")
        decisions[projection_id] = (relationship, reason, "")
    if set(decisions) != set(projection_ids):
        raise ValueError("return exactly one decision per supplied projection ID")
    return decisions


def _apply_decision(item, decision: _Decision):
    relationship, reason, code = decision
    return replace(
        item,
        target_relationship=relationship,
        target_relationship_reason=reason,
        target_relationship_failure_code=code,
    )


def _program_input(item: DevelopmentProgram) -> dict[str, object]:
    return {
        "projection_id": item.projection_id,
        "projection_kind": "development_record",
        "name": item.name,
        "source_role": item.source_role,
        "record_types": item.record_types,
        "source_context": _finding_context(item.supporting_findings),
    }


def _safety_input(item: SafetyObservation) -> dict[str, object]:
    return {
        "projection_id": item.projection_id,
        "projection_kind": "safety_observation",
        "name": item.product_name,
        "source_role": item.source_role,
        "record_type": item.record_type,
        "source_system": item.source_system,
        "label": item.label,
        "detail": item.detail,
        "source_context": _finding_context(item.supporting_findings),
    }


def _finding_context(findings) -> list[dict[str, str]]:
    return [
        {
            "title": finding.title,
            "source": finding.source,
            "excerpt": finding.excerpt or "",
        }
        for finding in findings[:CONTEXT_FINDINGS]
    ]


def build_system_prompt(*, indication: str, intervention_class: str) -> str:
    return (
        "Classify how each structured source projection relates to the product "
        "described by the canonical document claims. This is a display-only "
        "relationship label; do not assess evidence quality, precedent, safety "
        "causality, or whether a numeric target is met.\n\n"
        f"Configured product class: {intervention_class}. Indication: {indication}.\n\n"
        "target_relationship meanings:\n"
        "- direct: the record or signal concerns the same product/intervention "
        "represented by the uploaded document.\n"
        "- analogous: it concerns a different named candidate or product in the "
        "same relevant intervention class or product archetype.\n"
        "- adjacent: it is relevant contextual work, a complementary intervention, "
        "or another product class, but is not a same-class analogue.\n"
        "- unrelated: it has no meaningful relationship to the document product.\n"
        "- unknown: the supplied canonical claims or source context are insufficient.\n\n"
        "Source-study role is an independent provider fact. Experimental, comparator, "
        "or control does not by itself determine target relationship. Return one "
        "schema-bound decision for every supplied projection ID and a short reason."
    )


def _claims_message(attributes: list[Attribute]) -> str:
    """The document's canonical claims: the prefix every projection's request shares."""
    canonical_claims = [
        {
            "field": attribute.name,
            "definition": attribute.description,
            "document_target": attribute.document_target,
        }
        for attribute in attributes
        if attribute.document_target
    ]
    return "Canonical document claims:\n" + json.dumps(canonical_claims, ensure_ascii=False)


def _projections_message(items: list[dict[str, object]]) -> str:
    return (
        "\n\nStructured source projections to classify:\n"
        + json.dumps(items, ensure_ascii=False)
    )
