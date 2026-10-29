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
#: The fast tier: a display-only label no other axis reads. Medium effort, because the
#: label turns on whether a record contradicts a characteristic the claims make defining:
#: at low, the same eight contraception records asked three times agreed 16 of 24 times
#: (one hormonal pill analogous, its generic adjacent); at medium 21 of 24, for the same
#: median 2.7 s and about 150 tokens a call.
TASK: ModelTask = "fast"
EFFORT: Effort = "medium"
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
    # `direct` once read "the same product represented by the uploaded document". A
    # profile written for any candidate names no product, so the model stretched it to
    # "also about this indication": a live contraception iTPP labelled a copper IUD, an
    # antiprogestin and a screening study direct, one of them with a reason saying it was
    # not the product. Whether a document names its product is read from its claims, so
    # one definition serves every document type without a branch. A registry arm is named
    # for what it holds, so an RSV run also filed "Control", "Questionnaire" and a buffer
    # as direct: the label is about the named subject, never the trial around it.
    return (
        "Classify what each structured source projection is about, relative to the "
        "product the canonical document claims describe. The label is for display: do "
        "not assess evidence quality, precedent, safety causality, or whether a numeric "
        "target is met.\n\n"
        f"Configured product class: {intervention_class}. Indication: {indication}.\n\n"
        "First read from the claims what the document describes. Either it names its "
        "own product - a specific candidate identified by a name or code - or it "
        "describes a profile that any candidate could meet, naming none.\n\n"
        "target_relationship, from closest to furthest:\n"
        "- direct: the projection concerns the document's own named product, identified "
        "by that name, that code, or a synonym the source states for it. Only a document "
        "that names its product can have direct projections. Sharing the indication, the "
        "product class or the profile never makes a projection direct.\n"
        "- analogous: it concerns a different product or candidate that matches what the "
        "claims describe: the same product class, contradicting none of the "
        "characteristics the claims make defining. For a document that names no product, "
        "a product matching its profile is analogous.\n"
        "- adjacent: it is relevant context but not such a product: a product of another "
        "class, a product that departs from a characteristic the claims make defining, a "
        "complementary intervention, or other work on the indication.\n"
        "- unrelated: it has no meaningful relationship to the document's product or "
        "indication.\n"
        "- unknown: the claims or the source context are insufficient to decide.\n\n"
        "Label the projection's named subject, not the study it was taken from. A "
        "subject that is not a product - a placebo, a vehicle or buffer, a procedure, a "
        "questionnaire - is never direct or analogous, whatever the study tested.\n\n"
        "The source-study role (experimental, comparator, control) is a provider fact "
        "and does not decide the label: a comparator arm is labelled by the product it "
        "is, like any other.\n\n"
        "Return one schema-bound decision for every supplied projection ID. Its reason "
        "names the subject the projection concerns and the fact that decides the label, "
        "and agrees with the label."
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
