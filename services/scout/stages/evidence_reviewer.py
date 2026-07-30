"""Independent, non-authoritative triage for quantitative evidence units."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, replace

from ..ai import request_structured
from shared.batching import fixed_batches, map_ordered
from ..ai_contracts import evidence_review_batch
from ..models import (
    ConformityScore,
    LLMClientProtocol,
    Measurement,
    QuantitativeTarget,
)
from ..prompt_primitives import (
    COMPARATOR_POLICY_PRIMITIVE,
    EVIDENCE_UNIT_PRIMITIVE,
    SEMANTIC_DIMENSIONS_PRIMITIVE,
)


# Per-item scope: one admission recommendation per source record, so an
# unrelated record can never sit in this decision's prompt.
GROUPS_PER_REQUEST = 1
MAX_REVIEW_WORKERS = 4
MAX_TOKENS = 6000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EvidenceReviewGroup:
    id: str
    score_index: int
    target: QuantitativeTarget
    measurements: tuple[Measurement, ...]


def build_review_system_prompt() -> str:
    """Instructions sent when triaging external measurement proposals."""
    return (
        "ROLE\n"
        "You independently review existing quantitative evidence candidates from one source "
        "record against one document target. You recommend decisions; you cannot create, "
        "rewrite, merge, or reassign targets, measurements, semantic mappings, evidence units, "
        "citations, or provenance.\n\n"
        "INPUT AUTHORITY\n"
        "Review only the immutable target contract, mapped source facts, exact quotations, and "
        "proposed evidence-unit identities supplied for each group.\n\n"
        "SHARED PRIMITIVES\n"
        f"{SEMANTIC_DIMENSIONS_PRIMITIVE}\n\n"
        f"{COMPARATOR_POLICY_PRIMITIVE}\n\n"
        f"{EVIDENCE_UNIT_PRIMITIVE}\n\n"
        "DECISION PROCEDURE\n"
        "For every candidate, return admit, reject, or flag. Admit only a source-owned atomic "
        "scalar directly comparable with every required target dimension. Reject a candidate "
        "that is not a direct comparator or is a redundant/overlapping observation already "
        "represented by another admitted candidate from this record. Flag genuine ambiguity. "
        "Whether the value meets the target is never an admission criterion. Admit at most one "
        "alternative estimate from the same mapped evidence unit. Across different proposed "
        "units, admit multiple candidates only when the exact source text establishes mutually "
        "exclusive, non-overlapping arms or cohorts. A parent population and its subgroup overlap; "
        "retain only the most target-representative candidate. Treat mapper-supplied unit labels as "
        "proposals to verify, not proof of independence. Apply the target's direct-comparator "
        "contract as written: exact requires the same entity-level meaning, while compatible "
        "allows different named entities inside the stated scope. Do not silently narrow a "
        "compatible class to exact product identity. The target cutoff, comparator, role, and "
        "cutoff-bearing source quote are intentionally withheld because they are calculation "
        "inputs, not admission criteria.\n\n"
        "OUTPUT CONTRACT\n"
        "Review every group ID and every candidate ID exactly once. Give each decision one short, "
        "source-specific reason. Return only the schema-bound response."
    )


def prefill_evidence_review(
    scores: list[ConformityScore],
    targets: list[QuantitativeTarget],
    llm_client: LLMClientProtocol | None,
) -> list[ConformityScore]:
    """Recommend admission decisions without mutating calculation inputs.

    The independent reviewer may decide only existing candidates from one
    source record. It cannot change their mapped facts or provenance. Human
    confirmation remains the boundary that changes ``admission_status`` and
    rebuilds statistics.
    """
    groups = _review_groups(scores, targets)
    if not groups:
        return scores
    if llm_client is None:
        return _apply_recommendations(scores, groups, {})

    prompt = (
        build_review_system_prompt()
    )
    by_candidate: dict[str, tuple[str, str]] = {}
    batches = fixed_batches(groups, GROUPS_PER_REQUEST)

    def review_batch(batch: list[_EvidenceReviewGroup]) -> object | None:
        candidate_ids = [
            measurement.candidate_id
            for group in batch
            for measurement in group.measurements
        ]
        try:
            return request_structured(
                llm_client,
                evidence_review_batch(
                    [group.id for group in batch],
                    candidate_ids,
                ),
                prompt,
                "SOURCE-RECORD CANDIDATE GROUPS TO REVIEW\n"
                + "\n\n".join(_render_group(group) for group in batch),
                max_tokens=MAX_TOKENS,
                task="reasoning",
            )
        except Exception as exc:  # Triage failure must degrade to manual review.
            logger.warning(
                "Quantitative evidence AI prefill failed for %d group(s): %s",
                len(batch),
                exc,
            )
            return None

    responses = map_ordered(batches, review_batch, workers=MAX_REVIEW_WORKERS)

    for batch, raw in zip(batches, responses):
        allowed = {group.id: group for group in batch}
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("group_id", "")).strip()
            group = allowed.get(group_id)
            candidate_ids = {
                measurement.candidate_id for measurement in group.measurements
            } if group else set()
            decisions = item.get("decisions")
            if group is None or not isinstance(decisions, list):
                continue
            parsed: dict[str, tuple[str, str]] = {}
            for decision_item in decisions:
                if not isinstance(decision_item, dict):
                    continue
                candidate_id = str(decision_item.get("candidate_id", "")).strip()
                decision = str(decision_item.get("decision", "")).strip().lower()
                reason = " ".join(str(decision_item.get("reason", "")).split())
                if (
                    candidate_id in candidate_ids
                    and candidate_id not in parsed
                    and decision in {"admit", "reject", "flag"}
                    and reason
                ):
                    parsed[candidate_id] = (decision, reason)
            if set(parsed) != candidate_ids:
                continue
            measurements_by_id = {
                measurement.candidate_id: measurement
                for measurement in group.measurements
            }
            admitted_units = [
                measurements_by_id[candidate_id].evidence_unit_id
                for candidate_id, (decision, _reason) in parsed.items()
                if decision == "admit"
            ]
            if len(admitted_units) != len(set(admitted_units)):
                # One evidence unit may contribute only one alternative estimate.
                # Do not choose between semantically competing AI recommendations.
                continue
            for candidate_id, recommendation in parsed.items():
                by_candidate.setdefault(candidate_id, recommendation)
    return _apply_recommendations(scores, groups, by_candidate)


def _review_groups(
    scores: list[ConformityScore],
    targets: list[QuantitativeTarget],
) -> list[_EvidenceReviewGroup]:
    targets_by_id = {target.id: target for target in targets}
    groups: list[_EvidenceReviewGroup] = []
    for score_index, score in enumerate(scores):
        target = targets_by_id.get(score.target_id)
        if target is None:
            continue
        by_source_record: dict[str, list[Measurement]] = {}
        for measurement in [*score.measurements, *score.excluded_measurements]:
            if (
                measurement.evidence_mode != "prose"
                or measurement.admission_status != "needs_review"
            ):
                continue
            source_record_id = measurement.source_record_id or measurement.url
            by_source_record.setdefault(source_record_id, []).append(measurement)
        for source_record_id, measurements in by_source_record.items():
            material = f"{score.target_id}\n{source_record_id}"
            groups.append(_EvidenceReviewGroup(
                id="qer-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16],
                score_index=score_index,
                target=target,
                measurements=tuple(measurements),
            ))
    return groups


def _render_group(group: _EvidenceReviewGroup) -> str:
    target = group.target
    target_dimensions = {
        name: {
            "target": {
                "state": target.semantic_profile[name].state,
                "value": target.semantic_profile[name].value,
                "other": target.semantic_profile[name].other,
            },
            "comparison": {
                "mode": rule.mode,
                "scope": rule.scope,
                "reason": rule.reason,
            },
        }
        for name, rule in target.comparison_contract.items()
        if rule.mode != "unconstrained"
    }
    candidates: list[str] = []
    for measurement in group.measurements:
        source_dimensions = {
            name: {
                "source": {
                    "state": assessment.source.state,
                    "value": assessment.source.value,
                    "other": assessment.source.other,
                },
                "compatibility": {
                    "state": assessment.compatibility.state,
                    "reason": assessment.compatibility.reason,
                },
            }
            for name, assessment in measurement.semantic_assessment.dimensions.items()
            if name in target.comparison_dimensions
        }
        candidates.append("\n".join((
            f"[candidate:{measurement.candidate_id}]",
            f"Source record: {measurement.source_record_id}",
            "Proposed evidence unit: " + json.dumps({
                "id": measurement.evidence_unit_id,
                "status": measurement.evidence_unit.status,
                "group": {
                    "state": measurement.evidence_unit.group.state,
                    "value": measurement.evidence_unit.group.value,
                    "other": measurement.evidence_unit.group.other,
                },
                "cohort": {
                    "state": measurement.evidence_unit.cohort.state,
                    "value": measurement.evidence_unit.cohort.value,
                    "other": measurement.evidence_unit.cohort.other,
                },
                "reason": measurement.evidence_unit.reason,
            }, ensure_ascii=False, sort_keys=True),
            f"Exact source quote: {measurement.source_quote}",
            "Expression: " + json.dumps(
                {
                    "kind": measurement.expression.kind,
                    "value": measurement.expression.value,
                    "lower": measurement.expression.lower,
                    "upper": measurement.expression.upper,
                    "comparator": measurement.expression.comparator,
                    "unit": measurement.expression.unit,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "Source ownership: " + json.dumps({
                "state": measurement.semantic_assessment.source_ownership.state,
                "reason": measurement.semantic_assessment.source_ownership.reason,
            }, ensure_ascii=False, sort_keys=True),
            "Mapped dimensions: " + json.dumps(
                source_dimensions,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )))
    return "\n".join((
        f"[group:{group.id}]",
        "Linked fields: " + ", ".join(target.attribute_refs),
        f"Comparator measure unit: {target.unit}",
        "Required target dimensions: " + json.dumps(
            target_dimensions,
            ensure_ascii=False,
            sort_keys=True,
        ),
        *candidates,
    ))


def _apply_recommendations(
    scores: list[ConformityScore],
    groups: list[_EvidenceReviewGroup],
    recommendations: dict[str, tuple[str, str]],
) -> list[ConformityScore]:
    updates: dict[int, dict[str, Measurement]] = {}
    for group in groups:
        score_updates = updates.setdefault(group.score_index, {})
        for measurement in group.measurements:
            recommendation, reason = recommendations.get(
                measurement.candidate_id,
                (
                    "flag",
                    "Independent AI review did not return one complete source-record decision; review manually.",
                ),
            )
            score_updates[measurement.candidate_id] = replace(
                measurement,
                ai_recommendation=recommendation,
                ai_review_reason=reason,
            )

    reviewed: list[ConformityScore] = []
    for score_index, score in enumerate(scores):
        score_updates = updates.get(score_index, {})
        reviewed.append(replace(
            score,
            measurements=[
                score_updates.get(item.candidate_id, item) for item in score.measurements
            ],
            excluded_measurements=[
                score_updates.get(item.candidate_id, item)
                for item in score.excluded_measurements
            ],
        ))
    return reviewed
