"""Deterministic end-of-pipeline integrity checks for Scout results.

Stages validate their own model output locally.  This module validates the
assembled graph once, at the service boundary, so a future stage change cannot
silently detach evidence, claims, or citations from their declared lineage.
"""

from __future__ import annotations

import math

from services.searcher import SOURCE_ROLES

from services.chunker import ContentBlock, ImageAsset

from .models import (
    PROGRAM_SCOPE_KEY,
    QUANTITATIVE_SEMANTIC_FIELDS,
    VALID_EVIDENCE_STRENGTHS,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
    VALID_QUERY_TRACKS,
    VALID_RELATIONS,
    TARGET_RELATIONSHIPS,
    Attribute,
    ComparisonRule,
    DocumentContextValidation,
    DocumentSpan,
    EvidenceEntity,
    FunnelStats,
    NumericExpression,
    QuantitativeFieldLink,
    QuantitativeLedger,
    QuantitativeLedgerReview,
    QuantitativeStatementDisposition,
    QuantitativeTarget,
    ScoutResult,
    SemanticSlot,
)


def validate_result_contract(result: ScoutResult) -> ScoutResult:
    """Return ``result`` after enforcing cross-stage structure and lineage.

    This is intentionally fail-closed. No stage or import boundary repairs a
    partially cross-wired result.
    """
    block_ids = [block.id for block in result.blocks]
    _require_unique(block_ids, "document block ID")
    known_blocks = set(block_ids)

    variables = {attribute.name: attribute for attribute in result.variables}
    if len(variables) != len(result.variables):
        raise ValueError("Scout result contains duplicate field names")
    if result.phase == "target_review" and any((
        result.search_plan,
        result.matches,
        result.assessments,
        result.conformity,
        result.precedents,
        result.development_landscape,
        result.safety_observations,
        result.burden_indicators,
    )):
        raise ValueError("target-review result cannot contain downstream analysis")

    _require_subset(
        result.quantitative_ledger.block_ids,
        known_blocks,
        "quantitative ledger document blocks",
    )
    ledger_targets = {target.id: target for target in result.quantitative_ledger.targets}
    if len(ledger_targets) != len(result.quantitative_ledger.targets):
        raise ValueError("quantitative ledger contains duplicate target IDs")
    review_ids: set[str] = set()
    reviewed_target_ids: set[str] = set()
    for review in result.quantitative_ledger.reviews:
        if review.unit_id in review_ids:
            raise ValueError("quantitative ledger contains duplicate statement units")
        review_ids.add(review.unit_id)
        _require_subset(
            [review.block_id],
            set(result.quantitative_ledger.block_ids),
            f"quantitative ledger review {review.unit_id!r}",
        )
        _require_subset(
            review.target_ids,
            set(ledger_targets),
            f"quantitative ledger review {review.unit_id!r} targets",
        )
        reviewed_target_ids.update(review.target_ids)
        _require_subset(
            review.attribute_refs,
            set(variables),
            f"quantitative ledger review {review.unit_id!r} fields",
        )
    if reviewed_target_ids != set(ledger_targets):
        raise ValueError(
            "quantitative ledger targets are not covered exactly by statement reviews"
        )
    if result.phase != "target_review":
        pending_targets = [
            target.id
            for target in ledger_targets.values()
            if target.review_status == "needs_review"
        ]
        pending_statements = [
            review.unit_id
            for review in result.quantitative_ledger.reviews
            if review.review_status == "needs_review"
        ]
        if pending_targets or pending_statements:
            raise ValueError("Scout continued with an incomplete document-target review")
    for target in ledger_targets.values():
        _require_subset(
            target.attribute_refs,
            set(variables),
            f"quantitative ledger target {target.id!r} fields",
        )
        _require_subset(
            target.doc_block_ids,
            set(result.quantitative_ledger.block_ids),
            f"quantitative ledger target {target.id!r} document blocks",
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
        if (
            set(target.comparison_contract) != set(QUANTITATIVE_SEMANTIC_FIELDS)
            or target.comparison_contract["measure"].mode != "exact"
        ):
            raise ValueError(
                f"quantitative target {target.id!r} has an invalid comparison contract"
            )

    for attribute in result.variables:
        if not attribute.target_resolution_reason:
            raise ValueError(
                f"field {attribute.name!r} has no document-resolution reason"
            )
        _require_subset(
            attribute.block_ids,
            known_blocks,
            f"field {attribute.name!r} document blocks",
        )
        if attribute.document_target and not attribute.block_ids:
            raise ValueError(
                f"field {attribute.name!r} has a document target without source blocks"
            )
        if attribute.document_target and not attribute.document_spans:
            raise ValueError(
                f"field {attribute.name!r} has a document target without exact spans"
            )
        if attribute.document_spans:
            span_block_ids = list(
                dict.fromkeys(
                    block_id
                    for span in attribute.document_spans
                    for block_id in span.block_ids
                )
            )
            _require_subset(
                span_block_ids,
                known_blocks,
                f"field {attribute.name!r} document spans",
            )
            if span_block_ids != attribute.block_ids:
                raise ValueError(
                    f"field {attribute.name!r} block IDs diverge from its exact spans"
                )
            span_target = " ".join(
                dict.fromkeys(span.quote for span in attribute.document_spans)
            )
            if span_target != attribute.document_target:
                raise ValueError(
                    f"field {attribute.name!r} target diverges from its exact spans"
                )
        if not attribute.target_resolved and (
            attribute.document_target or attribute.block_ids or attribute.entities
        ):
            raise ValueError(
                f"unresolved field {attribute.name!r} carries document facts"
            )
        if (
            attribute.quantitative_target_status == "present"
            and not attribute.quantitative_target_ids
        ):
            raise ValueError(
                f"field {attribute.name!r} reports present numeric targets but has none"
            )
        for target_id in attribute.quantitative_target_ids:
            target = ledger_targets.get(target_id)
            if target is None or attribute.name not in target.analysis_attribute_refs:
                raise ValueError(
                    f"field {attribute.name!r} references an unlinked quantitative target"
                )
        for disposition in attribute.quantitative_statement_dispositions:
            if attribute.name not in disposition.attribute_refs:
                raise ValueError(
                    "quantitative statement disposition is projected onto the wrong field"
                )
            _require_subset(
                disposition.block_ids,
                known_blocks,
                f"quantitative statement disposition for {attribute.name!r}",
            )

    projected_ledger_targets = {
        target_id: target
        for target_id, target in ledger_targets.items()
        if result.phase == "target_review" or target.review_status != "rejected"
    }
    for attribute in result.variables:
        expected_projection = [
            target.id
            for target in projected_ledger_targets.values()
            if attribute.name in target.analysis_attribute_refs
        ]
        if attribute.quantitative_target_ids != expected_projection:
            raise ValueError(
                f"field {attribute.name!r} target IDs are not the ordered projection "
                "of the canonical quantitative ledger"
            )
    targets_by_id = projected_ledger_targets

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
            if insight.attribute_ref not in targets_by_id[target_id].analysis_attribute_refs:
                raise ValueError(
                    f"insight {insight.id!r} carries a target not linked to its field"
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
        target = targets_by_id.get(score.target_id)
        if target is None or score.attribute_refs != target.analysis_attribute_refs:
            raise ValueError(
                f"calibration {score.target_id!r} drifted from its target field links"
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
            _require_insight_scope(
                [measurement.insight_id],
                set(score.attribute_refs),
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
            if measurement.admission_status not in {"approved", "auto_admitted"}:
                raise ValueError(
                    f"calibration {score.target_id!r} calculated an unadmitted measurement"
                )
            if (
                measurement.admission_status == "auto_admitted"
                and measurement.evidence_mode != "structured_fact"
            ):
                raise ValueError(
                    f"calibration {score.target_id!r} auto-admitted prose evidence"
                )
            if not measurement.evidence_unit_id:
                raise ValueError(
                    f"calibration {score.target_id!r} admitted an unidentified evidence unit"
                )
        _require_unique(
            [measurement.evidence_unit_id for measurement in score.measurements],
            f"calibration {score.target_id!r} admitted evidence unit",
        )
        if any(
            measurement.admission_status in {"approved", "auto_admitted"}
            for measurement in score.excluded_measurements
        ):
            raise ValueError(
                f"calibration {score.target_id!r} excluded an admitted measurement"
            )
        for disposition in score.source_dispositions:
            _require_insight_scope(
                [disposition.insight_id],
                set(score.attribute_refs),
                insight_by_id,
                f"source disposition {disposition.source_id!r}",
            )
            _require_source_url(
                disposition.url,
                disposition.insight_id,
                insight_by_id,
                f"source disposition {disposition.source_id!r}",
            )
    if result.phase != "target_review" and score_targets != set(targets_by_id):
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
            if trace.attribute_ref not in targets_by_id[target_id].analysis_attribute_refs:
                raise ValueError(
                    f"search trace {trace.query!r} carries a target not linked to its field"
                )
        if len(trace.intent_ids) != len(trace.input_queries):
            raise ValueError(
                f"search trace {trace.query!r} has unaligned intent lineage"
            )

    for projection_name, projections in (
        ("development program", result.development_landscape),
        ("safety observation", result.safety_observations),
    ):
        _require_unique(
            [projection.projection_id for projection in projections],
            f"{projection_name} projection ID",
        )
        for projection in projections:
            if not projection.projection_id:
                raise ValueError(f"{projection_name} is missing its projection ID")
            if projection.source_role not in SOURCE_ROLES:
                raise ValueError(
                    f"{projection_name} has invalid source role {projection.source_role!r}"
                )
            if projection.target_relationship not in TARGET_RELATIONSHIPS:
                raise ValueError(
                    f"{projection_name} has invalid target relationship "
                    f"{projection.target_relationship!r}"
                )
            _require_subset(
                projection.attribute_refs,
                # A projection retrieved by the run's own questions rather than by a
                # variable carries the program scope, which is deliberately not a
                # variable. Without it here, an announcement that reached the landscape
                # would fail the contract for naming a field the document does not have.
                set(variables) | {PROGRAM_SCOPE_KEY},
                f"{projection_name} field references",
            )
            for supporting_finding in projection.supporting_findings:
                if not supporting_finding.url or not supporting_finding.source:
                    raise ValueError(
                        f"{projection_name} contains an untraceable supporting finding"
                    )

    # Burden indicators are a projection but not a role-classified one: a disease reading
    # is not experimental or comparator, and it is not direct or analogous to a target. It
    # is a measured quantity, so what it owes is identity, traceable readings, and sources.
    _require_unique(
        [indicator.projection_id for indicator in result.burden_indicators],
        "burden indicator projection ID",
    )
    for indicator in result.burden_indicators:
        if not indicator.projection_id:
            raise ValueError("burden indicator is missing its projection ID")
        if not indicator.indicator_code:
            raise ValueError("burden indicator is missing its indicator code")
        if not indicator.readings:
            raise ValueError(
                f"burden indicator {indicator.indicator_code!r} states no reading, so it "
                "names a statistic without reporting one"
            )
        _require_subset(
            indicator.attribute_refs,
            set(variables) | {PROGRAM_SCOPE_KEY},
            "burden indicator field references",
        )
        for supporting_finding in indicator.supporting_findings:
            if not supporting_finding.url or not supporting_finding.source:
                raise ValueError(
                    "burden indicator contains an untraceable supporting finding"
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


def _require_insight_scope(
    insight_ids: list[str],
    attribute_refs: set[str],
    insights: dict,
    context: str,
) -> None:
    _require_subset(insight_ids, set(insights), f"{context} insight lineage")
    for insight_id in insight_ids:
        if insights[insight_id].attribute_ref not in attribute_refs:
            raise ValueError(f"{context} cites an insight outside its linked fields")


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


# ---------------------------------------------------------------------------
# Draft rehydration
#
# A continuation request carries back the review draft `/run` produced. Turning
# that portable payload into a `ScoutResult` is part of Scout's contract, not a
# transport concern: the rules below decide what a draft is allowed to contain.
# The payload is plain data so this stays independent of any wire model.
# ---------------------------------------------------------------------------

_DOWNSTREAM_KEYS = (
    "search_plan",
    "matches",
    "assessments",
    "conformity",
    "precedents",
    "development_landscape",
    "safety_observations",
    "burden_indicators",
)


def result_from_target_review(payload: dict) -> ScoutResult:
    """Rehydrate only the portable, pre-retrieval Scout contract.

    Deliberately does not deserialize downstream judgments: a continuation may
    contain only the target-review draft produced by ``run_pipeline``.
    """
    if payload.get("phase") != "target_review":
        raise ValueError("Scout continuation requires a target-review draft")
    if any(payload.get(key) for key in _DOWNSTREAM_KEYS):
        raise ValueError("target-review draft cannot contain downstream results")

    ledger_payload = payload["quantitative_ledger"]
    targets = [_target_from_dict(item) for item in ledger_payload["targets"]]
    known_target_ids = {target.id for target in targets}

    return ScoutResult(
        matches=[],
        assessments=[],
        stats=FunnelStats(**payload["stats"]),
        context_validation=DocumentContextValidation(**payload["context_validation"]),
        quantitative_ledger=QuantitativeLedger(
            status=ledger_payload["status"],
            reason=ledger_payload["reason"],
            block_ids=list(ledger_payload["block_ids"]),
            reviews=[
                QuantitativeLedgerReview(**review)
                for review in ledger_payload["reviews"]
            ],
            targets=targets,
        ),
        variables=[
            _attribute_from_dict(item, known_target_ids)
            for item in payload["variables"]
        ],
        blocks=[_block_from_dict(item) for item in payload["blocks"]],
        phase="target_review",
        # The window was declared before the targets were reviewed, so it is
        # rehydrated with them. Dropping it here would silently widen the cohort
        # the continuation retrieves, and the statistics would then describe a
        # different question than the one the run was scoped to.
        published_since=payload.get("published_since", ""),
    )


def _target_from_dict(raw: dict) -> QuantitativeTarget:
    raw = dict(raw)
    raw["expression"] = NumericExpression(**raw["expression"])
    raw["semantic_profile"] = {
        name: SemanticSlot(**slot) for name, slot in raw["semantic_profile"].items()
    }
    raw["comparison_contract"] = {
        name: ComparisonRule(**rule) for name, rule in raw["comparison_contract"].items()
    }
    raw["semantic_provenance"] = {
        name: [DocumentSpan(**span) for span in spans]
        for name, spans in raw["semantic_provenance"].items()
    }
    raw["provenance_spans"] = [DocumentSpan(**span) for span in raw["provenance_spans"]]
    raw["field_links"] = [QuantitativeFieldLink(**link) for link in raw["field_links"]]
    return QuantitativeTarget(**raw)


def _attribute_from_dict(raw: dict, known_target_ids: set[str]) -> Attribute:
    return Attribute(
        name=raw["name"],
        description=raw["description"],
        block_ids=raw["block_ids"],
        document_target=raw["document_target"],
        document_spans=[DocumentSpan(**span) for span in raw["document_spans"]],
        definition_mode=raw["definition_mode"],
        target_resolved=raw["target_resolved"],
        target_resolution_reason=raw["target_resolution_reason"],
        evidence_domain=raw["evidence_domain"],
        entities=[EvidenceEntity(**entity) for entity in raw["entities"]],
        # A field may not carry a reference to a target this draft does not
        # contain. Dropping the dangling reference keeps the draft internally
        # consistent; the target itself was already excluded upstream.
        quantitative_target_ids=[
            target_id
            for target_id in raw["quantitative_target_ids"]
            if target_id in known_target_ids
        ],
        quantitative_statement_dispositions=[
            QuantitativeStatementDisposition(**disposition)
            for disposition in raw["quantitative_statement_dispositions"]
        ],
        quantitative_target_status=raw["quantitative_target_status"],
        quantitative_target_status_reason=raw["quantitative_target_status_reason"],
    )


def _block_from_dict(raw: dict) -> ContentBlock:
    raw = dict(raw)
    image = raw.pop("image", None)
    return ContentBlock(**raw, image=ImageAsset(**image) if image else None)
