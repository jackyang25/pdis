"""Deterministic end-of-pipeline integrity checks for Scout results.

Stages validate their own model output locally.  This module validates the
assembled graph once, at the service boundary, so a future stage change cannot
silently attach evidence, targets, or document citations to another field.
"""

from __future__ import annotations

import math

from .models import (
    QUANTITATIVE_SEMANTIC_FIELDS,
    VALID_EVIDENCE_STRENGTHS,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
    VALID_QUERY_TRACKS,
    VALID_RELATIONS,
    ScoutResult,
)


def validate_result_contract(result: ScoutResult) -> ScoutResult:
    """Return ``result`` after enforcing cross-stage ownership and lineage.

    This is intentionally fail-closed. Compatibility repair belongs at the
    saved-result import boundary; a fresh run must never emit a partially
    cross-wired result.
    """
    block_ids = [block.id for block in result.blocks]
    _require_unique(block_ids, "document block ID")
    known_blocks = set(block_ids)

    variables = {attribute.name: attribute for attribute in result.variables}
    if len(variables) != len(result.variables):
        raise ValueError("Scout result contains duplicate field names")

    targets_by_id = {}
    for attribute in result.variables:
        _require_subset(
            attribute.block_ids,
            known_blocks,
            f"field {attribute.name!r} document blocks",
        )
        if (
            attribute.quantitative_target_status == "present"
            and not attribute.quantitative_targets
        ):
            raise ValueError(
                f"field {attribute.name!r} reports present numeric targets but has none"
            )
        for target in attribute.quantitative_targets:
            if target.attribute_ref != attribute.name:
                raise ValueError(
                    f"quantitative target {target.id!r} is owned by "
                    f"{target.attribute_ref!r}, not {attribute.name!r}"
                )
            if target.id in targets_by_id:
                raise ValueError(f"duplicate quantitative target ID {target.id!r}")
            _require_subset(
                target.doc_block_ids,
                set(attribute.block_ids),
                f"quantitative target {target.id!r} document blocks",
            )
            if set(target.semantic_provenance) != set(QUANTITATIVE_SEMANTIC_FIELDS):
                raise ValueError(
                    f"quantitative target {target.id!r} has incomplete semantic provenance"
                )
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
                slot = target.semantic_profile[field_name]
                spans = target.semantic_provenance[field_name]
                if slot.state in {"specified", "other"} and not spans:
                    raise ValueError(
                        f"quantitative target {target.id!r} has uncited {field_name} semantics"
                    )
                if slot.state not in {"specified", "other"} and spans:
                    raise ValueError(
                        f"quantitative target {target.id!r} cites absent {field_name} semantics"
                    )
                for span in spans:
                    _require_subset(
                        span.block_ids,
                        known_blocks,
                        f"quantitative target {target.id!r} {field_name} provenance",
                    )
            targets_by_id[target.id] = target

    insight_by_id = {}
    for match in result.matches:
        insight = match.insight
        _require_field(insight.attribute_ref, variables, f"insight {insight.id!r}")
        if insight.id in insight_by_id:
            raise ValueError(f"duplicate insight ID {insight.id!r}")
        if match.relation not in VALID_RELATIONS:
            raise ValueError(f"invalid drift relation {match.relation!r}")
        if set(insight.query_tracks) - VALID_QUERY_TRACKS:
            raise ValueError(f"insight {insight.id!r} has an unknown query track")
        _require_subset(
            insight.retrieval_target_ids,
            set(targets_by_id),
            f"insight {insight.id!r} retrieval targets",
        )
        for target_id in insight.retrieval_target_ids:
            if targets_by_id[target_id].attribute_ref != insight.attribute_ref:
                raise ValueError(
                    f"insight {insight.id!r} carries a target from another field"
                )
        owned_blocks = set(variables[insight.attribute_ref].block_ids)
        _require_subset(
            match.doc_block_ids,
            owned_blocks,
            f"match for insight {insight.id!r} document blocks",
        )
        insight_by_id[insight.id] = insight

    assessment_fields: set[str] = set()
    for assessment in result.assessments:
        _require_field(
            assessment.attribute_ref,
            variables,
            f"evidence assessment {assessment.attribute_ref!r}",
        )
        if assessment.attribute_ref in assessment_fields:
            raise ValueError(
                f"duplicate evidence assessment for {assessment.attribute_ref!r}"
            )
        assessment_fields.add(assessment.attribute_ref)
        if assessment.strength not in VALID_EVIDENCE_STRENGTHS:
            raise ValueError(f"invalid grounding strength {assessment.strength!r}")
        _require_subset(
            assessment.doc_block_ids,
            set(variables[assessment.attribute_ref].block_ids),
            f"assessment {assessment.attribute_ref!r} document blocks",
        )
        _require_insight_ownership(
            assessment.supporting_insight_ids,
            assessment.attribute_ref,
            insight_by_id,
            f"assessment {assessment.attribute_ref!r}",
        )
        _require_finding_lineage(
            assessment.supporting_findings,
            assessment.supporting_insight_ids,
            insight_by_id,
            f"assessment {assessment.attribute_ref!r}",
        )

    precedent_fields: set[str] = set()
    for signal in result.precedents:
        _require_field(signal.attribute_ref, variables, f"precedent {signal.attribute_ref!r}")
        if signal.attribute_ref in precedent_fields:
            raise ValueError(f"duplicate precedent signal for {signal.attribute_ref!r}")
        precedent_fields.add(signal.attribute_ref)
        if signal.precedent not in VALID_PRECEDENT:
            raise ValueError(f"invalid precedent coverage {signal.precedent!r}")
        if signal.outcome not in VALID_PRECEDENT_OUTCOMES:
            raise ValueError(f"invalid precedent outcome {signal.outcome!r}")
        _require_subset(
            signal.doc_block_ids,
            set(variables[signal.attribute_ref].block_ids),
            f"precedent {signal.attribute_ref!r} document blocks",
        )
        combined_ids = list(
            dict.fromkeys(
                [
                    *signal.coverage_insight_ids,
                    *signal.outcome_insight_ids,
                ]
            )
        )
        if set(combined_ids) != set(signal.supporting_insight_ids):
            raise ValueError(
                f"precedent {signal.attribute_ref!r} has inconsistent insight lineage"
            )
        _require_insight_ownership(
            signal.supporting_insight_ids,
            signal.attribute_ref,
            insight_by_id,
            f"precedent {signal.attribute_ref!r}",
        )
        _require_finding_lineage(
            signal.supporting_findings,
            signal.supporting_insight_ids,
            insight_by_id,
            f"precedent {signal.attribute_ref!r}",
        )

    score_targets: set[str] = set()
    for score in result.conformity:
        _require_field(score.attribute_ref, variables, f"calibration {score.target_id!r}")
        target = targets_by_id.get(score.target_id)
        if target is None or target.attribute_ref != score.attribute_ref:
            raise ValueError(
                f"calibration {score.target_id!r} is not owned by field "
                f"{score.attribute_ref!r}"
            )
        if score.target_id in score_targets:
            raise ValueError(f"duplicate calibration for target {score.target_id!r}")
        score_targets.add(score.target_id)
        if (
            score.target_role != target.role
            or not math.isclose(score.target_value, target.value)
            or score.comparator != target.comparator
            or score.unit != target.unit
            or score.target_label != target.label
            or score.target_quote != target.quote
            or score.doc_block_ids != target.doc_block_ids
        ):
            raise ValueError(
                f"calibration {score.target_id!r} drifted from its canonical target"
            )
        _require_subset(
            score.doc_block_ids,
            set(target.doc_block_ids),
            f"calibration {score.target_id!r} document blocks",
        )
        if score.benchmark_count != len(score.measurements):
            raise ValueError(
                f"calibration {score.target_id!r} benchmark count is inconsistent"
            )
        candidate_ids = [
            measurement.candidate_id
            for measurement in [*score.measurements, *score.excluded_measurements]
        ]
        _require_unique(candidate_ids, "quantitative measurement candidate ID")
        for measurement in [*score.measurements, *score.excluded_measurements]:
            _require_insight_ownership(
                [measurement.insight_id],
                score.attribute_ref,
                insight_by_id,
                f"measurement {measurement.candidate_id!r}",
            )
            _require_source_url(
                measurement.url,
                measurement.insight_id,
                insight_by_id,
                f"measurement {measurement.candidate_id!r}",
            )
        for measurement in score.measurements:
            if measurement.semantic_status != "comparable":
                raise ValueError(
                    f"calibration {score.target_id!r} admitted a non-comparable measurement"
                )
        for disposition in score.source_dispositions:
            _require_insight_ownership(
                [disposition.insight_id],
                score.attribute_ref,
                insight_by_id,
                f"source disposition {disposition.source_id!r}",
            )
            _require_source_url(
                disposition.url,
                disposition.insight_id,
                insight_by_id,
                f"source disposition {disposition.source_id!r}",
            )
    if score_targets != set(targets_by_id):
        missing = set(targets_by_id) - score_targets
        extra = score_targets - set(targets_by_id)
        detail = ", ".join(sorted([*missing, *extra]))
        raise ValueError(f"quantitative ledgers do not cover the target set: {detail}")

    for trace in result.search_plan:
        _require_field(trace.attribute_ref, variables, f"search trace {trace.query!r}")
        if trace.status not in {"complete", "failed", "skipped"}:
            raise ValueError(f"invalid search status {trace.status!r}")
        if trace.applicability not in {"applicable", "not_applicable"}:
            raise ValueError(f"invalid source applicability {trace.applicability!r}")
        if set(trace.tracks) - VALID_QUERY_TRACKS:
            raise ValueError(f"search trace {trace.query!r} has an unknown query track")
        _require_subset(
            trace.doc_block_ids,
            set(variables[trace.attribute_ref].block_ids),
            f"search trace {trace.query!r} document blocks",
        )
        _require_subset(
            trace.target_ids,
            set(targets_by_id),
            f"search trace {trace.query!r} targets",
        )
        for target_id in trace.target_ids:
            if targets_by_id[target_id].attribute_ref != trace.attribute_ref:
                raise ValueError(
                    f"search trace {trace.query!r} carries a target from another field"
                )
        if len(trace.intent_ids) != len(trace.input_queries):
            raise ValueError(
                f"search trace {trace.query!r} has unaligned intent lineage"
            )

    for projection_name, projections in (
        ("development program", result.development_landscape),
        ("safety signal", result.safety_signals),
    ):
        for projection in projections:
            _require_subset(
                projection.attribute_refs,
                set(variables),
                f"{projection_name} field references",
            )

    _require_subset(
        result.context_validation.doc_block_ids,
        known_blocks,
        "document-context validation blocks",
    )
    if result.stats.matches != len(result.matches):
        raise ValueError("Scout match count does not match the emitted matches")
    if result.stats.insights != len(result.matches):
        raise ValueError("Scout insight count does not match the emitted insight graph")
    if result.stats.assessments != len(result.assessments):
        raise ValueError("Scout assessment count does not match the emitted assessments")
    return result


def _require_field(value: str | None, fields: dict, context: str) -> None:
    if not value or value not in fields:
        raise ValueError(f"{context} references unknown field {value!r}")


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Scout result contains a duplicate {label}")


def _require_subset(values, allowed: set[str], context: str) -> None:
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"{context} contain unknown IDs: {', '.join(sorted(unknown))}")


def _require_insight_ownership(
    insight_ids: list[str],
    attribute_ref: str,
    insights: dict,
    context: str,
) -> None:
    _require_subset(insight_ids, set(insights), f"{context} insight lineage")
    for insight_id in insight_ids:
        if insights[insight_id].attribute_ref != attribute_ref:
            raise ValueError(f"{context} cites an insight from another field")


def _require_finding_lineage(
    findings,
    insight_ids: list[str],
    insights: dict,
    context: str,
) -> None:
    allowed_urls = {
        finding.url
        for insight_id in insight_ids
        for finding in insights[insight_id].supporting_findings
    }
    _require_subset(
        [finding.url for finding in findings],
        allowed_urls,
        f"{context} finding lineage",
    )


def _require_source_url(
    url: str,
    insight_id: str,
    insights: dict,
    context: str,
) -> None:
    allowed_urls = {
        finding.url for finding in insights[insight_id].supporting_findings
    }
    if not url or url not in allowed_urls:
        raise ValueError(f"{context} references a source outside its insight lineage")
