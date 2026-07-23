"""Stage: traceable quantitative calibration for ONE document claim.

A transparent, reproducible complement to the qualitative `evidence_assessor`.
Where sources report comparable numbers against a doc-stated target (e.g.
efficacy >= 80%), this:

  1. (LLM) selects exact document/source spans and proposes closed
     claim-comparability labels.
  2. (code) verifies quotes, values, units, URLs, document blocks, enums, and
     source identities; then builds an included/excluded cohort ledger.
  3. (math) reports observed cohort statistics and the literal share meeting
     the target. No weighting or inferential confidence interval is implied.

Self-gating: returns None for non-quantitative variables. A verified numeric
target remains an explicit ledger even when no comparator qualifies. Pure
stdlib; no R or numpy.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import fmean, stdev
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from services.searcher import Finding

from ..context import (
    BLOCK_ID_JSON_INSTRUCTION,
    document_block_ids,
    limit_document_context,
    validated_block_ids,
)
from ..models import (
    AxisEvidence,
    Attribute,
    ConformityScore,
    Insight,
    LLMClientProtocol,
    MANDATORY_QUANTITATIVE_AXES,
    Measurement,
    QUANTITATIVE_COMPARABILITY_AXES,
    QuantitativeTarget,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
OWNERSHIP_MAX_TOKENS = 8000
MEASUREMENT_BATCH_SIZE = 4
MAX_TARGET_QUOTE_CHARS = 800
# Keep in lockstep with drift_classifier / evidence_assessor so all three
# doc-reading stages see the SAME baseline and a target near the end of a long
# doc is never cut off in one stage but not another.

_METHODOLOGY_PATH = Path(__file__).resolve().parents[1] / "configs" / "evidence_methodology.yaml"
with _METHODOLOGY_PATH.open("r", encoding="utf-8") as _methodology_file:
    _METHODOLOGY = yaml.safe_load(_methodology_file) or {}

VALID_EVIDENCE_FORMS = set(_METHODOLOGY["evidence_forms"])
VALID_PHASES = set(_METHODOLOGY["development_phases"])
VALID_SOURCE_RECORD_TYPES = set(_METHODOLOGY["source_record_types"])
CALIBRATION_LIMITED_MIN_COUNT = int(
    _METHODOLOGY["calibration_limited_min_count"]
)

COMPARABILITY_AXES = QUANTITATIVE_COMPARABILITY_AXES
COMPARABILITY_RELATIONS = frozenset(
    {"same", "compatible", "not_applicable", "different", "unknown"}
)
INCLUDABLE_RELATIONS_BY_AXIS = {
    "endpoint": frozenset({"same"}),
    "population": frozenset({"same", "not_applicable"}),
    "intervention": frozenset({"same", "compatible"}),
    "regimen": frozenset({"same", "not_applicable"}),
    "time_horizon": frozenset({"same", "not_applicable"}),
    "statistic": frozenset({"same"}),
}
CALIBRATION_SUFFICIENT_MIN_COUNT = int(
    _METHODOLOGY["calibration_sufficient_min_count"]
)
VALID_TARGET_ROLES = frozenset({"threshold", "optimal", "other"})


@dataclass(frozen=True)
class _NumericCandidate:
    id: str
    value: float
    unit: str
    insight: Insight
    finding: Finding
    source_quote: str


def score_conformity(
    attribute: Attribute,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[ConformityScore]:
    """Calibrate the canonical targets already bound to this Attribute."""
    scores: list[ConformityScore] = []
    for target in attribute.quantitative_targets:
        candidates = _classify_target_candidates(
            attribute,
            target,
            insights,
            llm_client,
            indication=indication,
            intervention_class=intervention_class,
            max_tokens=max_tokens,
        )
        measurements, excluded_measurements = _partition_cohort(candidates)
        if not measurements:
            scores.append(_empty_score(target, excluded_measurements))
            continue
        _attach_dates(measurements, insights)
        scores.append(
            _combine(
                target,
                measurements,
                excluded_measurements,
            )
        )
    return scores


def empty_conformity_scores(
    attributes: list[Attribute],
) -> list[ConformityScore]:
    """Project verified targets when retrieval yields no numeric evidence."""
    return [
        _empty_score(target, [])
        for attribute in attributes
        for target in attribute.quantitative_targets
    ]


def _empty_score(
    target: QuantitativeTarget,
    excluded_measurements: list[Measurement],
) -> ConformityScore:
    return ConformityScore(
        attribute_ref=target.attribute_ref,
        target_id=target.id,
        target_role=target.role,
        target_value=target.value,
        comparator=target.comparator,
        unit=target.unit,
        target_label=target.label,
        target_quote=target.quote,
        target_meeting_count=0,
        target_meeting_rate=0.0,
        verdict="No validated claim-compatible comparators",
        calibration_status="insufficient",
        doc_block_ids=target.doc_block_ids,
        excluded_measurements=excluded_measurements,
    )


def _partition_cohort(
    candidates: list[Measurement],
) -> tuple[list[Measurement], list[Measurement]]:
    """Apply comparability and source-identity rules without model discretion."""
    included: list[Measurement] = []
    excluded: list[Measurement] = []
    seen_records: set[str] = set()
    for candidate in candidates:
        reasons = list(candidate.exclusion_reasons)
        reasons.extend(
            [
                f"{axis}: {candidate.comparability.get(axis, 'unknown')}"
                + (
                    f" — {candidate.comparability_reasons.get(axis, '')}"
                    if candidate.comparability_reasons.get(axis)
                    else ""
                )
                for axis in COMPARABILITY_AXES
                if candidate.comparability.get(axis, "unknown")
                not in INCLUDABLE_RELATIONS_BY_AXIS[axis]
            ]
        )
        if not reasons and candidate.source_record_id in seen_records:
            reasons.append(
                f"duplicate source record: {candidate.source_record_id}"
            )
        if reasons:
            candidate.exclusion_reasons = reasons
            excluded.append(candidate)
            continue
        candidate.inclusion_reason = (
            "Endpoint/statistic match; population, regimen, and time horizon match or "
            "are not applicable; intervention is the same or an explicit comparator; "
            f"deduplicated as {candidate.source_record_id}."
        )
        seen_records.add(candidate.source_record_id)
        included.append(candidate)
    return included, excluded


# ---------------------------------------------------------------------------
# Combination math (pure, deterministic)
# ---------------------------------------------------------------------------


def _combine(
    target: QuantitativeTarget,
    measurements: list[Measurement],
    excluded_measurements: list[Measurement],
) -> ConformityScore:
    benchmark_values = sorted(measurement.value for measurement in measurements)
    benchmark_count = len(benchmark_values)
    met_target = [
        _meets_target(value, target.value, target.comparator)
        for value in benchmark_values
    ]
    target_meeting_count = sum(met_target)
    target_meeting_rate = target_meeting_count / benchmark_count
    target_percentile = _empirical_percentile(benchmark_values, target.value)
    ambition_percentile = (
        1.0 - target_percentile
        if target.comparator in {"<", "<="}
        else target_percentile
    )

    return ConformityScore(
        attribute_ref=target.attribute_ref,
        target_id=target.id,
        target_role=target.role,
        target_value=target.value,
        comparator=target.comparator,
        unit=target.unit,
        target_label=target.label,
        target_quote=target.quote,
        target_meeting_count=target_meeting_count,
        target_meeting_rate=round(target_meeting_rate, 3),
        verdict=(
            f"{target_meeting_count} of {benchmark_count} validated comparators "
            "meet the document target"
        ),
        benchmark_count=benchmark_count,
        benchmark_minimum=round(benchmark_values[0], 3),
        benchmark_maximum=round(benchmark_values[-1], 3),
        benchmark_mean=round(fmean(benchmark_values), 3),
        benchmark_median=round(_quantile(benchmark_values, 0.5), 3),
        benchmark_lower_quartile=round(_quantile(benchmark_values, 0.25), 3),
        benchmark_upper_quartile=round(_quantile(benchmark_values, 0.75), 3),
        benchmark_standard_deviation=(
            round(stdev(benchmark_values), 3) if benchmark_count >= 2 else None
        ),
        target_percentile=round(target_percentile, 3),
        ambition_percentile=round(ambition_percentile, 3),
        calibration_status=_calibration_status(measurements),
        doc_block_ids=target.doc_block_ids,
        measurements=measurements,
        excluded_measurements=excluded_measurements,
    )


def _quantile(values: list[float], probability: float) -> float:
    """Return a linearly interpolated empirical quantile for sorted values."""
    if not values:
        raise ValueError("at least one benchmark value is required")
    position = (len(values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return values[lower_index]
    fraction = position - lower_index
    return values[lower_index] + fraction * (
        values[upper_index] - values[lower_index]
    )


def _empirical_percentile(values: list[float], target: float) -> float:
    """Midpoint empirical CDF, avoiding an arbitrary all-or-nothing tie rank."""
    below = sum(value < target for value in values)
    equal = sum(value == target for value in values)
    return (below + 0.5 * equal) / len(values)


def _calibration_status(measurements: list[Measurement]) -> str:
    benchmark_count = len(measurements)
    if benchmark_count >= CALIBRATION_SUFFICIENT_MIN_COUNT:
        if all(
            measurement.source_identity_status == "canonical"
            for measurement in measurements
        ):
            return "sufficient"
    if benchmark_count >= CALIBRATION_LIMITED_MIN_COUNT:
        return "limited"
    return "insufficient"


def _meets_target(value: float, target: float, comparator: str) -> bool:
    return {
        "<": value < target,
        "<=": value <= target,
        ">": value > target,
        ">=": value >= target,
    }[comparator]


def _attach_dates(measurements: list[Measurement], insights: list[Insight]) -> None:
    """Attach source age for display without using it to alter cohort statistics."""
    published_by_url = {
        f.url: f.published_at
        for insight in insights
        for f in insight.supporting_findings
    }
    for m in measurements:
        published = published_by_url.get(m.url)
        m.age_months = _age_months(published)


def _age_months(published) -> float | None:
    if published is None:
        return None
    try:
        from datetime import datetime, timezone

        if isinstance(published, str):
            published = datetime.fromisoformat(published)
        now = datetime.now(timezone.utc)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        days = (now - published).days
        return max(0.0, days / 30.4)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------


def extract_quantitative_targets(
    attribute: Attribute,
    doc_text: str,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[QuantitativeTarget]:
    attempts = 2 if _looks_directional_numeric(attribute.document_target) else 1
    for attempt in range(attempts):
        retry_note = (
            "\n\nYour prior response omitted or malformed a visible numeric target. "
            "Return every distinct target as a separate exact-quoted object."
            if attempt
            else ""
        )
        raw = llm_client.call(
            _target_system_prompt(
                attribute,
                indication,
                intervention_class,
                framing=framing,
            ),
            _target_user_message(attribute, doc_text) + retry_note,
            max_tokens=max_tokens,
            images=images,
        )
        parsed = _parse(raw) or {}
        targets = _validated_targets(
            parsed.get("targets"),
            attribute=attribute,
            doc_text=doc_text,
            require_comparison_axes=True,
        )
        if targets or attempts == 1:
            return targets
    return []


def revalidate_quantitative_targets(
    attribute: Attribute,
    doc_text: str,
) -> list[QuantitativeTarget]:
    """Verify saved targets against their portable document blocks and stable IDs."""
    items = [
        {
            "value": target.value,
            "comparator": target.comparator,
            "unit": target.unit,
            "label": target.label,
            "role": target.role,
            "quote": target.quote,
            "doc_block_ids": target.doc_block_ids,
            "required_comparison_axes": target.required_comparison_axes,
            "ownership_candidates": target.ownership_candidates,
            "ownership_reason": target.ownership_reason,
        }
        for target in attribute.quantitative_targets
    ]
    validated = _validated_targets(items, attribute=attribute, doc_text=doc_text)
    supplied_ids = {target.id for target in attribute.quantitative_targets}
    return [target for target in validated if target.id in supplied_ids]


def resolve_quantitative_target_ownership(
    attributes: list[Attribute],
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int = OWNERSHIP_MAX_TOKENS,
) -> list[Attribute]:
    """Assign each exact repeated document target to one canonical field.

    A table row may legitimately bind to several overlapping fixed fields. The
    document fact is still one target, so repeated exact claims are arbitrated
    once against the closed candidate definitions. Unique targets require no
    model call. Invalid or omitted arbitration fails closed for that ambiguous
    group rather than duplicating one cohort under several labels.
    """
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    original_target_ids = {
        target.id
        for attribute in attributes
        for target in attribute.quantitative_targets
    }
    groups: dict[tuple[object, ...], list[QuantitativeTarget]] = {}
    for attribute in attributes:
        for target in attribute.quantitative_targets:
            key = (
                target.role,
                target.comparator,
                target.value,
                _canonical_unit(target.unit),
                _normalize_quote(target.quote),
                tuple(sorted(target.doc_block_ids)),
            )
            groups.setdefault(key, []).append(target)

    # Extraction is intentionally per field, so one field may omit a target
    # that another overlapping field found in the same table row. Build the
    # arbitration set from every resolved binding that owns the same source
    # block, not only from model emission. A binding summary may omit one cell
    # from a multi-value row; the closed field definitions then decide which
    # candidate most specifically owns the already verified exact claim.
    for targets in groups.values():
        exemplar = targets[0]
        existing_refs = {target.attribute_ref for target in targets}
        for attribute in attributes:
            shared_blocks = [
                block_id
                for block_id in exemplar.doc_block_ids
                if block_id in attribute.block_ids
            ]
            if (
                attribute.name in existing_refs
                or not shared_blocks
                or not _target_supported_by_binding(
                    exemplar.value,
                    exemplar.comparator,
                    exemplar.unit,
                    attribute.document_target,
                )
            ):
                continue
            targets.append(
                QuantitativeTarget(
                    attribute_ref=attribute.name,
                    value=exemplar.value,
                    comparator=exemplar.comparator,
                    unit=exemplar.unit,
                    label=exemplar.label,
                    role=exemplar.role,
                    quote=exemplar.quote,
                    doc_block_ids=shared_blocks,
                    required_comparison_axes=exemplar.required_comparison_axes,
                )
            )
            existing_refs.add(attribute.name)

    ambiguous: dict[str, list[QuantitativeTarget]] = {}
    keep_ids = {
        targets[0].id for targets in groups.values() if len(targets) == 1
    }
    replacements: dict[str, QuantitativeTarget] = {}
    transferred: dict[str, list[QuantitativeTarget]] = {}
    for key, targets in groups.items():
        if len(targets) < 2:
            continue
        material = json.dumps(key, sort_keys=True, ensure_ascii=False)
        group_id = "qg-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        ambiguous[group_id] = targets

    if ambiguous:
        system_prompt = _ownership_system_prompt()
        user_message = _ownership_user_message(ambiguous, attributes_by_name)
        decisions: dict[str, tuple[str, str]] = {}
        for attempt in range(2):
            raw = llm_client.call(
                system_prompt,
                user_message
                + (
                    "\n\nA prior response was incomplete. Return one owner for every "
                    "group ID above."
                    if attempt
                    else ""
                ),
                max_tokens=max_tokens,
            )
            parsed = _parse(raw) or {}
            decisions.update(_validated_ownership_decisions(parsed, ambiguous))
            if set(decisions) == set(ambiguous):
                break

        for group_id, targets in ambiguous.items():
            decision = decisions.get(group_id)
            if decision is None:
                logger.warning(
                    "quantitative target ownership unresolved for %s; omitting ambiguous target",
                    group_id,
                )
                continue
            owner, reason = decision
            selected = next(target for target in targets if target.attribute_ref == owner)
            candidate_refs = list(
                dict.fromkeys(target.attribute_ref for target in targets)
            )
            replacements[selected.id] = replace(
                selected,
                ownership_candidates=candidate_refs,
                ownership_reason=reason,
            )
            keep_ids.add(selected.id)
            if selected.id not in original_target_ids:
                transferred.setdefault(owner, []).append(replacements[selected.id])

    return [
        replace(
            attribute,
            quantitative_targets=[
                replacements.get(target.id, target)
                for target in attribute.quantitative_targets
                if target.id in keep_ids
            ]
            + transferred.get(attribute.name, []),
        )
        for attribute in attributes
    ]


def _validated_targets(
    items: object,
    *,
    attribute: Attribute,
    doc_text: str,
    require_comparison_axes: bool = False,
) -> list[QuantitativeTarget]:
    if not isinstance(items, list):
        return []
    # A target is a fact owned by the canonical field binding, not merely a fact
    # found in relevance-selected context. Both the rendered input and the
    # binding must authorize its exact source block.
    rendered_ids = document_block_ids(doc_text)
    allowed_ids = set(attribute.block_ids)
    if rendered_ids:
        allowed_ids &= rendered_ids
    targets: list[QuantitativeTarget] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        comparator = str(item.get("comparator", "")).strip()
        unit = str(item.get("unit", "")).strip()
        label = str(item.get("label", "")).strip()
        role = str(item.get("role", "other")).strip().lower()
        quote = str(item.get("quote", "")).strip()
        required_axes = _validated_required_axes(
            item.get("required_comparison_axes"),
            required=require_comparison_axes,
        )
        raw_candidates = item.get("ownership_candidates", [])
        ownership_candidates = (
            [
                value.strip()
                for value in raw_candidates
                if isinstance(value, str) and value.strip()
            ]
            if isinstance(raw_candidates, list)
            else []
        )
        if ownership_candidates and attribute.name not in ownership_candidates:
            continue
        ownership_reason = str(item.get("ownership_reason", "")).strip()
        block_ids = validated_block_ids(item.get("doc_block_ids"), allowed_ids)
        source_text = _text_for_blocks(doc_text, block_ids)
        if (
            not _is_finite_number(value)
            or comparator not in {">", ">=", "<", "<="}
            or not unit
            or not label
            or role not in VALID_TARGET_ROLES
            or not block_ids
            or not quote
            or required_axes is None
            or len(quote) > MAX_TARGET_QUOTE_CHARS
            or not _quote_in_text(quote, source_text)
            or not _value_unit_supported(float(value), unit, quote)
            or not _comparator_supported(comparator, quote)
            or not _target_supported_by_binding(
                float(value), comparator, unit, attribute.document_target
            )
        ):
            continue
        target = QuantitativeTarget(
            attribute_ref=attribute.name,
            value=float(value),
            comparator=comparator,
            unit=unit,
            label=label,
            role=role,
            quote=quote,
            doc_block_ids=block_ids,
            required_comparison_axes=required_axes,
            ownership_candidates=ownership_candidates,
            ownership_reason=ownership_reason,
        )
        if target.id in seen:
            continue
        seen.add(target.id)
        targets.append(target)
    return targets


def _classify_target_candidates(
    attribute: Attribute,
    target: QuantitativeTarget,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int,
) -> list[Measurement]:
    numeric_candidates = _numeric_candidates(insights, target.unit)
    measurements: list[Measurement] = []
    decided: set[str] = set()
    for start in range(0, len(numeric_candidates), MEASUREMENT_BATCH_SIZE):
        batch = numeric_candidates[start : start + MEASUREMENT_BATCH_SIZE]
        system_prompt = _measurement_system_prompt(
            attribute,
            target=target,
            indication=indication,
            intervention_class=intervention_class,
        )
        user_message = _measurement_user_message(target, batch)
        raw = llm_client.call(
            system_prompt,
            user_message,
            max_tokens=max_tokens,
        )
        parsed = _parse(raw) or {}
        batch_measurements = _validated_decisions(
            parsed.get("decisions"),
            target=target,
            candidates={candidate.id: candidate for candidate in batch},
        )
        batch_decided = {measurement.candidate_id for measurement in batch_measurements}
        missing = [candidate for candidate in batch if candidate.id not in batch_decided]
        if missing:
            retry = llm_client.call(
                system_prompt,
                _measurement_user_message(target, missing)
                + "\n\nA prior response omitted these candidates. Return exactly one "
                "closed relevance decision for every candidate listed above.",
                max_tokens=max_tokens,
            )
            retry_parsed = _parse(retry) or {}
            recovered = _validated_decisions(
                retry_parsed.get("decisions"),
                target=target,
                candidates={candidate.id: candidate for candidate in missing},
            )
            batch_measurements.extend(recovered)
        measurements.extend(batch_measurements)
        decided.update(measurement.candidate_id for measurement in batch_measurements)

    for candidate in numeric_candidates:
        if candidate.id in decided:
            continue
        source_record_id, source_identity_status = _source_record_identity(
            candidate.finding
        )
        unknown_evidence = {
            axis: AxisEvidence(
                relation="unknown",
                reason="No validated semantic decision was returned for this exact span.",
            )
            for axis in COMPARABILITY_AXES
        }
        measurements.append(
            Measurement(
                value=candidate.value,
                candidate_id=candidate.id,
                unit=candidate.unit,
                url=candidate.finding.url,
                insight_id=candidate.insight.id,
                source_quote=candidate.source_quote,
                source_record_id=source_record_id,
                source_identity_status=source_identity_status,
                comparability={axis: "unknown" for axis in COMPARABILITY_AXES},
                comparability_reasons={
                    axis: evidence.reason for axis, evidence in unknown_evidence.items()
                },
                axis_evidence=unknown_evidence,
                exclusion_reasons=[
                    "exact numeric source span was retained but not semantically classified"
                ],
            )
        )
    return measurements


def _validated_decisions(
    items: object,
    *,
    target: QuantitativeTarget,
    candidates: dict[str, _NumericCandidate],
) -> list[Measurement]:
    if not isinstance(items, list):
        return []
    output: list[Measurement] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_id", "")).strip()
        candidate = candidates.get(candidate_id)
        if candidate is None or candidate_id in seen:
            continue
        # Relevance is required. Missing model output must never silently
        # promote an exact numeric span into the comparator cohort.
        relevance = str(item.get("relevance", "")).strip().lower()
        relevance_reason = str(item.get("relevance_reason", "")).strip()
        if relevance not in {"relevant", "not_relevant", "unknown"}:
            continue
        evidence_form = str(item.get("evidence_form", "other")).strip().lower()
        if evidence_form not in VALID_EVIDENCE_FORMS:
            evidence_form = "other"
        phase = str(item.get("development_phase", "unknown")).strip().lower()
        if phase not in VALID_PHASES:
            phase = "unknown"
        record_type = str(item.get("source_record_type", "unknown")).strip().lower()
        if record_type not in VALID_SOURCE_RECORD_TYPES:
            record_type = "unknown"
        if relevance == "relevant":
            comparability, reasons, axis_evidence = _parse_axis_evidence(
                item.get("comparability"), target=target, candidate=candidate
            )
            exclusion_reasons: list[str] = []
        else:
            reason = relevance_reason or (
                "The exact span does not measure this target."
                if relevance == "not_relevant"
                else "The exact span is insufficient to determine target relevance."
            )
            comparability = {axis: "unknown" for axis in COMPARABILITY_AXES}
            reasons = {axis: reason for axis in COMPARABILITY_AXES}
            axis_evidence = {
                axis: AxisEvidence(relation="unknown", reason=reason)
                for axis in COMPARABILITY_AXES
            }
            exclusion_reasons = [f"candidate relevance: {relevance} — {reason}"]
        source_record_id, source_identity_status = _source_record_identity(
            candidate.finding
        )
        output.append(
            Measurement(
                value=candidate.value,
                candidate_id=candidate.id,
                unit=candidate.unit,
                evidence_form=evidence_form,
                development_phase=phase,
                source_record_type=record_type,
                url=candidate.finding.url,
                insight_id=candidate.insight.id,
                source_quote=candidate.source_quote,
                source_record_id=source_record_id,
                source_identity_status=source_identity_status,
                comparability=comparability,
                comparability_reasons=reasons,
                axis_evidence=axis_evidence,
                exclusion_reasons=exclusion_reasons,
            )
        )
        seen.add(candidate_id)
    return output


def _target_system_prompt(
    attribute: Attribute,
    indication: str,
    intervention_class: str,
    *,
    framing: str = "",
) -> str:
    framing = (
        framing.strip()
        or "Interpret each numeric statement according to the uploaded document's own role."
    ).replace("{intervention_class}", intervention_class).replace(
        "{indication}", indication
    )
    return (
        "You enumerate exact quantitative document targets for ONE variable.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\nDefinition: {attribute.description}\n"
        f"Canonical binding: {attribute.document_target or '(not stated)'}\n"
        f"Document-specific interpretation:\n{framing}\n\n"
        "Return EVERY distinct numeric target directly stated for this variable. Never collapse "
        "optimal and threshold values, different populations, different time horizons, or other "
        "operating conditions into one object. A repeated identical statement is one target. "
        "For each target return value, exact comparator (> >= < <=), source unit, a concise label "
        "that names its qualifiers, and role=threshold|optimal|other. Quote one short exact sentence "
        "or table-cell fragment containing the value, unit, direction, and qualifiers. Do not "
        "paraphrase or return an entire row. Return only blocks containing that quote. "
        "Also return required_comparison_axes once for the target. endpoint, intervention, and "
        "statistic are always required. Add population, regimen, and/or time_horizon only when "
        "the exact target constrains that qualifier. This profile is reused for every source. "
        f"{BLOCK_ID_JSON_INSTRUCTION} Deterministic code verifies every field. If no direct "
        "numeric target exists, return an empty targets list.\n\n"
        "Return ONLY JSON: "
        '{"targets":[{"value":80,"comparator":">","unit":"%",'
        '"label":"threshold >80% at 6 months","role":"threshold",'
        '"quote":"Threshold efficacy >80% at 6 months.",'
        '"required_comparison_axes":["endpoint","intervention","time_horizon","statistic"],'
        '"doc_block_ids":["document/b-0001"]}]}'
    )


def _ownership_system_prompt() -> str:
    return (
        "You assign repeated exact document targets to ONE canonical field owner. "
        "The target value, comparator, unit, quote, and block provenance are immutable. "
        "Choose only among each group's candidate attribute_ref values. Select the most "
        "specific neutral field definition that directly describes the measured quantity. "
        "Do not choose a broad product/container field when a candidate field explicitly "
        "names the quantity. Do not assign an efficacy value to a clinical-endpoint field: "
        "the endpoint field owns what is measured, while efficacy owns the numeric effect. "
        "Likewise, dose volume belongs to dose volume rather than presentation or schedule. "
        "This is ownership normalization, not evidence judgment. Return one non-empty reason "
        "for every group and do not invent another field.\n\n"
        "Return ONLY JSON: "
        '{"owners":[{"group_id":"qg-...","attribute_ref":"vaccine.efficacy",'
        '"reason":"The value directly measures protective efficacy."}]}'
    )


def _ownership_user_message(
    groups: dict[str, list[QuantitativeTarget]],
    attributes: dict[str, Attribute],
) -> str:
    lines = ["Repeated exact target groups:"]
    for group_id, targets in groups.items():
        target = targets[0]
        lines.extend(
            [
                "",
                f"[group:{group_id}] {target.role} {target.comparator} "
                f"{target.value} {target.unit}",
                f"Exact target: {target.quote}",
                "Candidate fields:",
            ]
        )
        for candidate in targets:
            attribute = attributes[candidate.attribute_ref]
            binding = " ".join(attribute.document_target.split())[:1_200]
            lines.append(
                f"- {attribute.name}: {attribute.description} | canonical binding: {binding}"
            )
    lines.append("\nReturn one canonical owner for every group now.")
    return "\n".join(lines)


def _validated_ownership_decisions(
    parsed: dict,
    groups: dict[str, list[QuantitativeTarget]],
) -> dict[str, tuple[str, str]]:
    raw = parsed.get("owners")
    if not isinstance(raw, list):
        return {}
    output: dict[str, tuple[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        group_id = str(item.get("group_id", "")).strip()
        owner = str(item.get("attribute_ref", "")).strip()
        reason = str(item.get("reason", "")).strip()
        candidates = {
            target.attribute_ref for target in groups.get(group_id, [])
        }
        if group_id in output or owner not in candidates or not reason:
            continue
        output[group_id] = (owner, reason[:500])
    return output


def _target_user_message(attribute: Attribute, doc_text: str) -> str:
    return "\n".join(
        (
            f"Variable: {attribute.name}",
            f"Definition: {attribute.description}",
            f"Canonical binding: {attribute.document_target or '(not stated)'}",
            f"Known canonical binding blocks: {', '.join(attribute.block_ids) or '(none)'}",
            "",
            "Relevant uploaded-document blocks:",
            limit_document_context(doc_text),
            "",
            "Enumerate the independent numeric targets now.",
        )
    )


def _measurement_system_prompt(
    attribute: Attribute,
    *,
    target: QuantitativeTarget,
    indication: str,
    intervention_class: str,
) -> str:
    return (
        "You classify immutable numeric source candidates for one verified document target.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}. Definition: {attribute.description}\n"
        f"Document target ID: {target.id}\n"
        f"Document target: {target.label} ({target.comparator} {target.value} {target.unit}).\n"
        f"Exact target span [{target.id}]: {target.quote}\n\n"
        "Every candidate has an immutable ID, exact value/unit, URL, and exact retained source "
        "span. Return only candidate_id; never copy or rewrite those provenance fields. Return "
        "EXACTLY ONE decision for EVERY supplied candidate; never omit one. First label relevance "
        "as relevant, not_relevant, or unknown and explain it briefly. Use not_relevant for a "
        "confidence bound, sample size, date, duration, background rate, or other number that does "
        "not measure this target. Use unknown only when the span is genuinely ambiguous. Return at "
        "most one decision-relevant point estimate per distinct source record. Do not calculate, "
        "convert units, infer missing values, use a confidence level as an outcome, or use a number "
        "merely because it appears in the passage. Label candidates that do not measure this "
        "variable not_relevant; do not omit them.\n\n"
        f"Required target comparison axes: {', '.join(target.required_comparison_axes)}. "
        "Classify endpoint, population, intervention, regimen, time_horizon, and statistic as "
        "same, compatible, not_applicable, different, or unknown, with a short reason. compatible "
        "is a defensible but non-identical comparator; different must not enter the direct cohort. "
        "Use unknown when the supplied spans do not establish a required axis. Return "
        "not_applicable for axes not listed as required; deterministic validation enforces this "
        "target-level profile for every source. For every axis, target_span_ids may contain "
        f"only {target.id}; source_span_ids may contain only that decision's candidate_id. "
        "same/compatible/different require both spans, not_applicable requires the target span, and "
        "unknown uses neither.\n\n"
        "Also label evidence_form, development_phase, and source_record_type using only:\n"
        f"evidence_form: {', '.join(sorted(VALID_EVIDENCE_FORMS))}\n"
        f"development_phase: {', '.join(sorted(VALID_PHASES))}\n"
        f"source_record_type: {', '.join(sorted(VALID_SOURCE_RECORD_TYPES))}\n\n"
        "Return ONLY JSON: "
        '{"decisions":[{"candidate_id":"qc-123","evidence_form":"randomized_trial",'
        '"relevance":"relevant","relevance_reason":"reports the target endpoint",'
        '"development_phase":"phase_3","source_record_type":"peer_reviewed",'
        '"comparability":{"endpoint":{"relation":"same","reason":"same endpoint",'
        f'"target_span_ids":["{target.id}"],"source_span_ids":["qc-123"]}},'
        '"population":{"relation":"unknown","reason":"not established",'
        '"target_span_ids":[],"source_span_ids":[]},'
        f'"intervention":{{"relation":"compatible","reason":"same class","target_span_ids":["{target.id}"],"source_span_ids":["qc-123"]}},'
        '"regimen":{"relation":"unknown","reason":"not established","target_span_ids":[],"source_span_ids":[]},'
        f'"time_horizon":{{"relation":"same","reason":"same follow-up","target_span_ids":["{target.id}"],"source_span_ids":["qc-123"]}},'
        f'"statistic":{{"relation":"same","reason":"same point estimate","target_span_ids":["{target.id}"],"source_span_ids":["qc-123"]}}}}}}]}}'
    )


def _measurement_user_message(
    target: QuantitativeTarget,
    candidates: list[_NumericCandidate],
) -> str:
    lines = [
        f"Target span [{target.id}]: {target.quote}",
        "",
        "Exact source candidates:",
    ]
    for candidate in candidates:
        finding = candidate.finding
        published = finding.published_at.isoformat() if finding.published_at else "unknown"
        lines.append(
            f"[candidate:{candidate.id}] value={candidate.value} {candidate.unit} | "
            f"url={finding.url} | lane={finding.excerpt_source_lane or finding.source} | "
            f"published={published} | title={finding.title}"
        )
        lines.append(f"    exact source span [{candidate.id}]: {candidate.source_quote}")
    lines.append("\nClassify the exact candidates now.")
    return "\n".join(lines)


def _has_source_verbatim_excerpt(finding: Finding) -> bool:
    """Web-search output is citation context, not a verbatim source passage."""
    return (finding.excerpt_source_lane or finding.source) != "web"


def _numeric_candidates(
    insights: list[Insight], unit: str
) -> list[_NumericCandidate]:
    candidates: list[_NumericCandidate] = []
    seen: set[str] = set()
    for insight in insights:
        for finding in insight.supporting_findings:
            if (
                not finding.excerpt
                or not _has_source_verbatim_excerpt(finding)
            ):
                continue
            for value, quote in _numeric_spans_for_unit(finding.excerpt, unit):
                material = "\n".join(
                    (
                        finding.url,
                        str(value),
                        _canonical_unit(unit),
                        _normalize_quote(quote),
                    )
                )
                candidate_id = "qc-" + hashlib.sha256(
                    material.encode("utf-8")
                ).hexdigest()[:16]
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                candidates.append(
                    _NumericCandidate(
                        id=candidate_id,
                        value=value,
                        unit=unit,
                        insight=insight,
                        finding=finding,
                        source_quote=quote,
                    )
                )
    return candidates


def _numeric_spans_for_unit(text: str, unit: str) -> list[tuple[float, str]]:
    """Locate values explicitly coupled to the target unit in bounded passages."""
    segments = [
        segment.strip()
        for segment in re.split(r"(?<=[!?])\s+|(?<!\d)\.\s+|\n+", text)
        if segment.strip()
    ]
    spans: list[tuple[float, str]] = []
    seen: set[tuple[float, str]] = set()
    for segment in segments:
        for value in _numeric_values_for_unit(segment, unit):
            key = (value, _normalize_quote(segment))
            if key in seen:
                continue
            seen.add(key)
            spans.append((value, segment[:1_500]))
    return spans


def _parse_axis_evidence(
    raw: object,
    *,
    target: QuantitativeTarget,
    candidate: _NumericCandidate,
) -> tuple[dict[str, str], dict[str, str], dict[str, AxisEvidence]]:
    payload = raw if isinstance(raw, dict) else {}
    relations: dict[str, str] = {}
    reasons: dict[str, str] = {}
    evidence_by_axis: dict[str, AxisEvidence] = {}
    required_axes = set(target.required_comparison_axes)
    for axis in COMPARABILITY_AXES:
        if axis not in required_axes:
            reason = "The verified document target does not constrain this axis."
            relations[axis] = "not_applicable"
            reasons[axis] = reason
            evidence_by_axis[axis] = AxisEvidence(
                relation="not_applicable",
                reason=reason,
                target_span_ids=[target.id],
                target_quotes=[target.quote],
            )
            continue
        item = payload.get(axis)
        item = item if isinstance(item, dict) else {}
        relation = str(item.get("relation", "unknown")).strip().lower()
        reason = str(item.get("reason", "")).strip()
        target_ids = _validated_span_ids(item.get("target_span_ids"), {target.id})
        source_ids = _validated_span_ids(item.get("source_span_ids"), {candidate.id})
        requires_both = relation in {"same", "compatible", "different"}
        requires_target = relation == "not_applicable"
        invalid_decision = (
            relation not in COMPARABILITY_RELATIONS
            or not reason
            or (requires_both and (not target_ids or not source_ids))
            or (requires_target and not target_ids)
            or (relation == "not_applicable" and bool(source_ids))
            or (relation == "unknown" and bool(target_ids or source_ids))
        )
        if invalid_decision:
            relation = "unknown"
            reason = (
                "Axis decision rejected because its closed label and span "
                "citations were inconsistent."
            )
            target_ids = []
            source_ids = []
        relations[axis] = relation
        reasons[axis] = reason
        evidence_by_axis[axis] = AxisEvidence(
            relation=relation,
            reason=reason,
            target_span_ids=target_ids,
            source_span_ids=source_ids,
            target_quotes=[target.quote] if target_ids else [],
            source_quotes=[candidate.source_quote] if source_ids else [],
        )
    return relations, reasons, evidence_by_axis


def _validated_span_ids(raw: object, allowed: set[str]) -> list[str]:
    if not isinstance(raw, list):
        return []
    return list(
        dict.fromkeys(
            item.strip()
            for item in raw
            if isinstance(item, str) and item.strip() in allowed
        )
    )


def _validated_required_axes(
    raw: object,
    *,
    required: bool,
) -> list[str] | None:
    """Validate the target-level comparability profile as one closed contract."""
    if raw is None and not required:
        return list(COMPARABILITY_AXES)
    if not isinstance(raw, list):
        return None
    axes = list(
        dict.fromkeys(
            item.strip()
            for item in raw
            if isinstance(item, str) and item.strip()
        )
    )
    if (
        not axes
        or set(axes) - set(COMPARABILITY_AXES)
        or not MANDATORY_QUANTITATIVE_AXES.issubset(axes)
    ):
        return None
    return [axis for axis in COMPARABILITY_AXES if axis in axes]


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _normalize_quote(value: str) -> str:
    return " ".join(html.unescape(value).split()).casefold()


def _quote_in_text(quote: str, source_text: str) -> bool:
    normalized_quote = _normalize_quote(quote)
    return bool(normalized_quote) and normalized_quote in _normalize_quote(source_text)


_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.·]\d+)?(?:[eE][-+]?\d+)?"
)


def _looks_directional_numeric(text: str) -> bool:
    if not text or not _NUMBER_RE.search(text):
        return False
    folded = _normalize_quote(text)
    return any(
        marker in folded
        for marker in (
            ">",
            "<",
            "≥",
            "≤",
            "at least",
            "at most",
            "minimum",
            "maximum",
            "no more than",
            "not less than",
            "threshold",
            "by ",
        )
    )


def _value_unit_supported(value: float, unit: str, quote: str) -> bool:
    """Require the selected number to be grammatically coupled to its unit."""
    return any(
        math.isclose(candidate, value, rel_tol=1e-9, abs_tol=1e-9)
        for candidate in _numeric_values_for_unit(quote, unit)
    )


def _target_supported_by_binding(
    value: float,
    comparator: str,
    unit: str,
    binding: str,
) -> bool:
    """Require the canonical field binding itself to own the numeric target.

    Exact source blocks prove that a number exists in the document. This check
    separately proves that the resolved field owns it. Failing closed may omit
    an incompletely bound target, but it prevents a neighboring field from
    donating one.
    """
    return (
        bool(binding)
        and _value_unit_supported(value, unit, binding)
        and _comparator_supported(comparator, binding)
    )


def _numeric_values_for_unit(text: str, unit: str) -> list[float]:
    canonical = _canonical_unit(unit)
    number = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.·]\d+)?(?:[eE][-+]?\d+)?"
    patterns: list[str]
    if canonical == "%":
        patterns = [rf"(?P<value>{number})\s*(?:%|percent(?:age)?\b|pct\b)"]
    elif canonical == "usd":
        patterns = [
            rf"(?:US\s*)?\$\s*(?P<value>{number})",
            rf"\bUSD\s*(?P<value>{number})",
            rf"(?P<value>{number})\s*(?:USD\b|US\s+dollars?\b)",
        ]
    elif canonical in {"hour", "hours"}:
        patterns = [rf"(?P<value>{number})\s*(?:hours?|hrs?)\b"]
    elif canonical in {"month", "months"}:
        patterns = [rf"(?P<value>{number})\s*(?:months?|mos?)\b"]
    elif canonical in {"year", "years"}:
        patterns = [rf"(?P<value>{number})\s*(?:years?|yrs?)\b"]
    elif canonical == "ml/dose":
        patterns = [
            rf"(?P<value>{number})\s*mL(?:\s*/\s*dose|\s+per\s+dose)?\b"
        ]
    elif canonical == "x/year":
        patterns = [
            rf"(?P<value>{number})\s*(?:times?|doses?|administrations?|boosters?)\s+per\s+year\b",
            rf"(?P<value>{number})\s*(?:x\s*/\s*year)\b",
        ]
    else:
        escaped = re.escape(unit.strip())
        patterns = [rf"(?P<value>{number})\s*{escaped}(?![A-Za-z0-9])"]

    values: list[float] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = float(
                    match.group("value").replace(",", "").replace("·", ".")
                )
            except (ValueError, IndexError):
                continue
            if not any(
                math.isclose(existing, value, rel_tol=1e-9, abs_tol=1e-9)
                for existing in values
            ):
                values.append(value)
    return values


def _comparator_supported(comparator: str, quote: str) -> bool:
    folded = _normalize_quote(quote)
    if comparator == ">":
        return bool(re.search(r"(?<![<>=])>(?!=)", folded)) or any(
            phrase in folded for phrase in ("greater than", "more than", "exceeds")
        )
    if comparator == "<":
        return bool(re.search(r"(?<![<>=])<(?!=)", folded)) or any(
            phrase in folded for phrase in ("less than", "below")
        )
    phrases = {
        ">=": (
            ">=", "≥", "at least", "minimum", "min.", "not less than",
            "no lower than", "or greater", "or more",
        ),
        "<=": (
            "<=", "≤", "at most", "maximum", "max.", "no more than",
            "not greater than", "up to", "or less",
        ),
    }
    return any(phrase in folded for phrase in phrases[comparator])


def _text_for_blocks(document_text: str, block_ids: list[str]) -> str:
    wanted = set(block_ids)
    matches = list(re.finditer(r"\[block:([^\]]+)\][^\n]*\n", document_text))
    selected: list[str] = []
    for index, match in enumerate(matches):
        if match.group(1) not in wanted:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(document_text)
        selected.append(document_text[match.end():end])
    return "\n".join(selected)


def _source_record_identity(finding: Finding) -> tuple[str, str]:
    record_ids = sorted(
        {
            f"{record.record_type}:{record.record_id.strip().casefold()}"
            for record in finding.development_records
            if record.record_id.strip()
        }
    )
    if record_ids:
        return record_ids[0], "canonical"

    split = urlsplit(finding.url)
    host = split.netloc.casefold().removeprefix("www.")
    path = split.path.rstrip("/")
    doi_match = re.search(r"(?:^|/)10\.\d{4,9}/[^?#]+", path, re.IGNORECASE)
    if host == "doi.org" and doi_match:
        return f"doi:{doi_match.group(0).lstrip('/').casefold()}", "canonical"
    for pattern, prefix in (
        (r"\bNCT\d{8}\b", "nct"),
        (r"\bISRCTN\d+\b", "isrctn"),
        (r"\bEUCTR\d+(?:-\d+)*\b", "euctr"),
    ):
        if match := re.search(pattern, f"{finding.url} {finding.title}", re.IGNORECASE):
            return f"{prefix}:{match.group(0).casefold()}", "canonical"

    normalized_title = re.sub(r"[^a-z0-9]+", " ", finding.title.casefold()).strip()
    if len(normalized_title) >= 12 and normalized_title not in {"study details", "untitled"}:
        digest = hashlib.sha256(normalized_title.encode("utf-8")).hexdigest()[:20]
        return f"title:{digest}", "title_fallback"

    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
        )
    )
    normalized_url = urlunsplit((split.scheme.casefold(), host, path, query, ""))
    digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:20]
    return f"url:{digest}", "url_fallback"


def _parse(raw: str) -> dict | None:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_object(text))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _canonical_unit(unit: str) -> str:
    """Normalize spelling only; never perform dimensional conversion."""
    normalized = re.sub(r"[\s._-]+", "", unit.strip().lower())
    aliases = {
        "percent": "%",
        "percentage": "%",
        "pct": "%",
        "us$": "usd",
        "$": "usd",
    }
    return aliases.get(normalized, normalized)


def _strip_fences(s: str) -> str:
    m = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", s, re.DOTALL)
    return m.group(1) if m else s


def _extract_json_object(s: str) -> str:
    decoder = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(s[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return s[i : i + end]
    return s
