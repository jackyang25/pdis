"""Stage: traceable quantitative calibration for ONE document claim.

A transparent, reproducible complement to the qualitative `evidence_assessor`.
Where sources report comparable numbers against a doc-stated target (e.g.
efficacy >= 80%), this:

  1. (LLM) normalizes the meaning of exact document/source spans into one
     typed semantic contract with honest unknown/other states.
  2. (code) verifies quotes, values, units, URLs, document blocks, enums, and
     source identities; then admits only atomic comparable measurements.
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
    Attribute,
    ConformityScore,
    DocumentSpan,
    Insight,
    LLMClientProtocol,
    MEASUREMENT_KINDS,
    MEASUREMENT_STATUSES,
    Measurement,
    NumericExpression,
    QUANTITATIVE_SEMANTIC_FIELDS,
    SEMANTIC_SLOT_STATES,
    QuantitativeTarget,
    SemanticSlot,
    SourcePassageDisposition,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
OWNERSHIP_MAX_TOKENS = 8000
SOURCE_BATCH_SIZE = 3
MAX_SOURCE_PASSAGE_CHARS = 8_000
MAX_TARGET_QUOTE_CHARS = 800
# Keep in lockstep with drift_classifier / evidence_assessor so all three
# doc-reading stages see the SAME baseline and a target near the end of a long
# doc is never cut off in one stage but not another.

_METHODOLOGY_PATH = Path(__file__).resolve().parents[1] / "configs" / "evidence_methodology.yaml"
with _METHODOLOGY_PATH.open("r", encoding="utf-8") as _methodology_file:
    _METHODOLOGY = yaml.safe_load(_methodology_file) or {}

CALIBRATION_LIMITED_MIN_COUNT = int(
    _METHODOLOGY["calibration_limited_min_count"]
)

CALIBRATION_SUFFICIENT_MIN_COUNT = int(
    _METHODOLOGY["calibration_sufficient_min_count"]
)
VALID_TARGET_ROLES = frozenset({"threshold", "optimal", "other"})


@dataclass(frozen=True)
class _SourcePassage:
    id: str
    insight: Insight
    finding: Finding
    text: str


@dataclass(frozen=True)
class QuantitativeTargetExtraction:
    """One explicit target-detection outcome for a canonical field."""

    status: str
    reason: str
    targets: list[QuantitativeTarget]


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
        candidates, dispositions = _extract_target_measurements(
            attribute,
            target,
            insights,
            llm_client,
            indication=indication,
            intervention_class=intervention_class,
            max_tokens=max_tokens,
        )
        measurements, excluded_measurements = _partition_cohort(candidates, target)
        if not measurements:
            scores.append(_empty_score(target, excluded_measurements, dispositions))
            continue
        _attach_dates(measurements, insights)
        scores.append(
            _combine(
                target,
                measurements,
                excluded_measurements,
                dispositions,
            )
        )
    return scores


def empty_conformity_scores(
    attributes: list[Attribute],
) -> list[ConformityScore]:
    """Project verified targets when retrieval yields no numeric evidence."""
    return [
        _empty_score(target, [], [])
        for attribute in attributes
        for target in attribute.quantitative_targets
    ]


def _empty_score(
    target: QuantitativeTarget,
    excluded_measurements: list[Measurement],
    source_dispositions: list[SourcePassageDisposition],
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
        source_dispositions=source_dispositions,
    )


def _partition_cohort(
    candidates: list[Measurement],
    target: QuantitativeTarget,
) -> tuple[list[Measurement], list[Measurement]]:
    """Apply the small deterministic admission contract.

    AI owns semantic conversion into one central status. Code admits only an
    scalar expression with a comparable meaning and a unique source record.
    It never tries to reconstruct clinical meaning from scattered axis labels.
    """
    included: list[Measurement] = []
    excluded: list[Measurement] = []
    eligible_by_record: dict[str, list[Measurement]] = {}
    for candidate in candidates:
        reasons = list(candidate.exclusion_reasons)
        if candidate.semantic_status != "comparable":
            reasons.append(
                f"semantic status: {candidate.semantic_status}"
                + (f" — {candidate.semantic_reason}" if candidate.semantic_reason else "")
            )
        if candidate.expression_kind not in {"point_estimate", "count", "rate"}:
            reasons.append(
                f"numeric expression is {candidate.expression_kind}, not an atomic scalar"
            )
        if _canonical_unit(candidate.unit) != _canonical_unit(target.unit):
            reasons.append("numeric unit is incompatible with the document target")
        if reasons:
            candidate.exclusion_reasons = reasons
            excluded.append(candidate)
            continue
        eligible_by_record.setdefault(candidate.source_record_id, []).append(candidate)

    for record_id, record_candidates in eligible_by_record.items():
        unique_values = {candidate.value for candidate in record_candidates}
        if len(unique_values) > 1:
            for candidate in record_candidates:
                candidate.exclusion_reasons = [
                    "multiple semantically comparable scalar values from source record "
                    f"{record_id}; no primary estimate was deterministically identifiable"
                ]
                excluded.append(candidate)
            continue
        selected, *duplicates = record_candidates
        selected.inclusion_reason = (
            "AI normalized this exact source measurement as semantically comparable; "
            "the exact quote/value/unit passed deterministic validation and the source "
            f"was deduplicated as {record_id}."
        )
        included.append(selected)
        for duplicate in duplicates:
            duplicate.exclusion_reasons = [f"duplicate source record and value: {record_id}"]
            excluded.append(duplicate)
    return included, excluded


# ---------------------------------------------------------------------------
# Combination math (pure, deterministic)
# ---------------------------------------------------------------------------


def _combine(
    target: QuantitativeTarget,
    measurements: list[Measurement],
    excluded_measurements: list[Measurement],
    source_dispositions: list[SourcePassageDisposition],
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
        source_dispositions=source_dispositions,
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
    """Compatibility wrapper for consumers that only need validated targets."""
    return extract_quantitative_target_set(
        attribute,
        doc_text,
        llm_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
        images=images,
        max_tokens=max_tokens,
    ).targets


def extract_quantitative_target_set(
    attribute: Attribute,
    doc_text: str,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> QuantitativeTargetExtraction:
    attempts = 2 if _looks_directional_numeric(attribute.document_target) else 1
    last_status = "uncertain"
    last_reason = "The quantitative target mapping did not return a valid decision."
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
        status = str(parsed.get("status", "uncertain")).strip().lower()
        reason = " ".join(str(parsed.get("status_reason", "")).split())
        if status not in {"present", "not_applicable", "uncertain"}:
            status = "uncertain"
        last_status = status
        last_reason = reason or {
            "present": "The document states at least one directional numeric target.",
            "not_applicable": "The canonical field does not state a directional numeric target.",
            "uncertain": "The document wording was insufficient to resolve a numeric target.",
        }[status]
        targets = _validated_targets(
            parsed.get("targets"),
            attribute=attribute,
            doc_text=doc_text,
        )
        if targets:
            return QuantitativeTargetExtraction("present", last_reason, targets)
        if status != "present" and attempts == 1:
            return QuantitativeTargetExtraction(status, last_reason, [])
    if last_status == "present":
        last_reason = (
            "A numeric target was proposed, but its exact value, direction, unit, "
            "or document provenance did not pass deterministic validation."
        )
    return QuantitativeTargetExtraction("uncertain", last_reason, [])


def resolve_quantitative_target_ownership(
    attributes: list[Attribute],
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int = OWNERSHIP_MAX_TOKENS,
) -> list[Attribute]:
    """Assign one semantic target to one owner and merge all exact provenance.

    Semantic identity deliberately excludes quote and block location. Repeated
    statements therefore become one target with multiple provenance spans,
    instead of duplicate ledgers. Cross-field ambiguity is resolved only among
    fields that independently emitted the same atomic semantic target.
    """
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    groups: dict[tuple[object, ...], list[QuantitativeTarget]] = {}
    for attribute in attributes:
        for target in attribute.quantitative_targets:
            groups.setdefault(_semantic_target_key(target, include_owner=False), []).append(target)

    ambiguous: dict[str, list[QuantitativeTarget]] = {}
    owner_by_group: dict[str, tuple[str, str]] = {}
    group_ids: dict[tuple[object, ...], str] = {}
    for key, targets in groups.items():
        material = json.dumps(key, sort_keys=True, ensure_ascii=False)
        group_id = "qg-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        group_ids[key] = group_id
        candidate_refs = list(dict.fromkeys(target.attribute_ref for target in targets))
        if len(candidate_refs) == 1:
            owner_by_group[group_id] = (
                candidate_refs[0],
                "Only this canonical field emitted the semantic target.",
            )
        else:
            ambiguous[group_id] = targets

    if ambiguous:
        system_prompt = _ownership_system_prompt()
        user_message = _ownership_user_message(ambiguous, attributes_by_name)
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
            owner_by_group.update(_validated_ownership_decisions(parsed, ambiguous))
            if set(ambiguous).issubset(owner_by_group):
                break

    owned: dict[str, list[QuantitativeTarget]] = {name: [] for name in attributes_by_name}
    for key, targets in groups.items():
        group_id = group_ids[key]
        decision = owner_by_group.get(group_id)
        if decision is None:
            logger.warning(
                "quantitative target ownership unresolved for %s; omitting target",
                group_id,
            )
            continue
        owner, reason = decision
        selected = next(target for target in targets if target.attribute_ref == owner)
        spans: list[DocumentSpan] = []
        seen_spans: set[tuple[str, tuple[str, ...]]] = set()
        for target in targets:
            for span in target.provenance_spans:
                span_key = (_normalize_quote(span.quote), tuple(span.block_ids))
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)
                spans.append(span)
        merged = replace(
            selected,
            provenance_spans=spans,
            doc_block_ids=list(
                dict.fromkeys(block_id for span in spans for block_id in span.block_ids)
            ),
            quote=spans[0].quote,
            ownership_reason=reason,
            id="",
        )
        owned[owner].append(merged)

    return [
        replace(attribute, quantitative_targets=owned[attribute.name])
        for attribute in attributes
    ]


def _validated_targets(
    items: object,
    *,
    attribute: Attribute,
    doc_text: str,
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
    targets_by_id: dict[str, QuantitativeTarget] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        expression = _validated_numeric_expression(item.get("expression"))
        role = str(item.get("role", "other")).strip().lower()
        quote = str(item.get("quote", "")).strip()
        semantic_profile = _validated_semantic_profile(item.get("semantic_profile"))
        ownership_reason = str(item.get("ownership_reason", "")).strip()
        other_constraints = _string_list(item.get("other_constraints"))
        if (
            expression is None
            or expression.kind != "bound"
            or role not in VALID_TARGET_ROLES
            or semantic_profile is None
        ):
            continue
        assert expression.value is not None
        value = expression.value
        comparator = expression.comparator
        unit = expression.unit
        raw_spans = item.get("provenance_spans")
        if not isinstance(raw_spans, list) or not raw_spans:
            raw_spans = [{"quote": quote, "block_ids": item.get("doc_block_ids")}]
        spans: list[DocumentSpan] = []
        seen_spans: set[tuple[str, tuple[str, ...]]] = set()
        for raw_span in raw_spans:
            if not isinstance(raw_span, dict):
                continue
            span_quote = str(raw_span.get("quote", "")).strip()
            span_ids = validated_block_ids(raw_span.get("block_ids"), allowed_ids)
            span_text = _text_for_blocks(doc_text, span_ids)
            span_key = (_normalize_quote(span_quote), tuple(span_ids))
            if (
                span_key in seen_spans
                or not span_ids
                or not span_quote
                or len(span_quote) > MAX_TARGET_QUOTE_CHARS
                or not _quote_in_text(span_quote, span_text)
                or not _value_unit_supported(float(value), unit, span_quote)
                or not _comparator_supported(comparator, span_quote)
            ):
                continue
            seen_spans.add(span_key)
            spans.append(DocumentSpan(quote=span_quote, block_ids=span_ids))
        if (
            not spans
            or not _target_supported_by_binding(
                float(value), comparator, unit, attribute.document_target
            )
        ):
            continue
        target = QuantitativeTarget(
            attribute_ref=attribute.name,
            expression=expression,
            role=role,
            quote=spans[0].quote,
            doc_block_ids=list(
                dict.fromkeys(block_id for span in spans for block_id in span.block_ids)
            ),
            semantic_profile=semantic_profile,
            provenance_spans=spans,
            ownership_reason=ownership_reason,
            other_constraints=other_constraints,
        )
        existing = targets_by_id.get(target.id)
        if existing is None:
            targets_by_id[target.id] = target
            continue
        merged_spans = list(existing.provenance_spans)
        existing_keys = {
            (_normalize_quote(span.quote), tuple(span.block_ids)) for span in merged_spans
        }
        merged_spans.extend(
            span
            for span in target.provenance_spans
            if (_normalize_quote(span.quote), tuple(span.block_ids)) not in existing_keys
        )
        targets_by_id[target.id] = replace(
            existing,
            provenance_spans=merged_spans,
            id=existing.id,
        )
    return list(targets_by_id.values())


def _extract_target_measurements(
    attribute: Attribute,
    target: QuantitativeTarget,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int,
) -> tuple[list[Measurement], list[SourcePassageDisposition]]:
    """Map bounded source-owned passages directly into complete measurements."""
    passages = _source_passages(insights)
    measurements: list[Measurement] = []
    dispositions: list[SourcePassageDisposition] = []
    decided: set[str] = set()
    for start in range(0, len(passages), SOURCE_BATCH_SIZE):
        batch = passages[start : start + SOURCE_BATCH_SIZE]
        system_prompt = _measurement_system_prompt(
            attribute,
            target=target,
            indication=indication,
            intervention_class=intervention_class,
        )
        user_message = _measurement_user_message(batch)
        raw = llm_client.call(
            system_prompt,
            user_message,
            max_tokens=max_tokens,
        )
        parsed = _parse(raw) or {}
        batch_measurements, batch_dispositions = _validated_source_decisions(
            parsed.get("sources"),
            passages={passage.id: passage for passage in batch},
        )
        batch_decided = {item.source_id for item in batch_dispositions}
        missing = [passage for passage in batch if passage.id not in batch_decided]
        if missing:
            retry = llm_client.call(
                system_prompt,
                _measurement_user_message(missing)
                + "\n\nA prior response omitted or malformed these source decisions. "
                "Return exactly one complete decision for every source ID above.",
                max_tokens=max_tokens,
            )
            retry_parsed = _parse(retry) or {}
            recovered_measurements, recovered_dispositions = _validated_source_decisions(
                retry_parsed.get("sources"),
                passages={passage.id: passage for passage in missing},
            )
            batch_measurements.extend(recovered_measurements)
            batch_dispositions.extend(recovered_dispositions)
        measurements.extend(batch_measurements)
        dispositions.extend(batch_dispositions)
        decided.update(item.source_id for item in batch_dispositions)

    for passage in passages:
        if passage.id in decided:
            continue
        dispositions.append(
            SourcePassageDisposition(
                source_id=passage.id,
                status="uncertain",
                reason="No complete validated semantic decision was returned for this passage.",
                url=passage.finding.url,
                insight_id=passage.insight.id,
            )
        )
    return measurements, dispositions


def _validated_source_decisions(
    items: object,
    *,
    passages: dict[str, _SourcePassage],
) -> tuple[list[Measurement], list[SourcePassageDisposition]]:
    if not isinstance(items, list):
        return [], []
    output: list[Measurement] = []
    dispositions: list[SourcePassageDisposition] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", "")).strip()
        passage = passages.get(source_id)
        if passage is None or source_id in seen:
            continue
        status = str(item.get("status", "")).strip().lower()
        reason = " ".join(str(item.get("reason", "")).split())
        if status not in {
            "measurements_found",
            "no_relevant_measurement",
            "uncertain",
        } or not reason:
            continue
        raw_measurements = item.get("measurements")
        if status == "measurements_found" and not isinstance(raw_measurements, list):
            continue
        validated: list[Measurement] = []
        for raw_measurement in raw_measurements if isinstance(raw_measurements, list) else []:
            measurement = _validated_passage_measurement(
                raw_measurement,
                passage=passage,
            )
            if measurement is not None:
                validated.append(measurement)
        if isinstance(raw_measurements, list) and len(validated) != len(raw_measurements):
            # Never silently keep only the convenient subset of a model
            # decision. Retry the whole source or preserve it as uncertain.
            continue
        if status == "measurements_found" and not validated:
            continue
        if status != "measurements_found" and validated:
            continue
        output.extend(validated)
        dispositions.append(
            SourcePassageDisposition(
                source_id=source_id,
                status=status,
                reason=reason[:500],
                url=passage.finding.url,
                insight_id=passage.insight.id,
            )
        )
        seen.add(source_id)
    return output, dispositions


def _validated_passage_measurement(
    raw: object,
    *,
    passage: _SourcePassage,
) -> Measurement | None:
    if not isinstance(raw, dict):
        return None
    quote = " ".join(str(raw.get("quote", "")).split())
    expression = _validated_numeric_expression(raw.get("expression"))
    semantic_status = str(raw.get("semantic_status", "")).strip().lower()
    semantic_reason = " ".join(str(raw.get("semantic_reason", "")).split())
    semantic_profile = _validated_semantic_profile(raw.get("semantic_profile"))
    if (
        not quote
        or not _quote_in_text(quote, passage.text)
        or expression is None
        or not _expression_supported(expression, quote)
        or semantic_status not in MEASUREMENT_STATUSES
        or not semantic_reason
        or semantic_profile is None
    ):
        return None
    material = json.dumps(
        {
            "source_id": passage.id,
            "quote": _normalize_quote(quote),
            "expression": {
                "kind": expression.kind,
                "unit": _canonical_unit(expression.unit),
                "value": expression.value,
                "lower": expression.lower,
                "upper": expression.upper,
                "comparator": expression.comparator,
            },
        },
        sort_keys=True,
    )
    candidate_id = "qm-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    source_record_id, source_identity_status = _source_record_identity(passage.finding)
    return Measurement(
        expression=expression,
        candidate_id=candidate_id,
        url=passage.finding.url,
        insight_id=passage.insight.id,
        source_quote=quote,
        source_record_id=source_record_id,
        source_identity_status=source_identity_status,
        semantic_status=semantic_status,
        semantic_reason=semantic_reason,
        semantic_profile=semantic_profile,
    )


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
        "You normalize exact quantitative document targets for ONE variable into atomic "
        "semantic records.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\nDefinition: {attribute.description}\n"
        f"Canonical binding: {attribute.document_target or '(not stated)'}\n"
        f"Document-specific interpretation:\n{framing}\n\n"
        "Return EVERY distinct directional numeric target directly stated for this variable. "
        "Split compound cells into atomic targets: adult and pediatric values, optimal and "
        "threshold values, and different time horizons are separate objects. A repeated semantic "
        "target is one object even when the document states it in multiple places; include every "
        "exact occurrence in provenance_spans. "
        "For each target return expression={kind:bound,value,comparator,unit} and "
        "role=threshold|optimal|other. In each provenance_span, "
        "quote the shortest exact fragment that uniquely supports this ONE value and its "
        "qualifiers; never return a whole compound row when a shorter fragment is available. "
        "Normalize meaning into semantic_profile with exactly these fields: measure, endpoint, "
        "intervention, population, regimen, time_horizon, statistic. Each field is an object with "
        "state=specified|not_specified|unknown|other, value, and other. specified requires a concise "
        "value; other requires an explanation in other; absent qualifiers are not_specified; use "
        "unknown only when the document is ambiguous. measure must be specified. Put any meaningful "
        "constraint outside those fields in other_constraints; otherwise return an empty list. "
        f"{BLOCK_ID_JSON_INSTRUCTION} Deterministic code verifies every field. Also return "
        "status=present|not_applicable|uncertain and a concise status_reason. Use not_applicable "
        "only when the field clearly has no directional numeric target; use uncertain when the "
        "wording may contain one but cannot be mapped faithfully. If no validated direct numeric "
        "target exists, return an empty targets list.\n\n"
        "Return ONLY JSON: "
        '{"status":"present","status_reason":"The field states an efficacy threshold.",'
        '"targets":[{"expression":{"kind":"bound","value":80,'
        '"comparator":">","unit":"%"},"role":"threshold",'
        '"semantic_profile":{"measure":{"state":"specified","value":"protective efficacy","other":""},'
        '"endpoint":{"state":"specified","value":"clinical malaria","other":""},'
        '"intervention":{"state":"specified","value":"malaria vaccine","other":""},'
        '"population":{"state":"not_specified","value":"","other":""},'
        '"regimen":{"state":"not_specified","value":"","other":""},'
        '"time_horizon":{"state":"specified","value":"6 months after primary series","other":""},'
        '"statistic":{"state":"specified","value":"efficacy point estimate","other":""}},'
        '"other_constraints":[],"provenance_spans":['
        '{"quote":"Threshold efficacy >80% at 6 months.",'
        '"block_ids":["document/b-0001"]}]}]}'
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


def _semantic_profile_json(profile: dict[str, SemanticSlot]) -> str:
    return json.dumps(
        {
            name: {
                "state": slot.state,
                "value": slot.value,
                "other": slot.other,
            }
            for name, slot in profile.items()
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _validated_semantic_profile(raw: object) -> dict[str, SemanticSlot] | None:
    if not isinstance(raw, dict) or set(raw) != set(QUANTITATIVE_SEMANTIC_FIELDS):
        return None
    profile: dict[str, SemanticSlot] = {}
    try:
        for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
            item = raw.get(field_name)
            if not isinstance(item, dict):
                return None
            state = str(item.get("state", "")).strip().lower()
            if state not in SEMANTIC_SLOT_STATES:
                return None
            profile[field_name] = SemanticSlot(
                state=state,
                value=str(item.get("value", "")),
                other=str(item.get("other", "")),
            )
    except ValueError:
        return None
    if profile["measure"].state != "specified":
        return None
    return profile


def _validated_numeric_expression(raw: object) -> NumericExpression | None:
    """Validate the one syntax-only numeric contract returned by the model."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind", "")).strip().lower()
    unit = str(raw.get("unit", "")).strip()
    if kind not in MEASUREMENT_KINDS:
        return None
    if kind not in {"other", "unknown"} and not unit:
        return None
    try:
        return NumericExpression(
            kind=kind,
            unit=unit,
            value=raw.get("value"),
            lower=raw.get("lower"),
            upper=raw.get("upper"),
            comparator=str(raw.get("comparator", "")),
        )
    except (TypeError, ValueError):
        return None


def _expression_supported(expression: NumericExpression, quote: str) -> bool:
    """Require every structured number and operator to appear in its exact quote."""
    if expression.kind in {"point_estimate", "count", "rate"}:
        return (
            expression.value is not None
            and _value_unit_supported(expression.value, expression.unit, quote)
        )
    if expression.kind == "bound":
        return (
            expression.value is not None
            and _value_unit_supported(expression.value, expression.unit, quote)
            and _comparator_supported(expression.comparator, quote)
        )
    if expression.kind in {"range", "confidence_interval"}:
        return (
            expression.lower is not None
            and expression.upper is not None
            and _number_supported(expression.lower, quote)
            and _number_supported(expression.upper, quote)
            and (
                _value_unit_supported(expression.lower, expression.unit, quote)
                or _value_unit_supported(expression.upper, expression.unit, quote)
            )
        )
    return bool(_NUMBER_RE.search(quote))


def _semantic_target_key(
    target: QuantitativeTarget,
    *,
    include_owner: bool,
) -> tuple[object, ...]:
    profile = tuple(
        (
            field_name,
            slot.state,
            slot.value.casefold(),
            slot.other.casefold(),
        )
        for field_name, slot in target.semantic_profile.items()
    )
    return (
        *((target.attribute_ref,) if include_owner else ()),
        target.role,
        target.comparator,
        target.value,
        _canonical_unit(target.unit),
        profile,
        tuple(sorted(item.casefold() for item in target.other_constraints)),
    )


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return list(
        dict.fromkeys(
            " ".join(str(item).split())
            for item in raw
            if " ".join(str(item).split())
        )
    )


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
        "You extract complete numeric measurements from bounded, source-owned passages "
        "against one atomic semantic target.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}. Definition: {attribute.description}\n"
        f"Document target ID: {target.id}\n"
        "The target's numeric threshold is intentionally withheld: whether a source value passes "
        "the target must NEVER affect semantic comparability.\n"
        f"Target unit: {target.unit}. Target role: {target.role}.\n"
        f"Target semantic profile: {_semantic_profile_json(target.semantic_profile)}\n"
        f"Other target constraints: {json.dumps(target.other_constraints, ensure_ascii=False)}\n\n"
        "Each source has an immutable ID and one retained source passage. Return EXACTLY ONE "
        "source decision for EVERY ID: measurements_found, no_relevant_measurement, or uncertain. "
        "Do not enumerate every number. Extract only complete statements that measure the target "
        "or a meaningfully related quantity. Each extracted measurement must contain the shortest "
        "self-contained exact quote that explicitly connects the number to the measured outcome "
        "or property and preserves its qualifiers, plus one expression object. A dose, exposure "
        "condition, storage temperature, visit time, follow-up duration, or sample size alone is "
        "NOT an outcome measurement. For example, 'stored for 6 weeks at 60 C' is not evidence of "
        "thermostability unless the same contiguous quote also states what stability, potency, or "
        "performance was retained. Do not import that missing meaning from a title, an Insight, or "
        "your background knowledge. If the retained passage cannot supply one self-contained exact "
        "span, return uncertain rather than a measurement. "
        "Expression kind is point_estimate|range|bound|confidence_interval|count|rate|other|unknown. "
        "point_estimate/count/rate use value; range/confidence_interval use lower+upper; bound uses "
        "value+comparator. Never split a range or confidence interval into point estimates. "
        "Then return one central "
        "semantic_status: comparable when it is an atomic measurement of the same target meaning; "
        "contextual when related but unsuitable for the direct cohort; incompatible when it clearly "
        "measures something else; unknown when context is insufficient. The magnitude of the number "
        "and whether it would meet the hidden target are NEVER relevance criteria. Normalize the "
        "source meaning into semantic_profile using the same seven fields and slot states as the "
        "target. Do not infer a qualifier absent from the supplied source context.\n\n"
        "Use no_relevant_measurement when the passage contains no relevant complete numeric "
        "statement. Use uncertain when one may exist but the supplied passage cannot support a "
        "faithful mapping. Never infer omitted context.\n\n"
        "Return ONLY JSON: "
        '{"sources":[{"source_id":"sp-123","status":"measurements_found",'
        '"reason":"The passage reports a target-relevant efficacy estimate.","measurements":['
        '{"quote":"Vaccine efficacy was 50.3% at 12 months.",'
        '"expression":{"kind":"point_estimate","unit":"%","value":50.3,'
        '"lower":null,"upper":null,"comparator":""},'
        '"semantic_status":"comparable",'
        '"semantic_reason":"reports the same measure and target qualifiers",'
        '"semantic_profile":{"measure":{"state":"specified","value":"protective efficacy","other":""},'
        '"endpoint":{"state":"specified","value":"clinical malaria","other":""},'
        '"intervention":{"state":"specified","value":"malaria vaccine","other":""},'
        '"population":{"state":"specified","value":"children","other":""},'
        '"regimen":{"state":"unknown","value":"","other":""},'
        '"time_horizon":{"state":"specified","value":"12 months","other":""},'
        '"statistic":{"state":"specified","value":"efficacy point estimate","other":""}}}]}]}'
    )


def _measurement_user_message(passages: list[_SourcePassage]) -> str:
    lines = ["Bounded source passages:"]
    for passage in passages:
        finding = passage.finding
        published = finding.published_at.isoformat() if finding.published_at else "unknown"
        lines.append(
            f"[source:{passage.id}] "
            f"url={finding.url} | lane={finding.excerpt_source_lane or finding.source} | "
            f"published={published} | title={finding.title}"
        )
        lines.append(f"    passage: {passage.text}")
    lines.append("\nReturn one complete decision for every source passage now.")
    return "\n".join(lines)


def _has_source_verbatim_excerpt(finding: Finding) -> bool:
    """Web-search output is citation context, not a verbatim source passage."""
    return (finding.excerpt_source_lane or finding.source) != "web"


def _source_passages(insights: list[Insight]) -> list[_SourcePassage]:
    """Deduplicate source-owned passages before any semantic extraction."""
    passages: list[_SourcePassage] = []
    seen: set[str] = set()
    for insight in insights:
        for finding in insight.supporting_findings:
            if (
                not finding.excerpt
                or not _has_source_verbatim_excerpt(finding)
            ):
                continue
            text = finding.excerpt[:MAX_SOURCE_PASSAGE_CHARS]
            material = "\n".join((finding.url, _normalize_quote(text)))
            source_id = "sp-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
            if source_id in seen:
                continue
            seen.add(source_id)
            passages.append(
                _SourcePassage(
                    id=source_id,
                    insight=insight,
                    finding=finding,
                    text=text,
                )
            )
    return passages


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


def _number_supported(value: float, quote: str) -> bool:
    """Verify a number literally appears, independent of shared range-unit syntax."""
    for match in _NUMBER_RE.finditer(quote):
        try:
            candidate = float(match.group(0).replace(",", "").replace("·", "."))
        except ValueError:
            continue
        if math.isclose(candidate, value, rel_tol=1e-9, abs_tol=1e-9):
            return True
    return False


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
    # A hyphen between digits is a range separator, never a unary minus. Keep
    # both endpoints for traceability; the semantic normalizer classifies the
    # expression as ``range`` so neither enters point-estimate statistics.
    text = re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", " to ", text)
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
