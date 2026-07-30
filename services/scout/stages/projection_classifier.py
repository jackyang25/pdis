"""Display-only relationship classification for structured source projections.

This stage enriches Landscape and Safety views after retrieval normalization.
Its output is never consumed by Scout's evidence, drift, calibration, or
precedent axes, and provider failures therefore degrade only these labels.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from ..ai import request_structured
from ..ai_contracts import projection_relationship_batch
from shared.batching import fixed_batches, map_ordered
from ..models import (
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
PROJECTION_WORKERS = 8
MAX_TOKENS = 5000
MAX_EXCERPT_CHARS = 1200


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
    def classify_batch(batch: list[dict[str, object]]) -> dict[str, tuple[str, str]]:
        projection_ids = [str(item["projection_id"]) for item in batch]
        try:
            parsed = request_structured(
                llm_client,
                projection_relationship_batch(projection_ids),
                build_system_prompt(
                    indication=indication,
                    intervention_class=intervention_class,
                ),
                _user_message(attributes, batch),
                max_tokens=MAX_TOKENS,
                task="fast",
            )
        except Exception as exc:  # noqa: BLE001 - optional projection enrichment
            logger.warning("Scout projection relationship mapping skipped: %s", exc)
            return {}
        return _validated_decisions(parsed, set(projection_ids))

    decisions: dict[str, tuple[str, str]] = {}
    for batch_decisions in map_ordered(
        fixed_batches(items, PROJECTIONS_PER_REQUEST),
        classify_batch,
        workers=PROJECTION_WORKERS,
    ):
        decisions.update(batch_decisions)

    return (
        [_apply_decision(item, decisions) for item in development_programs],
        [_apply_decision(item, decisions) for item in safety_observations],
    )


def _validated_decisions(
    parsed: object,
    allowed_ids: set[str],
) -> dict[str, tuple[str, str]]:
    if not isinstance(parsed, list):
        return {}
    counts: dict[str, int] = {}
    valid: dict[str, tuple[str, str]] = {}
    for raw in parsed:
        if not isinstance(raw, dict):
            continue
        projection_id = str(raw.get("projection_id") or "").strip()
        if projection_id not in allowed_ids:
            continue
        counts[projection_id] = counts.get(projection_id, 0) + 1
        relationship = str(raw.get("target_relationship") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if relationship in TARGET_RELATIONSHIPS:
            valid[projection_id] = (relationship, reason)
    return {
        projection_id: decision
        for projection_id, decision in valid.items()
        if counts.get(projection_id) == 1
    }


def _apply_decision(item, decisions: dict[str, tuple[str, str]]):
    relationship, reason = decisions.get(item.projection_id, ("unknown", ""))
    return replace(
        item,
        target_relationship=relationship,
        target_relationship_reason=reason,
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
            "excerpt": (finding.excerpt or "")[:MAX_EXCERPT_CHARS],
        }
        for finding in findings[:4]
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


def _user_message(attributes: list[Attribute], items: list[dict[str, object]]) -> str:
    canonical_claims = [
        {
            "field": attribute.name,
            "definition": attribute.description,
            "document_target": attribute.document_target,
        }
        for attribute in attributes
        if attribute.document_target
    ]
    return json.dumps(
        {
            "canonical_document_claims": canonical_claims,
            "structured_source_projections": items,
        },
        ensure_ascii=False,
    )
