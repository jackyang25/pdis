"""Stage: traceable quantitative calibration for ONE document claim.

A transparent, reproducible complement to the qualitative `evidence_assessor`.
Where sources report comparable numbers against a doc-stated target (e.g.
efficacy >= 80%), this:

  1. (LLM) normalizes the meaning of exact document/source spans into one
     typed semantic contract with honest unknown/other states.
  2. (code) verifies schemas, cited passages, IDs, URLs, provenance, and source
     identities; then admits only structurally valid atomic measurements.
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
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import fmean, stdev
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from pydantic import ValidationError

from services.chunker import ContentBlock
from services.searcher import Finding

from ..ai import request_structured
from ..ai_contracts import (
    document_quantitative_ledger_batch,
    source_measurement_batch,
)
from ..ai_wire import (
    EvidenceUnitIdentityWire,
    NumericExpressionWire,
    SemanticSlotWire,
    TernaryDecisionWire,
)
from ..context import (
    BLOCK_ID_JSON_INSTRUCTION,
    document_block_ids,
    render_document_context,
    validated_block_ids,
)
from ..models import (
    Attribute,
    ConformityScore,
    DocumentSpan,
    Insight,
    LLMClientProtocol,
    Measurement,
    MeasurementSemanticAssessment,
    EvidenceUnitIdentity,
    NumericExpression,
    QUANTITATIVE_SEMANTIC_FIELDS,
    QuantitativeLedger,
    QuantitativeLedgerReview,
    SEMANTIC_SLOT_STATES,
    QuantitativeTarget,
    QuantitativeStatementDisposition,
    SemanticDimensionAssessment,
    SemanticSlot,
    SourcePassageDisposition,
    TernaryDecision,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
SOURCE_BATCH_SIZE = 3
SOURCE_MAPPING_MAX_WORKERS = 6
MAX_SOURCE_PASSAGE_CHARS = 8_000
MAX_TARGET_QUOTE_CHARS = 800
LEDGER_BATCH_MAX_UNITS = 24
LEDGER_BATCH_MAX_CHARS = 24_000
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
class QuantitativeStatementUnit:
    """One exact canonical field span reviewed without rebinding ownership."""

    id: str
    block_id: str
    quote: str
    attribute_ref: str = ""


@dataclass(frozen=True)
class QuantitativeLedgerBatch:
    """A bounded set of statement units plus their original source blocks."""

    units: list[QuantitativeStatementUnit]
    blocks: list[ContentBlock]


@dataclass(frozen=True)
class QuantitativeLedgerBatchResult:
    """Validated output for one non-overlapping ledger batch."""

    reviews: list[QuantitativeLedgerReview]
    targets: list[QuantitativeTarget]


@dataclass(frozen=True)
class _CanonicalNumericBinding:
    """One upstream document binding available as semantic context."""

    ref: str
    attribute_ref: str
    document_target: str
    spans: tuple[DocumentSpan, ...]
    entities: tuple[str, ...]


@dataclass(frozen=True)
class _QuantitativeBatchValidation:
    result: QuantitativeLedgerBatchResult
    retry_unit_ids: set[str]


@dataclass(frozen=True)
class _TargetMappingValidation:
    targets: list[QuantitativeTarget]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PassageMeasurementValidation:
    measurement: Measurement | None = None
    candidate_key: "_MeasurementCandidateKey | None" = None
    code: str = ""
    reason: str = ""


@dataclass(frozen=True)
class _MeasurementCandidateKey:
    """The one canonical identity for a target-relative source proposal."""

    canonical_json: str

    @classmethod
    def from_validated(
        cls,
        *,
        target_id: str,
        source_id: str,
        quote: str,
        expression: NumericExpression,
        evidence_unit_id: str,
        evidence_unit: EvidenceUnitIdentity,
        semantic_assessment: MeasurementSemanticAssessment,
    ) -> "_MeasurementCandidateKey":
        payload = {
            "target_id": target_id,
            "source_id": source_id,
            "quote": _normalize_quote(quote),
            "expression": {
                "kind": expression.kind,
                "unit": _unit_key(expression.unit),
                "value": expression.value,
                "lower": expression.lower,
                "upper": expression.upper,
                "comparator": expression.comparator,
            },
            "evidence_unit": {
                "id": evidence_unit_id,
                "status": evidence_unit.status,
            },
            "semantic_assessment": {
                "source_ownership": semantic_assessment.source_ownership.state,
                "dimensions": {
                    field_name: {
                        "source": {
                            "state": assessment.source.state,
                            "value": assessment.source.value.casefold(),
                            "other": assessment.source.other.casefold(),
                        },
                        "compatibility": assessment.compatibility.state,
                    }
                    for field_name, assessment in sorted(
                        semantic_assessment.dimensions.items()
                    )
                },
            },
        }
        return cls(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    @property
    def candidate_id(self) -> str:
        digest = hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()
        return f"qm-{digest}"


@dataclass(frozen=True)
class _CalibrationTask:
    """One independent target-relative source-passage mapping request."""

    attribute: Attribute
    target: QuantitativeTarget
    passages: list[_SourcePassage]


@dataclass(frozen=True)
class _CalibrationBatchResult:
    measurements: list[Measurement]
    dispositions: list[SourcePassageDisposition]


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
        scores.append(
            _finalize_target_score(target, candidates, dispositions, insights)
        )
    return scores


def score_conformity_all(
    attributes: list[Attribute],
    insights_by_attribute: dict[str, list[Insight]],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_workers: int = SOURCE_MAPPING_MAX_WORKERS,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[ConformityScore]:
    """Calibrate all targets through one bounded, ordered work queue.

    Each target/passage batch is semantically independent. Concurrency changes
    only request scheduling: task inputs, local retry behavior, validation, and
    deterministic cohort assembly are shared with the sequential entry point.
    """
    target_order: list[tuple[Attribute, QuantitativeTarget, list[Insight]]] = []
    tasks: list[_CalibrationTask] = []
    for attribute in attributes:
        insights = insights_by_attribute.get(attribute.name, [])
        passages = _source_passages(insights)
        for target in attribute.quantitative_targets:
            target_order.append((attribute, target, insights))
            tasks.extend(
                _CalibrationTask(
                    attribute=attribute,
                    target=target,
                    passages=passages[start : start + SOURCE_BATCH_SIZE],
                )
                for start in range(0, len(passages), SOURCE_BATCH_SIZE)
            )

    total = len(tasks)
    if progress_callback and total:
        progress_callback(0, total)
    completed = 0
    progress_lock = threading.Lock()

    def run(task: _CalibrationTask) -> _CalibrationBatchResult:
        nonlocal completed
        result = _map_source_passage_batch(
            task.attribute,
            task.target,
            task.passages,
            llm_client,
            indication=indication,
            intervention_class=intervention_class,
            max_tokens=max_tokens,
        )
        if progress_callback:
            with progress_lock:
                completed += 1
                progress_callback(completed, total)
        return result

    if tasks:
        worker_count = max(1, min(max_workers, total))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            batch_results = list(executor.map(run, tasks))
    else:
        batch_results = []

    mapped: dict[
        tuple[str, str], tuple[list[Measurement], list[SourcePassageDisposition]]
    ] = {}
    for task, result in zip(tasks, batch_results):
        key = (task.attribute.name, task.target.id)
        measurements, dispositions = mapped.setdefault(key, ([], []))
        measurements.extend(result.measurements)
        dispositions.extend(result.dispositions)

    scores: list[ConformityScore] = []
    for attribute, target, insights in target_order:
        candidates, dispositions = mapped.get(
            (attribute.name, target.id),
            ([], []),
        )
        scores.append(
            _finalize_target_score(target, candidates, dispositions, insights)
        )
    return scores


def _finalize_target_score(
    target: QuantitativeTarget,
    candidates: list[Measurement],
    dispositions: list[SourcePassageDisposition],
    insights: list[Insight],
) -> ConformityScore:
    """Apply the one deterministic cohort and statistics boundary."""
    measurements, excluded_measurements = _partition_cohort(candidates, target)
    if not measurements:
        return _empty_score(target, excluded_measurements, dispositions)
    _attach_dates(measurements, insights)
    return _combine(
        target,
        measurements,
        excluded_measurements,
        dispositions,
    )


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

    AI owns bounded semantic mapping, but prose-derived measurements are only
    candidates. Code admits a semantically eligible scalar only after explicit
    review, or when a future adapter supplies a typed structured fact.
    """
    included: list[Measurement] = []
    excluded: list[Measurement] = []
    eligible_by_unit: dict[str, list[Measurement]] = {}
    for candidate in candidates:
        candidate.semantic_status, candidate.semantic_reason = (
            _derived_semantic_status(candidate, target)
        )
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
        if _unit_key(candidate.unit) != _unit_key(target.unit):
            reasons.append("numeric unit is incompatible with the document target")
        if candidate.semantic_status == "comparable":
            if candidate.evidence_mode == "structured_fact":
                candidate.admission_status = "auto_admitted"
                candidate.admission_reason = (
                    "The adapter supplied a typed source-owned numeric fact."
                )
            elif candidate.admission_status not in {"approved", "rejected"}:
                candidate.admission_status = "needs_review"
                candidate.admission_reason = (
                    "This candidate was semantically mapped from prose and requires "
                    "explicit review before it can enter descriptive statistics."
                )
        else:
            candidate.admission_status = "not_eligible"
            candidate.admission_reason = candidate.semantic_reason
        if candidate.admission_status not in {"approved", "auto_admitted"}:
            reasons.append(candidate.admission_reason or "candidate is not admitted")
        if reasons:
            candidate.exclusion_reasons = reasons
            excluded.append(candidate)
            continue
        evidence_unit_id = candidate.evidence_unit_id or candidate.source_record_id
        eligible_by_unit.setdefault(evidence_unit_id, []).append(candidate)

    for evidence_unit_id, unit_candidates in eligible_by_unit.items():
        unique_values = {candidate.value for candidate in unit_candidates}
        if len(unique_values) > 1:
            for candidate in unit_candidates:
                candidate.exclusion_reasons = [
                    "multiple admitted scalar values from evidence unit "
                    f"{evidence_unit_id}; one estimate must be selected"
                ]
                excluded.append(candidate)
            continue
        selected, *duplicates = unit_candidates
        selected.inclusion_reason = (
            "This admitted measurement satisfied the typed calculation contract and "
            f"was deduplicated as evidence unit {evidence_unit_id}. "
            f"{selected.admission_reason}"
        )
        included.append(selected)
        for duplicate in duplicates:
            duplicate.exclusion_reasons = [
                f"duplicate evidence unit and value: {evidence_unit_id}"
            ]
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
        None
        if target.comparator == "="
        else 1.0 - target_percentile
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
            f"{target_meeting_count} of {benchmark_count} admitted comparators "
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
        ambition_percentile=(
            round(ambition_percentile, 3)
            if ambition_percentile is not None
            else None
        ),
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
        "=": math.isclose(value, target, rel_tol=1e-9, abs_tol=1e-9),
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
# Canonical document-first target ledger
# ---------------------------------------------------------------------------


def prepare_quantitative_ledger_batches(
    blocks: list[ContentBlock],
    attributes: list[Attribute] | None = None,
    *,
    max_units: int = LEDGER_BATCH_MAX_UNITS,
    max_chars: int = LEDGER_BATCH_MAX_CHARS,
) -> list[QuantitativeLedgerBatch]:
    """Batch exact spans from the authoritative document-claim ledger.

    Numeric interpretation must not scan the raw document and independently
    recreate field ownership. Each unit is therefore one complete, already
    validated field span. Keeping the whole span also preserves table labels,
    populations, roles, and qualifiers that were previously lost by splitting
    flattened cells into sentence fragments.

    ``attributes=None`` remains a narrow compatibility path for focused legacy
    tests; production always supplies the resolved canonical attributes.
    """
    block_by_id = {block.id: block for block in blocks}
    units: list[QuantitativeStatementUnit] = []
    seen_units: set[tuple[str, str, tuple[str, ...]]] = set()
    if attributes is None:
        for block in blocks:
            for unit in _statement_units(block):
                units.append(unit)
    else:
        for attribute in attributes:
            if not attribute.target_resolved or not attribute.document_target:
                continue
            for span in attribute.document_spans:
                block_ids = tuple(
                    block_id for block_id in span.block_ids if block_id in block_by_id
                )
                if not block_ids:
                    continue
                key = (attribute.name, _normalize_quote(span.quote), block_ids)
                if key in seen_units:
                    continue
                seen_units.add(key)
                material = "\n".join((attribute.name, *block_ids, span.quote))
                units.append(
                    QuantitativeStatementUnit(
                        id="qlu-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16],
                        block_id=block_ids[0],
                        quote=span.quote,
                        attribute_ref=attribute.name,
                    )
                )

    batches: list[QuantitativeLedgerBatch] = []
    batch_blocks: list[ContentBlock] = []
    batch_units: list[QuantitativeStatementUnit] = []
    batch_chars = 0

    def flush() -> None:
        nonlocal batch_blocks, batch_units, batch_chars
        if batch_units:
            batches.append(
                QuantitativeLedgerBatch(units=batch_units, blocks=batch_blocks)
            )
        batch_blocks = []
        batch_units = []
        batch_chars = 0

    for unit in units:
        unit_blocks = [
            block_by_id[block_id]
            for block_id in dict.fromkeys([unit.block_id])
            if block_id in block_by_id
        ]
        added_blocks = [
            block for block in unit_blocks if all(item.id != block.id for item in batch_blocks)
        ]
        added_chars = sum(len(block.content or "") for block in added_blocks)
        if batch_units and (
            len(batch_units) + 1 > max_units
            or batch_chars + added_chars > max_chars
        ):
            flush()
            added_blocks = unit_blocks
            added_chars = sum(len(block.content or "") for block in added_blocks)
        batch_blocks.extend(added_blocks)
        batch_chars += added_chars
        batch_units.append(unit)
    flush()
    return batches


def _canonical_numeric_bindings(
    attributes: list[Attribute],
) -> list[_CanonicalNumericBinding]:
    """Project the upstream claim ledger into stable semantic context refs.

    Only exact, document-present bindings qualify. The opaque refs are local to
    one model request and resolve back to already-validated ``DocumentSpan``
    objects; they never become result data.
    """
    bindings: list[_CanonicalNumericBinding] = []
    for index, attribute in enumerate(attributes, 1):
        if (
            not attribute.target_resolved
            or not attribute.document_target
            or not attribute.document_spans
        ):
            continue
        bindings.append(
            _CanonicalNumericBinding(
                ref=f"binding-{index:04d}",
                attribute_ref=attribute.name,
                document_target=attribute.document_target,
                spans=tuple(attribute.document_spans),
                entities=tuple(
                    dict.fromkeys(
                        f"{entity.entity_type}: {entity.name}"
                        + (f" ({entity.identifier})" if entity.identifier else "")
                        for entity in attribute.entities
                    )
                ),
            )
        )
    return bindings


def _resolve_document_semantic_provenance(
    raw_profile: object,
    *,
    unit: QuantitativeStatementUnit,
    bindings_by_ref: dict[str, _CanonicalNumericBinding],
) -> dict[str, list[dict[str, object]]] | None:
    """Resolve model-selected context refs to exact canonical source spans."""
    if not isinstance(raw_profile, dict) or set(raw_profile) != set(
        QUANTITATIVE_SEMANTIC_FIELDS
    ):
        return None
    output: dict[str, list[dict[str, object]]] = {}
    for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
        raw_slot = raw_profile.get(field_name)
        if not isinstance(raw_slot, dict):
            return None
        state = str(raw_slot.get("state", "")).strip().lower()
        raw_refs = raw_slot.get("source_refs")
        if state not in SEMANTIC_SLOT_STATES or not isinstance(raw_refs, list):
            return None
        refs = list(
            dict.fromkeys(
                str(value).strip()
                for value in raw_refs
                if isinstance(value, str) and str(value).strip()
            )
        )
        asserted = state in {"specified", "other"}
        if asserted != bool(refs):
            return None
        spans: list[DocumentSpan] = []
        for ref in refs:
            if ref == "statement":
                spans.append(DocumentSpan(quote=unit.quote, block_ids=[unit.block_id]))
                continue
            binding = bindings_by_ref.get(ref)
            if binding is None:
                return None
            spans.extend(binding.spans)
        deduplicated: list[DocumentSpan] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for span in spans:
            key = (span.quote.casefold(), tuple(span.block_ids))
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(span)
        if asserted and not deduplicated:
            return None
        output[field_name] = [
            {"quote": span.quote, "block_ids": list(span.block_ids)}
            for span in deduplicated
        ]
    return output


def _render_document_semantic_context(
    blocks: list[ContentBlock],
    canonical_bindings: list[_CanonicalNumericBinding],
) -> str:
    """Render local blocks plus exact upstream spans for provenance checks."""
    sections = [render_document_context(blocks)]
    seen: set[tuple[str, str]] = set()
    for binding in canonical_bindings:
        for span in binding.spans:
            for block_id in span.block_ids:
                key = (block_id, span.quote)
                if key in seen:
                    continue
                seen.add(key)
                sections.append(f"[block:{block_id}]\n{span.quote}")
    return "\n\n".join(section for section in sections if section)


def extract_quantitative_ledger_batch(
    batch: QuantitativeLedgerBatch,
    attributes: list[Attribute],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> QuantitativeLedgerBatchResult:
    """Review a bounded statement batch, retrying incomplete items once."""
    canonical_bindings = _canonical_numeric_bindings(attributes)
    system_prompt = _document_ledger_system_prompt(
        attributes,
        canonical_bindings=canonical_bindings,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
    )
    images = [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in batch.blocks
        if block.image
    ] or None

    def request(
        current: QuantitativeLedgerBatch,
        feedback: dict[str, str] | None = None,
    ) -> object | None:
        contract = document_quantitative_ledger_batch(
            [binding.ref for binding in canonical_bindings],
            [unit.id for unit in current.units],
            [attribute.name for attribute in attributes],
        )
        user_message = _document_ledger_user_message(current)
        if feedback:
            details = "\n".join(
                f"- [unit:{unit_id}] {reason}"
                for unit_id, reason in feedback.items()
            )
            user_message += (
                "\n\nA prior mapping for these units failed its typed or source-lineage contract. "
                "Correct only the cited contract violations; do not change valid source meaning:\n"
                f"{details}"
            )
        return request_structured(
            llm_client,
            contract,
            system_prompt,
            user_message,
            max_tokens=max_tokens,
            images=images,
        )

    first = _validated_quantitative_ledger_batch(
        request(batch),
        batch=batch,
        attributes=attributes,
        canonical_bindings=canonical_bindings,
    )
    if not first.retry_unit_ids:
        return first.result
    retry_batch = QuantitativeLedgerBatch(
        units=[unit for unit in batch.units if unit.id in first.retry_unit_ids],
        blocks=batch.blocks,
    )
    retry_feedback = {
        review.unit_id: review.reason
        for review in first.result.reviews
        if review.unit_id in first.retry_unit_ids
    }
    retry = _validated_quantitative_ledger_batch(
        request(retry_batch, retry_feedback),
        batch=retry_batch,
        attributes=attributes,
        canonical_bindings=canonical_bindings,
    )
    retained_reviews = [
        review
        for review in first.result.reviews
        if review.unit_id not in first.retry_unit_ids
    ]
    review_by_id = {
        review.unit_id: review
        for review in [*retained_reviews, *retry.result.reviews]
    }
    merged_reviews = [review_by_id[unit.id] for unit in batch.units]
    retained_target_ids = {
        target_id for review in retained_reviews for target_id in review.target_ids
    }
    target_by_id = {
        target.id: target
        for target in [
            *(
                target
                for target in first.result.targets
                if target.id in retained_target_ids
            ),
            *retry.result.targets,
        ]
    }
    return QuantitativeLedgerBatchResult(
        reviews=merged_reviews,
        targets=list(target_by_id.values()),
    )


def _validated_quantitative_ledger_batch(
    parsed: object,
    *,
    batch: QuantitativeLedgerBatch,
    attributes: list[Attribute],
    canonical_bindings: list[_CanonicalNumericBinding],
) -> _QuantitativeBatchValidation:
    """Validate one response and identify only structurally failed units."""
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    bindings_by_ref = {binding.ref: binding for binding in canonical_bindings}
    batch_text = render_document_context(batch.blocks)
    semantic_context = _render_document_semantic_context(
        batch.blocks,
        canonical_bindings,
    )
    raw_reviews = parsed.get("reviews") if isinstance(parsed, dict) else None
    raw_reviews = raw_reviews if isinstance(raw_reviews, list) else []
    by_id: dict[str, dict] = {}
    duplicate_ids: set[str] = set()
    for raw in raw_reviews:
        if not isinstance(raw, dict):
            continue
        unit_id = str(raw.get("unit_id", "")).strip()
        if not unit_id:
            continue
        if unit_id in by_id:
            duplicate_ids.add(unit_id)
        else:
            by_id[unit_id] = raw

    batch_block_ids = {block.id for block in batch.blocks}
    reviews: list[QuantitativeLedgerReview] = []
    targets: list[QuantitativeTarget] = []
    retry_unit_ids: set[str] = set()
    for unit in batch.units:
        raw = by_id.get(unit.id)
        if raw is None or unit.id in duplicate_ids:
            retry_unit_ids.add(unit.id)
            reviews.append(
                _uncertain_unit_review(
                    unit,
                    "The model did not return one unique review for this statement.",
                )
            )
            continue
        classification = str(raw.get("classification", "")).strip().lower()
        reason = " ".join(str(raw.get("reason", "")).split())
        attribute_ref = str(raw.get("attribute_ref", "")).strip()
        canonical_owner = unit.attribute_ref
        raw_targets = raw.get("targets")
        raw_targets = raw_targets if isinstance(raw_targets, list) else []
        if (
            classification not in {
                "target", "context_only", "non_scalar", "range_or_set",
                "non_numeric", "uncertain",
            }
            or not reason
            or (attribute_ref and attribute_ref not in attributes_by_name)
            or (canonical_owner and attribute_ref not in {"", canonical_owner})
        ):
            retry_unit_ids.add(unit.id)
            reviews.append(
                _uncertain_unit_review(
                    unit,
                    "The model returned an invalid statement classification.",
                    attribute_ref=(
                        attribute_ref if attribute_ref in attributes_by_name else ""
                    ),
                )
            )
            continue

        if classification != "target":
            if raw_targets:
                retry_unit_ids.add(unit.id)
                reviews.append(
                    _uncertain_unit_review(
                        unit,
                        "A non-target statement incorrectly carried target objects.",
                        attribute_ref=attribute_ref,
                    )
                )
                continue
            if classification == "non_numeric":
                attribute_ref = ""
            reviews.append(
                QuantitativeLedgerReview(
                    unit_id=unit.id,
                    block_id=unit.block_id,
                    quote=unit.quote,
                    classification=classification,
                    attribute_ref=attribute_ref or canonical_owner,
                    reason=reason,
                    review_status=(
                        "needs_review" if classification == "uncertain" else "resolved"
                    ),
                )
            )
            continue

        validated: list[QuantitativeTarget] = []
        validation_issues: list[str] = []
        for raw_target in raw_targets:
            if not isinstance(raw_target, dict):
                validation_issues.append("invalid_target_object")
                continue
            owner = str(raw_target.get("attribute_ref", "")).strip()
            if canonical_owner:
                owner = canonical_owner
            attribute = attributes_by_name.get(owner)
            if (
                attribute is None
                or not attribute.target_resolved
                or not attribute.document_target
                or unit.block_id not in attribute.block_ids
            ):
                validation_issues.append("invalid_field_ownership")
                continue
            target_quote = " ".join(str(raw_target.get("quote", "")).split())
            if (
                not target_quote
                or len(target_quote) > MAX_TARGET_QUOTE_CHARS
                or not _quote_in_text(target_quote, unit.quote)
            ):
                validation_issues.append("invalid_target_quote")
                continue
            candidate = dict(raw_target)
            candidate["attribute_ref"] = owner
            candidate["provenance_spans"] = [
                {"quote": target_quote, "block_ids": [unit.block_id]}
            ]
            raw_profile = raw_target.get("semantic_profile")
            semantic_provenance = _resolve_document_semantic_provenance(
                raw_profile,
                unit=unit,
                bindings_by_ref=bindings_by_ref,
            )
            if semantic_provenance is None:
                validation_issues.append("invalid_semantic_provenance")
                continue
            candidate["semantic_provenance"] = semantic_provenance
            candidate["review_status"] = "needs_review"
            candidate["ownership_reason"] = (
                " ".join(str(raw_target.get("ownership_reason", "")).split())
                or reason
            )
            mapping = _validated_targets_with_issues(
                [candidate],
                attribute=attribute,
                doc_text=batch_text,
                semantic_context=semantic_context,
                allowed_target_block_ids=set(attribute.block_ids) & batch_block_ids,
                require_document_target_support=True,
                canonical_semantic_provenance=True,
            )
            if len(mapping.targets) != 1:
                validation_issues.extend(mapping.issues or ("invalid_target_mapping",))
                continue
            validated.extend(mapping.targets)
        if validation_issues or not validated:
            retry_unit_ids.add(unit.id)
            issue_text = ", ".join(dict.fromkeys(
                validation_issues or ["missing_target_mapping"]
            ))
            reviews.append(
                _uncertain_unit_review(
                    unit,
                    f"Target mapping rejected [{issue_text}].",
                    attribute_ref=(
                        attribute_ref if attribute_ref in attributes_by_name else ""
                    ),
                )
            )
            continue
        targets.extend(validated)
        validated_attribute_refs = {target.attribute_ref for target in validated}
        reviews.append(
            QuantitativeLedgerReview(
                unit_id=unit.id,
                block_id=unit.block_id,
                quote=unit.quote,
                classification="target",
                reason=reason,
                attribute_ref=(
                    next(iter(validated_attribute_refs))
                    if len(validated_attribute_refs) == 1
                    else ""
                ),
                target_ids=[target.id for target in validated],
                review_status="resolved",
            )
        )
    return _QuantitativeBatchValidation(
        result=QuantitativeLedgerBatchResult(reviews=reviews, targets=targets),
        retry_unit_ids=retry_unit_ids,
    )


def assemble_quantitative_document_ledger(
    attributes: list[Attribute],
    batches: list[QuantitativeLedgerBatch],
    results: list[QuantitativeLedgerBatchResult],
) -> tuple[list[Attribute], QuantitativeLedger]:
    """Merge batch outputs once and derive every field-local quantitative view."""
    reviews = [review for result in results for review in result.reviews]
    targets = _merge_document_targets(
        [target for result in results for target in result.targets]
    )
    known_target_ids = {target.id for target in targets}
    reviews = [
        replace(
            review,
            target_ids=[
                target_id
                for target_id in review.target_ids
                if target_id in known_target_ids
            ],
        )
        for review in reviews
    ]
    uncertain_count = sum(review.classification == "uncertain" for review in reviews)
    attribute_names = {attribute.name for attribute in attributes}
    owned_block_ids = {
        block_id for attribute in attributes for block_id in attribute.block_ids
    }
    target_context_uncertain_count = sum(
        review.classification == "uncertain"
        and (
            review.attribute_ref in attribute_names
            or review.block_id in owned_block_ids
        )
        for review in reviews
    )
    numeric_non_targets = sum(
        review.classification
        in {"context_only", "non_scalar", "range_or_set", "uncertain"}
        for review in reviews
    )
    if target_context_uncertain_count:
        status = "uncertain"
    elif targets or numeric_non_targets:
        status = "complete"
    else:
        status = "not_applicable"
    reason = (
        f"Reviewed {len(reviews)} non-overlapping document statements; mapped "
        f"{len(targets)} numeric targets; retained {numeric_non_targets} non-target "
        f"or unresolved numeric statements; {uncertain_count} statements remain uncertain, "
        f"including {target_context_uncertain_count} in target-bearing document "
        "context. Uncertain statements are excluded from target-specific retrieval "
        "and calibration without blocking qualitative evidence retrieval."
    )
    ledger = QuantitativeLedger(
        status=status,
        reason=reason,
        block_ids=list(
            dict.fromkeys(
                block.id for batch in batches for block in batch.blocks
            )
        ),
        reviews=reviews,
        targets=targets,
    )
    return _project_ledger_to_attributes(attributes, ledger), ledger


def finalize_quantitative_document_review(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
) -> tuple[list[Attribute], QuantitativeLedger]:
    """Freeze explicit client-held target decisions before retrieval.

    The client returns the complete portable draft, so no server session or
    second document interpretation is required. Rejected proposals remain in
    the ledger audit trail but are not projected into retrieval/calculation.
    Uncertain statements must be explicitly acknowledged as excluded.
    """
    pending_targets = [
        target.id for target in ledger.targets if target.review_status == "needs_review"
    ]
    pending_statements = [
        review.unit_id
        for review in ledger.reviews
        if review.review_status == "needs_review"
    ]
    if pending_targets or pending_statements:
        raise ValueError(
            "Document target review is incomplete: "
            f"{len(pending_targets)} target proposal(s) and "
            f"{len(pending_statements)} unresolved statement(s) remain."
        )
    return _project_ledger_to_attributes(
        attributes,
        ledger,
        admitted_statuses={"approved"},
    ), ledger


def _statement_units(block: ContentBlock) -> list[QuantitativeStatementUnit]:
    units: list[QuantitativeStatementUnit] = []
    ordinal = 0
    for raw_line in (block.content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Semicolons commonly separate independently qualified numeric claims
        # inside one table cell.  Splitting only at this explicit delimiter
        # avoids language-specific sentence heuristics.
        pieces = [piece.strip() for piece in re.split(r"\s*;\s*", line) if piece.strip()]
        for piece in pieces:
            material = f"{block.id}\n{ordinal}\n{piece}"
            unit_id = "qlu-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
            units.append(
                QuantitativeStatementUnit(
                    id=unit_id,
                    block_id=block.id,
                    quote=piece,
                    attribute_ref="",
                )
            )
            ordinal += 1
    if not units and block.image:
        material = f"{block.id}\nvisual"
        units.append(
            QuantitativeStatementUnit(
                id="qlu-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16],
                block_id=block.id,
                quote="[visual content]",
                attribute_ref="",
            )
        )
    return units


def _uncertain_unit_review(
    unit: QuantitativeStatementUnit,
    reason: str,
    *,
    attribute_ref: str = "",
) -> QuantitativeLedgerReview:
    return QuantitativeLedgerReview(
        unit_id=unit.id,
        block_id=unit.block_id,
        quote=unit.quote,
        classification="uncertain",
        reason=reason,
        attribute_ref=attribute_ref,
        review_status="needs_review",
    )


def _merge_document_targets(
    targets: list[QuantitativeTarget],
) -> list[QuantitativeTarget]:
    merged: dict[str, QuantitativeTarget] = {}
    for target in targets:
        existing = merged.get(target.id)
        if existing is None:
            merged[target.id] = target
            continue
        spans = list(existing.provenance_spans)
        span_keys = {(_normalize_quote(span.quote), tuple(span.block_ids)) for span in spans}
        spans.extend(
            span for span in target.provenance_spans
            if (_normalize_quote(span.quote), tuple(span.block_ids)) not in span_keys
        )
        semantic_provenance: dict[str, list[DocumentSpan]] = {}
        for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
            field_spans = list(existing.semantic_provenance.get(field_name, []))
            field_keys = {
                (_normalize_quote(span.quote), tuple(span.block_ids))
                for span in field_spans
            }
            field_spans.extend(
                span for span in target.semantic_provenance.get(field_name, [])
                if (_normalize_quote(span.quote), tuple(span.block_ids)) not in field_keys
            )
            semantic_provenance[field_name] = field_spans
        merged[target.id] = replace(
            existing,
            provenance_spans=spans,
            semantic_provenance=semantic_provenance,
            id=existing.id,
        )
    return list(merged.values())


def _project_ledger_to_attributes(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    *,
    admitted_statuses: set[str] | None = None,
) -> list[Attribute]:
    targets_by_attribute: dict[str, list[QuantitativeTarget]] = {
        attribute.name: [] for attribute in attributes
    }
    for target in ledger.targets:
        if admitted_statuses is None or target.review_status in admitted_statuses:
            targets_by_attribute[target.attribute_ref].append(target)
    attributes_by_block: dict[str, set[str]] = {}
    for attribute in attributes:
        for block_id in attribute.block_ids:
            attributes_by_block.setdefault(block_id, set()).add(attribute.name)
    dispositions_by_attribute: dict[str, list[QuantitativeStatementDisposition]] = {
        attribute.name: [] for attribute in attributes
    }
    for review in ledger.reviews:
        if (
            review.attribute_ref in dispositions_by_attribute
            and review.attribute_ref
            in attributes_by_block.get(review.block_id, set())
            and review.classification
            in {"context_only", "non_scalar", "range_or_set", "uncertain"}
        ):
            dispositions_by_attribute[review.attribute_ref].append(
                QuantitativeStatementDisposition(
                    quote=review.quote,
                    block_ids=[review.block_id],
                    disposition=review.classification,
                    reason=review.reason,
                    attribute_ref=review.attribute_ref,
                )
            )
    uncertain_attribute_refs: set[str] = set()
    for review in ledger.reviews:
        owners = attributes_by_block.get(review.block_id, set())
        if review.classification != "uncertain":
            continue
        if review.attribute_ref in owners:
            uncertain_attribute_refs.add(review.attribute_ref)
        elif len(owners) == 1:
            uncertain_attribute_refs.update(owners)
    projected: list[Attribute] = []
    for attribute in attributes:
        targets = targets_by_attribute[attribute.name]
        dispositions = dispositions_by_attribute[attribute.name]
        block_ids = list(
            dict.fromkeys(
                [
                    *attribute.block_ids,
                    *(block_id for target in targets for block_id in target.doc_block_ids),
                ]
            )
        )
        document_target = attribute.document_target
        document_spans = list(attribute.document_spans)
        if targets:
            document_spans = list(
                {
                    (span.quote, tuple(span.block_ids)): span
                    for span in [
                        *document_spans,
                        *(
                            span
                            for target in targets
                            for span in target.provenance_spans
                        ),
                    ]
                }.values()
            )
        if document_spans:
            document_target = " ".join(
                dict.fromkeys(span.quote for span in document_spans)
            )
        if targets:
            status = "present"
            status_reason = (
                f"The document ledger assigned {len(targets)} independently "
                "calibratable numeric target(s) to this field."
            )
        elif attribute.name in uncertain_attribute_refs:
            status = "uncertain"
            status_reason = (
                "One or more statements in this field's source blocks could not be "
                "mapped or validated safely."
            )
        else:
            status = "not_applicable"
            status_reason = (
                "The complete document ledger assigned no independently calibratable "
                "numeric target to this field."
            )
        projected.append(
            replace(
                attribute,
                block_ids=block_ids,
                document_target=document_target,
                document_spans=document_spans,
                target_resolved=attribute.target_resolved or bool(document_target),
                quantitative_targets=targets,
                quantitative_statement_dispositions=dispositions,
                quantitative_target_status=status,
                quantitative_target_status_reason=status_reason,
            )
        )
    return projected


def _document_ledger_system_prompt(
    attributes: list[Attribute],
    *,
    canonical_bindings: list[_CanonicalNumericBinding] | None = None,
    indication: str,
    intervention_class: str,
    framing: str,
) -> str:
    field_catalog = "\n".join(
        f"- {attribute.name}: {attribute.description}"
        for attribute in attributes
    )
    canonical_bindings = canonical_bindings or _canonical_numeric_bindings(attributes)
    binding_catalog = "\n".join(
        (
            f"[context:{binding.ref}]\n"
            f"field: {binding.attribute_ref}\n"
            f"canonical target: {binding.document_target}\n"
            "source blocks: "
            + ", ".join(
                dict.fromkeys(
                    block_id
                    for span in binding.spans
                    for block_id in span.block_ids
                )
            )
            + ("\nentities: " + "; ".join(binding.entities) if binding.entities else "")
        )
        for binding in canonical_bindings
    ) or "(No document-present canonical bindings.)"
    framing = (
        framing.strip()
        or "Interpret each statement according to the uploaded document's own role."
    ).replace("{intervention_class}", intervention_class).replace(
        "{indication}", indication
    )
    return (
        "You create quantitative proposals from the authoritative document-claim ledger. "
        "Each supplied unit is already bound to exactly one canonical field. Preserve that "
        "ownership; do not rebind it or interpret unrelated raw-document text. Each unit must "
        "appear exactly once in reviews.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Document framing: {framing}\n\n"
        "Canonical fields:\n"
        f"{field_catalog}\n\n"
        "Canonical document bindings (authoritative cross-block context):\n"
        f"{binding_catalog}\n\n"
        "For every unit choose target, context_only, non_scalar, range_or_set, "
        "non_numeric, or uncertain. Use uncertain instead of guessing. A target is an "
        "explicit exact or directional scalar that can be compared independently. Split "
        "distinct roles, populations, regimens, time horizons, and semicolon-delimited "
        "claims into atomic target objects. A unit may contain multiple target objects. "
        "For each target repeat the canonical field shown beside the unit exactly. "
        "If a non-target clearly belongs to one field, set its attribute_ref; otherwise "
        "use an empty string. A [visual content] unit may be classified non_numeric when "
        "the image has no numeric claim; otherwise classify it uncertain because it has "
        "no exact source text from which a target can be verified.\n\n"
        "A number is a target only when the document asserts it as a desired, required, "
        "threshold, optimal, maximum, minimum, or exact criterion. Values mentioned only in "
        "a rejected alternative, contrast, example, citation, background fact, or phrase such "
        "as 'as opposed to' are context_only, never targets. Numeric syntax may come only from "
        "the supplied unit. Canonical bindings provide "
        "cross-block meaning but are not additional numeric statements to extract in this "
        "batch. For each target, quote copies the shortest complete, exact source excerpt that "
        "asserts that one target. It must include its numeric expression and enough local wording "
        "to identify the measure and qualifiers, must be a verbatim substring of the supplied "
        "unit, and must not exceed 800 characters. Do not return the whole field span when a "
        "shorter target-specific excerpt is available. expression is your normalized semantic "
        "reading of that excerpt. Convert written quantities and directional prose into the typed "
        "numeric schema, preserve the stated magnitude, and use a concise canonical unit. Do not "
        "invent a target or infer one from background knowledge. Copy the short exact excerpt "
        "into quote; code binds that citation to the unit's existing block provenance without "
        "reinterpreting its numeric meaning. The surrounding source block may establish "
        "threshold/optimal role "
        "and semantic meaning. Preserve "
        "the document's row or endpoint label. semantic_profile uses measure, endpoint, "
        "intervention, population, regimen, time_horizon, statistic, and conditions. "
        "Comparison dimensions are derived by code from asserted semantic slots and from slots "
        "that are unknown and comparison-required; "
        "return the same set in comparison_dimensions for schema compatibility. For every "
        "semantic slot, source_refs must identify where its "
        "meaning came from: statement for the reviewed unit, or one or more exact "
        "[context:<ref>] bindings above. Asserted slots require at least one source_ref; "
        "unasserted slots require none. Conditions includes only settings that change numeric "
        "interpretation. Do not judge whether external evidence passes the target.\n\n"
        "For non-target reviews targets must be empty. For target reviews include every "
        "atomic target in the unit. Copy unit IDs exactly. Return only the schema JSON."
    )


def _document_ledger_user_message(batch: QuantitativeLedgerBatch) -> str:
    units = "\n".join(
        f"[unit:{unit.id}] [field:{unit.attribute_ref}] [block:{unit.block_id}] {unit.quote}"
        for unit in batch.units
    )
    return (
        "Original source blocks (structural context):\n"
        f"{render_document_context(batch.blocks)}\n\n"
        "Review each statement unit exactly once:\n"
        f"{units}"
    )


def _validated_targets(
    items: object,
    *,
    attribute: Attribute,
    doc_text: str,
    semantic_context: str,
    allowed_target_block_ids: set[str] | None = None,
    require_document_target_support: bool = True,
    canonical_semantic_provenance: bool = False,
) -> list[QuantitativeTarget]:
    """Compatibility wrapper for callers that only need admitted targets."""
    return _validated_targets_with_issues(
        items,
        attribute=attribute,
        doc_text=doc_text,
        semantic_context=semantic_context,
        allowed_target_block_ids=allowed_target_block_ids,
        require_document_target_support=require_document_target_support,
        canonical_semantic_provenance=canonical_semantic_provenance,
    ).targets


def _validated_targets_with_issues(
    items: object,
    *,
    attribute: Attribute,
    doc_text: str,
    semantic_context: str,
    allowed_target_block_ids: set[str] | None = None,
    require_document_target_support: bool = True,
    canonical_semantic_provenance: bool = False,
) -> _TargetMappingValidation:
    if not isinstance(items, list):
        return _TargetMappingValidation([], ("invalid_target_list",))
    # A target is a fact owned by the canonical field binding, not merely a fact
    # found in relevance-selected context. Both the rendered input and the
    # binding must authorize its exact source block.
    rendered_ids = document_block_ids(doc_text)
    allowed_ids = (
        set(allowed_target_block_ids)
        if allowed_target_block_ids is not None
        else set(attribute.block_ids)
    )
    if rendered_ids:
        allowed_ids &= rendered_ids
    semantic_allowed_ids = document_block_ids(semantic_context)
    targets_by_id: dict[str, QuantitativeTarget] = {}
    issues: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            issues.append("invalid_target_object")
            continue
        raw_spans = item.get("provenance_spans")
        expression = _validated_numeric_expression(item.get("expression"))
        role = str(item.get("role", "other")).strip().lower()
        raw_dimensions = item.get("comparison_dimensions")
        semantic_profile = _validated_semantic_profile(item.get("semantic_profile"))
        ownership_reason = str(item.get("ownership_reason", "")).strip()
        if (
            expression is None
            or expression.kind != "bound"
            or role not in VALID_TARGET_ROLES
            or semantic_profile is None
            or not isinstance(raw_dimensions, list)
        ):
            issues.append("invalid_target_semantic_contract")
            continue
        proposed_dimensions = list(
            dict.fromkeys(
                str(value).strip()
                for value in raw_dimensions
                if isinstance(value, str)
            )
        )
        asserted_dimensions = {
            field_name
            for field_name, slot in semantic_profile.items()
            if slot.state in {"specified", "other"}
        }
        unknown_dimensions = {
            field_name
            for field_name, slot in semantic_profile.items()
            if slot.state == "unknown"
        }
        if set(proposed_dimensions) - set(QUANTITATIVE_SEMANTIC_FIELDS):
            issues.append("invalid_comparison_dimensions")
            continue
        # The semantic profile is authoritative. Deriving this projection here
        # prevents two AI-owned representations of the same meaning from
        # disagreeing and rejecting an otherwise valid target. Unknown slots
        # remain comparison-required, which fails closed downstream.
        comparison_dimensions = [
            field_name
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
            if field_name in asserted_dimensions or field_name in unknown_dimensions
        ]
        if "measure" not in comparison_dimensions:
            issues.append("invalid_target_semantic_contract")
            continue
        semantic_provenance = _validated_semantic_provenance(
            item.get("semantic_provenance"),
            semantic_profile,
            semantic_context,
            semantic_allowed_ids,
            max_quote_chars=(
                None if canonical_semantic_provenance else MAX_TARGET_QUOTE_CHARS
            ),
        )
        if semantic_provenance is None:
            issues.append("invalid_semantic_provenance")
            continue
        if not isinstance(raw_spans, list) or not raw_spans:
            issues.append("missing_target_provenance")
            continue
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
            ):
                continue
            seen_spans.add(span_key)
            spans.append(DocumentSpan(quote=span_quote, block_ids=span_ids))
        if not spans:
            issues.append("invalid_target_provenance")
            continue
        if require_document_target_support and not all(
            _quote_in_text(span.quote, attribute.document_target)
            for span in spans
        ):
            issues.append("target_outside_canonical_binding")
            continue
        target = QuantitativeTarget(
            attribute_ref=attribute.name,
            expression=expression,
            role=role,
            quote=spans[0].quote,
            doc_block_ids=list(
                dict.fromkeys(block_id for span in spans for block_id in span.block_ids)
            ),
            comparison_dimensions=comparison_dimensions,
            semantic_profile=semantic_profile,
            semantic_provenance=semantic_provenance,
            provenance_spans=spans,
            ownership_reason=ownership_reason,
            review_status=str(item.get("review_status", "approved")),
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
        merged_semantic_provenance: dict[str, list[DocumentSpan]] = {}
        for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
            field_spans = [*existing.semantic_provenance.get(field_name, [])]
            field_keys = {
                (_normalize_quote(span.quote), tuple(span.block_ids))
                for span in field_spans
            }
            field_spans.extend(
                span
                for span in target.semantic_provenance.get(field_name, [])
                if (_normalize_quote(span.quote), tuple(span.block_ids))
                not in field_keys
            )
            merged_semantic_provenance[field_name] = field_spans
        targets_by_id[target.id] = replace(
            existing,
            provenance_spans=merged_spans,
            semantic_provenance=merged_semantic_provenance,
            id=existing.id,
        )
    return _TargetMappingValidation(
        list(targets_by_id.values()),
        tuple(dict.fromkeys(issues)),
    )


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
    """Sequential compatibility entry point used by focused callers/tests."""
    passages = _source_passages(insights)
    measurements: list[Measurement] = []
    dispositions: list[SourcePassageDisposition] = []
    for start in range(0, len(passages), SOURCE_BATCH_SIZE):
        batch = passages[start : start + SOURCE_BATCH_SIZE]
        result = _map_source_passage_batch(
            attribute,
            target,
            batch,
            llm_client,
            indication=indication,
            intervention_class=intervention_class,
            max_tokens=max_tokens,
        )
        measurements.extend(result.measurements)
        dispositions.extend(result.dispositions)
    return measurements, dispositions


def _map_source_passage_batch(
    attribute: Attribute,
    target: QuantitativeTarget,
    batch: list[_SourcePassage],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int,
) -> _CalibrationBatchResult:
    """Map one independent batch, including its one local corrective retry."""
    system_prompt = _measurement_system_prompt(
        attribute,
        target=target,
        indication=indication,
        intervention_class=intervention_class,
    )
    contract = source_measurement_batch(
        _required_comparison_axes(target),
        [passage.id for passage in batch],
    )
    parsed = request_structured(
        llm_client,
        contract,
        system_prompt,
        _measurement_user_message(batch),
        max_tokens=max_tokens,
    )
    parsed = parsed if isinstance(parsed, dict) else {}
    measurements, dispositions, issues = _validated_source_decisions(
        parsed.get("sources"),
        passages={passage.id: passage for passage in batch},
        target=target,
    )
    decided = {item.source_id for item in dispositions}
    missing = [passage for passage in batch if passage.id not in decided]
    if missing:
        retry_contract = source_measurement_batch(
            _required_comparison_axes(target),
            [passage.id for passage in missing],
        )
        retry_parsed = request_structured(
            llm_client,
            retry_contract,
            system_prompt,
            _measurement_user_message(missing)
            + "\n\nA prior response omitted or malformed these source decisions. "
            "Correct only these typed or source-lineage failures and return exactly "
            "one complete decision for every source ID above:\n"
            + "\n".join(
                f"- [source:{passage.id}] "
                f"{issues.get(passage.id, 'missing_source_decision')}"
                for passage in missing
            ),
            max_tokens=max_tokens,
        )
        retry_parsed = retry_parsed if isinstance(retry_parsed, dict) else {}
        recovered_measurements, recovered_dispositions, retry_issues = (
            _validated_source_decisions(
                retry_parsed.get("sources"),
                passages={passage.id: passage for passage in missing},
                target=target,
            )
        )
        measurements.extend(recovered_measurements)
        dispositions.extend(recovered_dispositions)
        issues.update(retry_issues)

    decided = {item.source_id for item in dispositions}
    for passage in batch:
        if passage.id in decided:
            continue
        issue = issues.get(passage.id, "missing_source_decision")
        dispositions.append(
            SourcePassageDisposition(
                source_id=passage.id,
                status="uncertain",
                reason=f"Source mapping rejected [{issue}] after one retry.",
                url=passage.finding.url,
                insight_id=passage.insight.id,
            )
        )
    return _CalibrationBatchResult(measurements, dispositions)


def _validated_source_decisions(
    items: object,
    *,
    passages: dict[str, _SourcePassage],
    target: QuantitativeTarget,
) -> tuple[
    list[Measurement],
    list[SourcePassageDisposition],
    dict[str, str],
]:
    if not isinstance(items, list):
        return [], [], {
            source_id: "invalid_source_decision_list" for source_id in passages
        }
    output: list[Measurement] = []
    dispositions: list[SourcePassageDisposition] = []
    issues: dict[str, str] = {}
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
            issues[source_id] = "invalid_source_decision"
            continue
        raw_measurements = item.get("measurements")
        if status == "measurements_found" and not isinstance(raw_measurements, list):
            issues[source_id] = "invalid_measurement_list"
            continue
        validated_by_key: dict[str, Measurement] = {}
        measurement_issues: list[str] = []
        for raw_measurement in raw_measurements if isinstance(raw_measurements, list) else []:
            validation = _validated_passage_measurement(
                raw_measurement,
                passage=passage,
                target=target,
            )
            if validation.measurement is not None and validation.candidate_key is not None:
                validated_by_key.setdefault(
                    validation.candidate_key.canonical_json,
                    validation.measurement,
                )
            else:
                measurement_issues.append(validation.code or "invalid_measurement")
        if measurement_issues:
            # Never silently keep only the convenient subset of a model
            # decision. Retry the whole source or preserve it as uncertain.
            issues[source_id] = ", ".join(dict.fromkeys(measurement_issues))
            continue
        validated = list(validated_by_key.values())
        if status == "measurements_found" and not validated:
            issues[source_id] = "missing_validated_measurement"
            continue
        if status != "measurements_found" and validated:
            issues[source_id] = "unexpected_measurement_payload"
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
    for source_id in passages:
        if source_id not in seen and source_id not in issues:
            issues[source_id] = "missing_source_decision"
    return output, dispositions, issues


def _validated_passage_measurement(
    raw: object,
    *,
    passage: _SourcePassage,
    target: QuantitativeTarget,
) -> _PassageMeasurementValidation:
    if not isinstance(raw, dict):
        return _PassageMeasurementValidation(
            code="invalid_measurement_object",
            reason="Measurement was not an object.",
        )
    quote = " ".join(str(raw.get("quote", "")).split())
    if not quote or not _quote_in_text(quote, passage.text):
        return _PassageMeasurementValidation(
            code="source_quote_not_found",
            reason="The exact quote was not found in its retained source passage.",
        )
    expression = _validated_numeric_expression(raw.get("expression"))
    semantic_assessment = _validated_measurement_semantic_assessment(
        raw.get("semantic_assessment"),
        required_fields=_required_comparison_axes(target),
    )
    evidence_unit = _validated_evidence_unit_identity(raw.get("evidence_unit"))
    if (
        expression is None
    ):
        return _PassageMeasurementValidation(
            code="invalid_numeric_expression",
            reason="The normalized numeric expression did not satisfy its schema.",
        )
    if semantic_assessment is None:
        return _PassageMeasurementValidation(
            code="invalid_measurement_semantics",
            reason="Measurement semantics did not satisfy the target contract.",
        )
    if evidence_unit is None:
        return _PassageMeasurementValidation(
            code="invalid_evidence_unit",
            reason="Measurement evidence-unit identity did not satisfy the contract.",
        )
    source_record_id, source_identity_status = _source_record_identity(passage.finding)
    evidence_unit_id = _evidence_unit_key(source_record_id, evidence_unit)
    candidate_key = _MeasurementCandidateKey.from_validated(
        target_id=target.id,
        source_id=passage.id,
        quote=quote,
        expression=expression,
        evidence_unit_id=evidence_unit_id,
        evidence_unit=evidence_unit,
        semantic_assessment=semantic_assessment,
    )
    measurement = Measurement(
        expression=expression,
        candidate_id=candidate_key.candidate_id,
        url=passage.finding.url,
        insight_id=passage.insight.id,
        source_quote=quote,
        source_record_id=source_record_id,
        source_identity_status=source_identity_status,
        evidence_unit_id=evidence_unit_id,
        evidence_unit=evidence_unit,
        semantic_assessment=semantic_assessment,
    )
    measurement.semantic_status, measurement.semantic_reason = (
        _derived_semantic_status(measurement, target)
    )
    return _PassageMeasurementValidation(
        measurement=measurement,
        candidate_key=candidate_key,
    )


def _validated_evidence_unit_identity(raw: object) -> EvidenceUnitIdentity | None:
    try:
        wire = EvidenceUnitIdentityWire.model_validate(raw)
        return EvidenceUnitIdentity(
            status=wire.status,
            group=SemanticSlot(**wire.group.model_dump()),
            cohort=SemanticSlot(**wire.cohort.model_dump()),
            reason=wire.reason,
        )
    except (ValidationError, ValueError):
        return None


def _evidence_unit_key(
    source_record_id: str,
    identity: EvidenceUnitIdentity,
) -> str:
    """Build one deterministic within-record comparison-unit key.

    Unresolved identity deliberately collapses to record level. Resolved units
    distinguish only the source-stated group and cohort—not endpoint, timepoint,
    or statistic, which do not make repeated observations independent.
    """
    if identity.status != "resolved":
        return f"{source_record_id}/unit:record"

    def slot_value(slot: SemanticSlot) -> str:
        value = slot.value if slot.state == "specified" else slot.other
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    material = json.dumps(
        {
            "group": slot_value(identity.group),
            "cohort": slot_value(identity.cohort),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"{source_record_id}/unit:{digest}"


def _validated_ternary_decision(raw: object) -> TernaryDecision | None:
    try:
        wire = TernaryDecisionWire.model_validate(raw)
        return TernaryDecision(
            state=wire.state,
            reason=wire.reason,
        )
    except (ValidationError, ValueError):
        return None


def _validated_measurement_semantic_assessment(
    raw: object,
    *,
    required_fields: set[str],
) -> MeasurementSemanticAssessment | None:
    if not isinstance(raw, dict) or set(raw) != {
        "source_ownership",
        "dimensions",
    }:
        return None
    ownership = _validated_ternary_decision(raw.get("source_ownership"))
    dimensions_raw = raw.get("dimensions")
    if (
        ownership is None
        or not isinstance(dimensions_raw, dict)
        or not required_fields.issubset(dimensions_raw)
        or not set(dimensions_raw).issubset(QUANTITATIVE_SEMANTIC_FIELDS)
    ):
        return None
    dimensions: dict[str, SemanticDimensionAssessment] = {}
    for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
        item = dimensions_raw.get(field_name)
        if item is None and field_name not in required_fields:
            dimensions[field_name] = SemanticDimensionAssessment(
                source=SemanticSlot(state="not_specified"),
                compatibility=TernaryDecision(state="yes"),
            )
            continue
        if not isinstance(item, dict) or set(item) != {"source", "compatibility"}:
            return None
        source_profile = _validated_semantic_slot(item.get("source"))
        compatibility = _validated_ternary_decision(item.get("compatibility"))
        if source_profile is None or compatibility is None:
            return None
        dimensions[field_name] = SemanticDimensionAssessment(
            source=source_profile,
            compatibility=compatibility,
        )
    if dimensions["measure"].source.state not in {"specified", "other"}:
        return None
    return MeasurementSemanticAssessment(
        source_ownership=ownership,
        dimensions=dimensions,
    )


def _validated_semantic_slot(raw: object) -> SemanticSlot | None:
    try:
        wire = SemanticSlotWire.model_validate(raw)
        return SemanticSlot(
            state=wire.state,
            value=wire.value,
            other=wire.other,
        )
    except (ValidationError, ValueError):
        return None


def _required_comparison_axes(target: QuantitativeTarget) -> set[str]:
    """Return target dimensions whose compatibility is necessary for admission."""
    return set(target.comparison_dimensions)


def _derived_semantic_status(
    measurement: Measurement,
    target: QuantitativeTarget,
) -> tuple[str, str]:
    """Derive the public disposition from closed, auditable model decisions."""
    assessment = measurement.semantic_assessment
    ownership = assessment.source_ownership
    if ownership.state == "unknown":
        return "unknown", f"Source ownership is unknown: {ownership.reason}"
    if ownership.state == "no":
        return "contextual", f"The source does not own this result: {ownership.reason}"

    ambiguous_target_axes = [
        field_name
        for field_name, slot in target.semantic_profile.items()
        if slot.state == "unknown"
    ]
    if ambiguous_target_axes:
        return (
            "unknown",
            "The document target is ambiguous for: "
            + ", ".join(field_name.replace("_", " ") for field_name in ambiguous_target_axes),
        )

    required = _required_comparison_axes(target)
    for field_name in sorted(required):
        dimension = assessment.dimensions[field_name]
        source_slot = dimension.source
        decision = dimension.compatibility
        if source_slot.state not in {"specified", "other"}:
            return (
                "unknown",
                f"Required {field_name.replace('_', ' ')} context is absent from the source.",
            )
        if decision.state == "unknown":
            return (
                "unknown",
                f"{field_name.replace('_', ' ').capitalize()} compatibility is unknown: "
                f"{decision.reason}",
            )
        if decision.state == "no":
            status = "incompatible" if field_name == "measure" else "contextual"
            return (
                status,
                f"{field_name.replace('_', ' ').capitalize()} is not compatible: "
                f"{decision.reason}",
            )
    return (
        "comparable",
        "The source owns the result and every required target dimension is compatible.",
    )


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


def _validated_semantic_provenance(
    raw: object,
    profile: dict[str, SemanticSlot],
    context: str,
    allowed_ids: set[str],
    max_quote_chars: int | None = MAX_TARGET_QUOTE_CHARS,
) -> dict[str, list[DocumentSpan]] | None:
    """Require every asserted target dimension to cite exact document text."""
    if not isinstance(raw, dict) or set(raw) != set(QUANTITATIVE_SEMANTIC_FIELDS):
        return None
    output: dict[str, list[DocumentSpan]] = {}
    for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
        raw_spans = raw.get(field_name)
        if not isinstance(raw_spans, list):
            return None
        spans: list[DocumentSpan] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for item in raw_spans:
            if not isinstance(item, dict):
                continue
            quote = " ".join(str(item.get("quote", "")).split())
            block_ids = validated_block_ids(item.get("block_ids"), allowed_ids)
            key = (_normalize_quote(quote), tuple(block_ids))
            if (
                not quote
                or not block_ids
                or (max_quote_chars is not None and len(quote) > max_quote_chars)
                or key in seen
                or not _quote_in_text(quote, _text_for_blocks(context, block_ids))
            ):
                continue
            seen.add(key)
            spans.append(DocumentSpan(quote=quote, block_ids=block_ids))
        if profile[field_name].state in {"specified", "other"} and not spans:
            return None
        if profile[field_name].state not in {"specified", "other"} and spans:
            return None
        output[field_name] = spans
    return output


def _validated_numeric_expression(raw: object) -> NumericExpression | None:
    """Parse the model-owned normalized value through its typed calculation shape."""
    try:
        wire = NumericExpressionWire.model_validate(raw)
        return NumericExpression(
            **wire.model_dump()
        )
    except (ValidationError, TypeError, ValueError):
        return None


def _measurement_system_prompt(
    attribute: Attribute,
    *,
    target: QuantitativeTarget,
    indication: str,
    intervention_class: str,
) -> str:
    required_fields = sorted(_required_comparison_axes(target))
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
        "Every target dimension above is independently grounded in the uploaded document.\n\n"
        "Each source has an immutable ID and one retained source passage. Return EXACTLY ONE "
        "source decision for EVERY ID: measurements_found, no_relevant_measurement, or uncertain. "
        "Do not enumerate every number. Extract only complete statements that measure the target "
        "or a meaningfully related quantity. Each extracted measurement must contain the shortest "
        "self-contained exact quote that explicitly connects the number to the measured outcome "
        "or property and preserves its qualifiers, plus one normalized expression object. "
        "Also return evidence_unit for the distinct source group that owns the measurement. "
        "Use status=resolved only when the passage explicitly distinguishes that arm or cohort from "
        "another non-overlapping comparison arm or cohort in the same source record. Put that identity "
        "in group and cohort; these labels describe who contributed the observation, not its endpoint, "
        "timepoint, statistic, or analysis method. Use record_level when the source reports only one "
        "aggregate group, even when that population is described. Use uncertain when groups may overlap or the passage suggests multiple groups but "
        "does not identify which one owns the value. Do not invent arm or cohort names. "
        "expression is your normalized semantic reading of the exact quote. Convert written "
        "quantities and directional prose into the typed numeric schema without inventing or "
        "changing the reported magnitude. Use the document "
        "target unit exactly when the source has the same unit meaning; otherwise retain a concise "
        "canonical source unit so code excludes it from direct statistics. A dose, exposure "
        "condition, storage temperature, visit time, follow-up duration, or sample size alone is "
        "NOT an outcome measurement. For example, 'stored for 6 weeks at 60 C' is not evidence of "
        "thermostability unless the same contiguous quote also states what stability, potency, or "
        "performance was retained. Do not import that missing meaning from a title, an Insight, or "
        "your background knowledge. If the retained passage cannot supply one self-contained exact "
        "span, return uncertain rather than a measurement. "
        "Expression kind is point_estimate|range|bound|confidence_interval|count|rate|other|unknown. "
        "point_estimate/count/rate use value; range/confidence_interval use lower+upper; bound uses "
        "value+comparator. Never split a range or confidence interval into point estimates. "
        "Do NOT return an aggregate comparable/contextual label. Instead return ONE "
        "semantic_assessment. source_ownership.state is yes only when the numeric claim is a result or record fact "
        "owned by this exact source record. Use no for another study's result quoted as background, "
        "general background, a protocol assumption, a planned outcome, or an unsupported assertion; "
        "use unknown when ownership cannot be established. A registry sentence can appear verbatim "
        "yet still be background rather than a result of that registered study. "
        f"Inside dimensions return exactly the target-constrained fields: {json.dumps(required_fields)}. "
        "Do not assess unconstrained fields: they cannot affect this cohort. Each returned field contains source={state,value,other} "
        "and compatibility={state,reason}. Compatibility yes means the source value is semantically "
        "compatible with that target "
        "dimension for direct numeric comparison; it does not require identical wording. no means a "
        "material conflict. unknown means the retained passage lacks enough context. In particular, "
        "clinical disease is not the same endpoint as infection or parasitemia, and a follow-up "
        "window is not automatically the same as a point estimate at its endpoint. The magnitude of "
        "the number and whether it would meet the hidden target are NEVER relevance criteria. "
        "Use a concise reason for every no or unknown decision; "
        "yes decisions may use an empty reason. Do not infer a qualifier absent from the supplied source "
        "context. Code, not "
        "you, derives the final cohort disposition from these decisions.\n\n"
        "Use no_relevant_measurement when the passage contains no relevant complete numeric "
        "statement. Use uncertain when one may exist but the supplied passage cannot support a "
        "faithful mapping. Never infer omitted context. Return only the schema-bound response."
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


def _normalize_quote(value: str) -> str:
    return " ".join(html.unescape(value).split()).casefold()


def _quote_in_text(quote: str, source_text: str) -> bool:
    normalized_quote = _normalize_quote(quote)
    return bool(normalized_quote) and normalized_quote in _normalize_quote(source_text)


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


def _unit_key(unit: str) -> str:
    """Compare AI-produced unit identifiers without reinterpreting source text."""
    return re.sub(r"\s+", "", unit.strip().casefold().replace("⁄", "/"))
