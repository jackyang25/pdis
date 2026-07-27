"""Independent, non-authoritative triage for quantitative evidence units."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from ..ai import request_structured
from ..ai_contracts import evidence_review_batch
from ..models import (
    ConformityScore,
    LLMClientProtocol,
    Measurement,
    QuantitativeTarget,
)


MAX_GROUPS_PER_REVIEW = 12
MAX_REVIEW_WORKERS = 4
MAX_TOKENS = 6000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EvidenceReviewGroup:
    id: str
    score_index: int
    target: QuantitativeTarget
    measurements: tuple[Measurement, ...]


def prefill_evidence_review(
    scores: list[ConformityScore],
    targets: list[QuantitativeTarget],
    llm_client: LLMClientProtocol | None,
) -> list[ConformityScore]:
    """Recommend admission decisions without mutating calculation inputs.

    The independent reviewer may select only an existing candidate ID, reject
    one complete evidence unit, or flag it. Human confirmation remains the
    boundary that changes ``admission_status`` and rebuilds statistics.
    """
    groups = _review_groups(scores, targets)
    if not groups:
        return scores
    if llm_client is None:
        return _apply_recommendations(scores, groups, {})

    prompt = (
        "You independently review existing quantitative evidence mappings. You cannot "
        "create, rewrite, merge, or reassign targets, measurements, semantic dimensions, "
        "evidence units, citations, or provenance. For each evidence unit, decide admit "
        "only when one supplied candidate is a source-owned atomic scalar that is directly "
        "comparable with every required document-target dimension. Decide reject when no "
        "candidate in the unit is a valid direct comparator. Decide flag when the retained "
        "quote or mapping is genuinely ambiguous. Whether the numeric value passes the "
        "target is never an admission criterion. When alternatives exist, admit at most one "
        "candidate. Review every group ID exactly once and give one short reason. Return only "
        "schema JSON."
    )
    by_group: dict[str, tuple[str, str, str]] = {}
    batches = [
        groups[offset : offset + MAX_GROUPS_PER_REVIEW]
        for offset in range(0, len(groups), MAX_GROUPS_PER_REVIEW)
    ]

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
                "Review these existing evidence units:\n\n"
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

    with ThreadPoolExecutor(max_workers=min(MAX_REVIEW_WORKERS, len(batches))) as executor:
        responses = list(executor.map(review_batch, batches))

    for batch, raw in zip(batches, responses):
        allowed = {group.id: group for group in batch}
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("group_id", "")).strip()
            decision = str(item.get("decision", "")).strip().lower()
            selected = str(item.get("selected_candidate_id", "")).strip()
            reason = " ".join(str(item.get("reason", "")).split())
            group = allowed.get(group_id)
            candidate_ids = {
                measurement.candidate_id for measurement in group.measurements
            } if group else set()
            structurally_valid = (
                group is not None
                and group_id not in by_group
                and decision in {"admit", "reject", "flag"}
                and bool(reason)
                and (
                    (decision == "admit" and selected in candidate_ids)
                    or (decision != "admit" and not selected)
                )
            )
            if structurally_valid:
                by_group[group_id] = (decision, selected, reason)
    return _apply_recommendations(scores, groups, by_group)


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
        by_unit: dict[str, list[Measurement]] = {}
        for measurement in [*score.measurements, *score.excluded_measurements]:
            if (
                measurement.evidence_mode != "prose"
                or measurement.admission_status != "needs_review"
            ):
                continue
            unit_id = measurement.evidence_unit_id or measurement.source_record_id
            by_unit.setdefault(unit_id, []).append(measurement)
        for unit_id, measurements in by_unit.items():
            material = f"{score.target_id}\n{unit_id}"
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
            "state": slot.state,
            "value": slot.value,
            "other": slot.other,
        }
        for name, slot in target.semantic_profile.items()
        if name in target.comparison_dimensions
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
        f"Document target: {target.label}",
        f"Exact document quote: {target.quote}",
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
    recommendations: dict[str, tuple[str, str, str]],
) -> list[ConformityScore]:
    updates: dict[int, dict[str, Measurement]] = {}
    for group in groups:
        decision, selected, reason = recommendations.get(
            group.id,
            (
                "flag",
                "",
                "Independent AI review did not return one complete decision; review manually.",
            ),
        )
        score_updates = updates.setdefault(group.score_index, {})
        for measurement in group.measurements:
            recommendation = (
                "admit"
                if decision == "admit" and measurement.candidate_id == selected
                else "reject"
                if decision in {"admit", "reject"}
                else "flag"
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
