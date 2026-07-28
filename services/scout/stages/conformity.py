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
    quantitative_claim_reconciliation,
    source_measurement_batch,
)
from ..ai_wire import (
    EvidenceUnitIdentityWire,
    EvidenceUnitPartitionWire,
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
    ComparisonRule,
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
    QuantitativeFieldLink,
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
LEDGER_RETRY_MAX_UNITS = 4
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
    """One source block interpreted once across all relevant fields."""

    id: str
    block_id: str
    quote: str
    candidate_attribute_refs: tuple[str, ...] = ()


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
    response_failure_unit_ids: set[str]


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
class _ValidatedSourceDecision:
    """One structurally valid passage decision pending record-wide validation."""

    source_id: str
    passage: _SourcePassage
    status: str
    reason: str
    partition: EvidenceUnitPartitionWire
    measurements: tuple[Measurement, ...]


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

    linked_attributes: tuple[Attribute, ...]
    target: QuantitativeTarget
    passages: list[_SourcePassage]


@dataclass(frozen=True)
class _CalibrationBatchResult:
    measurements: list[Measurement]
    dispositions: list[SourcePassageDisposition]


def score_conformity(
    attribute: Attribute,
    targets: list[QuantitativeTarget],
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[ConformityScore]:
    """Calibrate canonical targets linked to this field view."""
    scores: list[ConformityScore] = []
    for target in targets:
        if attribute.name not in target.analysis_attribute_refs:
            continue
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
    targets: list[QuantitativeTarget],
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
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    target_order: list[tuple[QuantitativeTarget, list[Insight]]] = []
    tasks: list[_CalibrationTask] = []
    for target in targets:
        linked_attributes = [
            attributes_by_name[ref]
            for ref in target.analysis_attribute_refs
            if ref in attributes_by_name
        ]
        if not linked_attributes:
            continue
        insights = list({
            insight.id: insight
            for linked in linked_attributes
            for insight in insights_by_attribute.get(linked.name, [])
        }.values())
        passages = _source_passages(insights)
        target_order.append((target, insights))
        tasks.extend(
            _CalibrationTask(
                linked_attributes=tuple(linked_attributes),
                target=target,
                passages=batch,
            )
            for batch in _source_passage_batches(passages)
        )

    total = len(tasks)
    if progress_callback and total:
        progress_callback(0, total)
    completed = 0
    progress_lock = threading.Lock()

    def run(task: _CalibrationTask) -> _CalibrationBatchResult:
        nonlocal completed
        result = _map_source_passage_batch(
            task.linked_attributes,
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

    mapped: dict[str, tuple[list[Measurement], list[SourcePassageDisposition]]] = {}
    for task, result in zip(tasks, batch_results):
        key = task.target.id
        measurements, dispositions = mapped.setdefault(key, ([], []))
        measurements.extend(result.measurements)
        dispositions.extend(result.dispositions)

    scores: list[ConformityScore] = []
    for target, insights in target_order:
        candidates, dispositions = mapped.get(
            target.id,
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
    targets: list[QuantitativeTarget],
) -> list[ConformityScore]:
    """Project verified targets when retrieval yields no numeric evidence."""
    return [
        _empty_score(target, [], [])
        for target in targets
    ]


def _empty_score(
    target: QuantitativeTarget,
    excluded_measurements: list[Measurement],
    source_dispositions: list[SourcePassageDisposition],
) -> ConformityScore:
    return ConformityScore(
        attribute_refs=target.analysis_attribute_refs,
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
        attribute_refs=target.analysis_attribute_refs,
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
    """Batch document-centric source units from the canonical claim ledger.

    Every cited block is interpreted once even when several canonical fields
    reference it. Candidate fields express upstream relevance only; the model
    creates typed field links without assigning ownership to any field.

    ``attributes=None`` remains a narrow compatibility path for focused legacy
    tests; production always supplies the resolved canonical attributes.
    """
    block_by_id = {block.id: block for block in blocks}
    units: list[QuantitativeStatementUnit] = []
    if attributes is None:
        for block in blocks:
            for unit in _statement_units(block):
                units.append(unit)
    else:
        candidates_by_block: dict[str, list[str]] = {}
        for attribute in attributes:
            if not attribute.target_resolved or not attribute.document_target:
                continue
            for span in attribute.document_spans:
                for block_id in span.block_ids:
                    if block_id in block_by_id:
                        candidates_by_block.setdefault(block_id, []).append(attribute.name)
        for block in blocks:
            candidate_refs = tuple(dict.fromkeys(candidates_by_block.get(block.id, [])))
            if not candidate_refs:
                continue
            quote = block.content or "[visual content]"
            units.append(
                QuantitativeStatementUnit(
                    id="qlu-" + hashlib.sha256(block.id.encode("utf-8")).hexdigest()[:16],
                    block_id=block.id,
                    quote=quote,
                    candidate_attribute_refs=candidate_refs,
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
    resolved_attribute_refs = [
        attribute.name
        for attribute in attributes
        if attribute.target_resolved and attribute.document_target
    ]
    system_prompt = _document_ledger_system_prompt(
        attributes,
        canonical_bindings=canonical_bindings,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
    )
    def request(
        current: QuantitativeLedgerBatch,
        feedback: dict[str, str] | None = None,
    ) -> object | None:
        contract = document_quantitative_ledger_batch(
            [binding.ref for binding in canonical_bindings],
            [unit.id for unit in current.units],
            resolved_attribute_refs,
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
        images = [
            {"block_id": block.id, "data_url": block.image.data_url()}
            for block in current.blocks
            if block.image
        ] or None
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
    retry_feedback = {
        review.unit_id: review.reason
        for review in first.result.reviews
        if review.unit_id in first.retry_unit_ids
    }
    retry_results: list[QuantitativeLedgerBatchResult] = []
    retry_response_failures: set[str] = set()
    for retry_batch in _quantitative_retry_batches(
        batch,
        first.retry_unit_ids,
    ):
        retry = _validated_quantitative_ledger_batch(
            request(
                retry_batch,
                {
                    unit.id: retry_feedback[unit.id]
                    for unit in retry_batch.units
                },
            ),
            batch=retry_batch,
            attributes=attributes,
            canonical_bindings=canonical_bindings,
        )
        retry_results.append(retry.result)
        retry_response_failures.update(retry.response_failure_unit_ids)
    if retry_response_failures:
        raise ValueError(
            "Quantitative mapping returned incomplete schema-bound decisions "
            f"for {len(retry_response_failures)} statement(s) after one targeted retry."
        )
    retry_result = QuantitativeLedgerBatchResult(
        reviews=[
            review for result in retry_results for review in result.reviews
        ],
        targets=[
            target for result in retry_results for target in result.targets
        ],
    )
    first_reviews = {review.unit_id: review for review in first.result.reviews}
    retry_reviews = {review.unit_id: review for review in retry_result.reviews}
    review_by_id: dict[str, QuantitativeLedgerReview] = {}
    for unit in batch.units:
        first_review = first_reviews[unit.id]
        if unit.id not in first.retry_unit_ids:
            review_by_id[unit.id] = first_review
            continue
        review_by_id[unit.id] = _merge_quantitative_retry_review(
            first_review,
            retry_reviews[unit.id],
        )
    merged_reviews = [review_by_id[unit.id] for unit in batch.units]
    retained_target_ids = {
        target_id for review in merged_reviews for target_id in review.target_ids
    }
    merged_targets = _merge_document_targets(
        [*first.result.targets, *retry_result.targets]
    )
    return QuantitativeLedgerBatchResult(
        reviews=merged_reviews,
        targets=[
            target for target in merged_targets if target.id in retained_target_ids
        ],
    )


def _quantitative_retry_batches(
    batch: QuantitativeLedgerBatch,
    retry_unit_ids: set[str],
) -> list[QuantitativeLedgerBatch]:
    """Retry failed decisions once with only their source-owned blocks."""
    block_by_id = {block.id: block for block in batch.blocks}
    retry_units = [
        unit for unit in batch.units if unit.id in retry_unit_ids
    ]
    retries: list[QuantitativeLedgerBatch] = []
    for start in range(0, len(retry_units), LEDGER_RETRY_MAX_UNITS):
        units = retry_units[start:start + LEDGER_RETRY_MAX_UNITS]
        blocks = [
            block_by_id[block_id]
            for block_id in dict.fromkeys(unit.block_id for unit in units)
            if block_id in block_by_id
        ]
        retries.append(QuantitativeLedgerBatch(units=units, blocks=blocks))
    return retries


def _merge_quantitative_retry_review(
    first: QuantitativeLedgerReview,
    retry: QuantitativeLedgerReview,
) -> QuantitativeLedgerReview:
    """Merge one retried source statement without discarding valid siblings."""
    target_ids = list(dict.fromkeys([*first.target_ids, *retry.target_ids]))
    attribute_refs = list(dict.fromkeys([
        *first.attribute_refs,
        *retry.attribute_refs,
    ]))
    if retry.classification == "target" and retry.review_status == "resolved":
        return replace(
            retry,
            target_ids=target_ids,
            attribute_refs=attribute_refs,
        )
    if not target_ids:
        return retry
    return QuantitativeLedgerReview(
        unit_id=retry.unit_id,
        block_id=retry.block_id,
        quote=retry.quote,
        classification="partial_target",
        reason=(
            "Source-verifiable targets were retained, but another proposed mapping "
            f"from this statement remains unresolved. {retry.reason}"
        ),
        attribute_refs=attribute_refs,
        target_ids=target_ids,
        review_status="needs_review",
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
    response_failure_unit_ids: set[str] = set()
    for unit in batch.units:
        raw = by_id.get(unit.id)
        if raw is None or unit.id in duplicate_ids:
            retry_unit_ids.add(unit.id)
            response_failure_unit_ids.add(unit.id)
            reviews.append(
                _uncertain_unit_review(
                    unit,
                    "The model did not return one unique review for this statement.",
                )
            )
            continue
        classification = str(raw.get("classification", "")).strip().lower()
        reason = " ".join(str(raw.get("reason", "")).split())
        attribute_refs = list(dict.fromkeys(
            str(value).strip()
            for value in raw.get("attribute_refs", [])
            if str(value).strip()
        ))
        raw_targets = raw.get("targets")
        raw_targets = raw_targets if isinstance(raw_targets, list) else []
        if (
            classification not in {
                "target", "context_only", "non_scalar", "range_or_set",
                "non_numeric", "uncertain",
            }
            or not reason
            or not set(attribute_refs).issubset(attributes_by_name)
        ):
            retry_unit_ids.add(unit.id)
            response_failure_unit_ids.add(unit.id)
            reviews.append(
                _uncertain_unit_review(
                    unit,
                    "The model returned an invalid statement classification.",
                    attribute_refs=[
                        ref for ref in attribute_refs if ref in attributes_by_name
                    ],
                )
            )
            continue

        if classification != "target":
            if raw_targets:
                retry_unit_ids.add(unit.id)
                response_failure_unit_ids.add(unit.id)
                reviews.append(
                    _uncertain_unit_review(
                        unit,
                        "A non-target statement incorrectly carried target objects.",
                        attribute_refs=attribute_refs,
                    )
                )
                continue
            if classification == "non_numeric":
                attribute_refs = []
            reviews.append(
                QuantitativeLedgerReview(
                    unit_id=unit.id,
                    block_id=unit.block_id,
                    quote=unit.quote,
                    classification=classification,
                    attribute_refs=attribute_refs,
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
            field_links = _validated_document_field_links(
                raw_target.get("field_links"),
                attributes_by_name,
            )
            if field_links is None:
                validation_issues.append("invalid_field_links")
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
            candidate["field_links"] = field_links
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
            mapping = _validated_targets_with_issues(
                [candidate],
                doc_text=batch_text,
                semantic_context=semantic_context,
                allowed_target_block_ids={unit.block_id} & batch_block_ids,
                canonical_semantic_provenance=True,
            )
            if len(mapping.targets) != 1:
                validation_issues.extend(mapping.issues or ("invalid_target_mapping",))
                continue
            validated.extend(mapping.targets)
        target_ids = [target.id for target in validated]
        if len(target_ids) != len(set(target_ids)):
            validation_issues.append("duplicate_atomic_target")
            validated = list({target.id: target for target in validated}.values())
        if validation_issues:
            retry_unit_ids.add(unit.id)
            issue_text = _target_mapping_issue_text(
                validation_issues or ["missing_target_mapping"]
            )
            if validated:
                targets.extend(validated)
                validated_attribute_refs = list(dict.fromkeys(
                    ref for target in validated for ref in target.attribute_refs
                ))
                reviews.append(
                    QuantitativeLedgerReview(
                        unit_id=unit.id,
                        block_id=unit.block_id,
                        quote=unit.quote,
                        classification="partial_target",
                        reason=(
                            f"Retained {len(validated)} source-verifiable target(s); "
                            f"another proposed mapping was rejected [{issue_text}]."
                        ),
                        attribute_refs=list(dict.fromkeys([
                            *validated_attribute_refs,
                            *(ref for ref in attribute_refs if ref in attributes_by_name),
                        ])),
                        target_ids=[target.id for target in validated],
                        review_status="needs_review",
                    )
                )
            else:
                reviews.append(
                    _uncertain_unit_review(
                        unit,
                        f"Target mapping rejected [{issue_text}].",
                        attribute_refs=[
                            ref for ref in attribute_refs if ref in attributes_by_name
                        ],
                    )
                )
            continue
        if not validated:
            retry_unit_ids.add(unit.id)
            reviews.append(
                _uncertain_unit_review(
                    unit,
                    "Target mapping rejected [missing_target_mapping].",
                    attribute_refs=[
                        ref for ref in attribute_refs if ref in attributes_by_name
                    ],
                )
            )
            continue
        targets.extend(validated)
        validated_attribute_refs = list(dict.fromkeys(
            ref for target in validated for ref in target.attribute_refs
        ))
        reviews.append(
            QuantitativeLedgerReview(
                unit_id=unit.id,
                block_id=unit.block_id,
                quote=unit.quote,
                classification="target",
                reason=reason,
                attribute_refs=validated_attribute_refs,
                target_ids=[target.id for target in validated],
                review_status="resolved",
            )
        )
    return _QuantitativeBatchValidation(
        result=QuantitativeLedgerBatchResult(reviews=reviews, targets=targets),
        retry_unit_ids=retry_unit_ids,
        response_failure_unit_ids=response_failure_unit_ids,
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
    unresolved_classifications = {"uncertain", "partial_target"}
    unresolved_count = sum(
        review.classification in unresolved_classifications for review in reviews
    )
    attribute_names = {attribute.name for attribute in attributes}
    owned_block_ids = {
        block_id for attribute in attributes for block_id in attribute.block_ids
    }
    target_context_uncertain_count = sum(
        review.classification in unresolved_classifications
        and (
            bool(set(review.attribute_refs) & attribute_names)
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
        f"numeric statements; {unresolved_count} statements have an unresolved remainder, "
        f"including {target_context_uncertain_count} in target-bearing document "
        "context. Unresolved remainders are excluded from target-specific retrieval "
        "and calibration; independently validated sibling targets remain eligible."
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


def reconcile_quantitative_document_ledger(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int = 6000,
) -> tuple[list[Attribute], QuantitativeLedger]:
    """Merge document-wide semantic duplicates before independent review.

    The model may only partition existing IDs and select a representative.
    Code restricts comparison to claims with identical calculation inputs,
    then combines declared field links and exact provenance without parsing
    prose or changing numeric meaning.
    """
    candidate_targets = _reconciliation_candidates(ledger.targets)
    if len(candidate_targets) < 2:
        return attributes, ledger
    allowed_ids = [target.id for target in candidate_targets]
    contract = quantitative_claim_reconciliation(allowed_ids)
    prompt = (
        "ROLE\n"
        "You reconcile an already-normalized document claim ledger. You may partition only "
        "the supplied target IDs and select an existing representative; you cannot rewrite "
        "targets, semantic mappings, field links, or provenance.\n\n"
        "GROUPING RULES\n"
        "Group targets only "
        "when they express the same atomic document requirement repeated or paraphrased "
        "in different passages. Equal numbers alone are not sufficient: keep different "
        "roles, populations, regimens, endpoints, time horizons, or operating conditions "
        "separate. Their direct-comparator contracts must also describe the same admissible "
        "cohort; do not merge targets whose comparison scope materially differs. Field names "
        "are views and must not prevent a merge. For each group, "
        "choose the member with the clearest and most generally faithful comparison identity "
        "as representative.\n\n"
        "OUTPUT\n"
        "Return every supplied target ID exactly once, including singleton groups, and give "
        "each group a short reason. Return only the schema-bound response."
    )
    payload = json.dumps(
        [_reconciliation_payload(target) for target in candidate_targets],
        ensure_ascii=False,
        indent=2,
    )

    def request(message: str) -> object | None:
        try:
            return request_structured(
                llm_client,
                contract,
                prompt,
                message,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning(
                "Quantitative claim reconciliation failed; retaining claims unchanged: %s",
                exc,
            )
            return None

    parsed = request(payload)
    groups = _validated_reconciliation_groups(
        parsed,
        candidate_targets=candidate_targets,
    )
    if groups is None:
        parsed = request(
            payload
            + "\n\nThe prior response did not partition every supplied ID exactly once. "
            "Return a complete partition using only the supplied IDs.",
        )
        groups = _validated_reconciliation_groups(
            parsed,
            candidate_targets=candidate_targets,
        )
    if groups is None:
        logger.warning(
            "Quantitative claim reconciliation returned an invalid partition; "
            "retaining the source-verifiable claims unchanged"
        )
        return attributes, ledger

    targets_by_id = {target.id: target for target in ledger.targets}
    member_to_representative = {
        member_id: representative_id
        for representative_id, member_ids, _reason in groups
        for member_id in member_ids
    }
    merged_by_representative = {
        representative_id: _merge_reconciled_targets(
            targets_by_id[representative_id],
            [targets_by_id[member_id] for member_id in member_ids],
        )
        for representative_id, member_ids, _reason in groups
    }
    reconciled_targets: list[QuantitativeTarget] = []
    emitted: set[str] = set()
    for target in ledger.targets:
        representative_id = member_to_representative.get(target.id, target.id)
        if representative_id in emitted:
            continue
        emitted.add(representative_id)
        reconciled_targets.append(
            merged_by_representative.get(representative_id, target)
        )
    reconciled_reviews = [
        replace(
            review,
            target_ids=list(
                dict.fromkeys(
                    member_to_representative.get(target_id, target_id)
                    for target_id in review.target_ids
                )
            ),
        )
        for review in ledger.reviews
    ]
    merged_count = len(candidate_targets) - len(groups)
    reconciled = replace(
        ledger,
        targets=reconciled_targets,
        reviews=reconciled_reviews,
        reason=(
            ledger.reason
            + f" Reconciled {merged_count} repeated target representation(s) "
            "document-wide before review."
        ),
    )
    return _project_ledger_to_attributes(attributes, reconciled), reconciled


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
                    candidate_attribute_refs=(),
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
                candidate_attribute_refs=(),
            )
        )
    return units


def _uncertain_unit_review(
    unit: QuantitativeStatementUnit,
    reason: str,
    *,
    attribute_refs: list[str] | None = None,
) -> QuantitativeLedgerReview:
    return QuantitativeLedgerReview(
        unit_id=unit.id,
        block_id=unit.block_id,
        quote=unit.quote,
        classification="uncertain",
        reason=reason,
        attribute_refs=attribute_refs or [],
        review_status="needs_review",
    )


def _merge_document_targets(
    targets: list[QuantitativeTarget],
) -> list[QuantitativeTarget]:
    """Merge repeated citations of one already-normalized canonical target.

    Duplicate atomic outputs inside one source unit are rejected before this
    boundary. Here, an identical target ID represents the same normalized
    assertion repeated in another cited block; provenance and field views are
    combined without creating a second statistical target.
    """
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
            field_links=list({
                (link.attribute_ref, link.relation): link
                for link in [*existing.field_links, *target.field_links]
            }.values()),
            provenance_spans=spans,
            semantic_provenance=semantic_provenance,
            id=existing.id,
        )
    return list(merged.values())


def _reconciliation_signature(target: QuantitativeTarget) -> tuple[object, ...]:
    """Return calculation inputs that must already agree before semantic merging."""
    return (
        target.expression.kind,
        target.comparator,
        target.value,
        target.unit.casefold(),
        target.role,
    )


def _reconciliation_candidates(
    targets: list[QuantitativeTarget],
) -> list[QuantitativeTarget]:
    by_signature: dict[tuple[object, ...], list[QuantitativeTarget]] = {}
    for target in targets:
        by_signature.setdefault(_reconciliation_signature(target), []).append(target)
    candidate_ids = {
        target.id
        for group in by_signature.values()
        if len(group) > 1
        for target in group
    }
    return [target for target in targets if target.id in candidate_ids]


def _reconciliation_payload(target: QuantitativeTarget) -> dict[str, object]:
    return {
        "target_id": target.id,
        "expression": {
            "comparator": target.comparator,
            "value": target.value,
            "unit": target.unit,
        },
        "role": target.role,
        "comparison_contract": {
            name: {
                "mode": rule.mode,
                "scope": rule.scope,
                "reason": rule.reason,
            }
            for name, rule in target.comparison_contract.items()
        },
        "semantic_profile": {
            name: {
                "state": slot.state,
                "value": slot.value,
                "other": slot.other,
            }
            for name, slot in target.semantic_profile.items()
        },
        "field_links": [
            {
                "attribute_ref": link.attribute_ref,
                "relation": link.relation,
                "reason": link.reason,
            }
            for link in target.field_links
        ],
        "source_passages": [
            {"quote": span.quote, "block_ids": span.block_ids}
            for span in target.provenance_spans
        ],
    }


def _validated_reconciliation_groups(
    parsed: object,
    *,
    candidate_targets: list[QuantitativeTarget],
) -> list[tuple[str, list[str], str]] | None:
    if not isinstance(parsed, list):
        return None
    targets_by_id = {target.id: target for target in candidate_targets}
    expected_ids = set(targets_by_id)
    seen: set[str] = set()
    groups: list[tuple[str, list[str], str]] = []
    for raw in parsed:
        if not isinstance(raw, dict):
            return None
        representative_id = str(raw.get("representative_target_id", "")).strip()
        raw_member_ids = raw.get("member_target_ids")
        reason = " ".join(str(raw.get("reason", "")).split())
        if not isinstance(raw_member_ids, list):
            return None
        member_ids = list(
            dict.fromkeys(
                str(value).strip()
                for value in raw_member_ids
                if str(value).strip()
            )
        )
        if (
            not reason
            or representative_id not in member_ids
            or not member_ids
            or not set(member_ids).issubset(expected_ids)
            or seen.intersection(member_ids)
        ):
            return None
        signatures = {
            _reconciliation_signature(targets_by_id[target_id])
            for target_id in member_ids
        }
        if len(signatures) != 1:
            return None
        seen.update(member_ids)
        groups.append((representative_id, member_ids, reason))
    return groups if seen == expected_ids else None


def _merge_reconciled_targets(
    representative: QuantitativeTarget,
    members: list[QuantitativeTarget],
) -> QuantitativeTarget:
    relation_priority = {"defines": 0, "constrains": 1, "context_for": 2}
    links_by_field: dict[str, QuantitativeFieldLink] = {}
    for target in members:
        for link in target.field_links:
            current = links_by_field.get(link.attribute_ref)
            if (
                current is None
                or relation_priority[link.relation]
                < relation_priority[current.relation]
            ):
                links_by_field[link.attribute_ref] = link
    provenance_spans = list({
        (span.quote, tuple(span.block_ids)): span
        for target in members
        for span in target.provenance_spans
    }.values())
    semantic_provenance: dict[str, list[DocumentSpan]] = {}
    for field_name, representative_slot in representative.semantic_profile.items():
        if representative_slot.state not in {"specified", "other"}:
            semantic_provenance[field_name] = []
            continue
        semantic_provenance[field_name] = list({
            (span.quote, tuple(span.block_ids)): span
            for target in members
            for span in target.semantic_provenance.get(field_name, [])
        }.values())
    return replace(
        representative,
        field_links=list(links_by_field.values()),
        provenance_spans=provenance_spans,
        semantic_provenance=semantic_provenance,
        id=representative.id,
    )


def _project_ledger_to_attributes(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    *,
    admitted_statuses: set[str] | None = None,
) -> list[Attribute]:
    target_ids_by_attribute: dict[str, list[str]] = {
        attribute.name: [] for attribute in attributes
    }
    for target in ledger.targets:
        if admitted_statuses is None or target.review_status in admitted_statuses:
            for attribute_ref in target.analysis_attribute_refs:
                if attribute_ref in target_ids_by_attribute:
                    target_ids_by_attribute[attribute_ref].append(target.id)
    attributes_by_block: dict[str, set[str]] = {}
    for attribute in attributes:
        for block_id in attribute.block_ids:
            attributes_by_block.setdefault(block_id, set()).add(attribute.name)
    dispositions_by_attribute: dict[str, list[QuantitativeStatementDisposition]] = {
        attribute.name: [] for attribute in attributes
    }
    for review in ledger.reviews:
        if (
            review.attribute_refs
            and review.classification
            in {"context_only", "non_scalar", "range_or_set", "uncertain"}
        ):
            for attribute_ref in review.attribute_refs:
                if attribute_ref not in dispositions_by_attribute:
                    continue
                dispositions_by_attribute[attribute_ref].append(
                    QuantitativeStatementDisposition(
                        quote=review.quote,
                        block_ids=[review.block_id],
                        disposition=review.classification,
                        reason=review.reason,
                        attribute_refs=review.attribute_refs,
                    )
                )
    uncertain_attribute_refs: set[str] = set()
    for review in ledger.reviews:
        if review.classification not in {"uncertain", "partial_target"}:
            continue
        if review.attribute_refs:
            uncertain_attribute_refs.update(review.attribute_refs)
        else:
            uncertain_attribute_refs.update(
                attributes_by_block.get(review.block_id, set())
            )
    projected: list[Attribute] = []
    for attribute in attributes:
        target_ids = target_ids_by_attribute[attribute.name]
        dispositions = dispositions_by_attribute[attribute.name]
        if target_ids:
            status = "present"
            status_reason = (
                f"The document ledger linked {len(target_ids)} independently "
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
                quantitative_target_ids=target_ids,
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
        if attribute.target_resolved and attribute.document_target
    ) or "(No resolved canonical fields.)"
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
        "ROLE\n"
        "You create quantitative proposals from the authoritative document-claim ledger. "
        "Each supplied unit is one source block and lists every canonical field that already "
        "cites that block. Those fields are candidate product views, never claim owners. "
        "Interpret the unit once and create one atomic target regardless of how many fields "
        "expose it. Link fields with defines when the statement directly specifies that field, "
        "constrains when it imposes a requirement on it, or context_for when it is useful but "
        "does not define or constrain it. Every target needs at least one defines or constrains "
        "link. Each unit must "
        "appear exactly once in reviews.\n\n"
        "AUTHORITATIVE CONTEXT\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Document framing: {framing}\n\n"
        "Canonical fields:\n"
        f"{field_catalog}\n\n"
        "Canonical document bindings (authoritative cross-block context):\n"
        f"{binding_catalog}\n\n"
        "UNIT CLASSIFICATION\n"
        "For every unit choose target, context_only, non_scalar, range_or_set, "
        "non_numeric, or uncertain. Use uncertain instead of guessing. A target is an "
        "explicit exact or directional scalar that can be compared independently. Split "
        "distinct roles, populations, regimens, time horizons, and semicolon-delimited "
        "claims into atomic target objects. A unit may contain multiple target objects. "
        "For each target choose field_links from the canonical field catalog. The unit's "
        "candidate fields are strong relevance cues, not an ownership boundary; use another "
        "resolved field only when the authoritative bindings make that relationship explicit. Never emit "
        "the same atomic assertion again for another field. For a non-target, attribute_refs "
        "lists every field for which the disposition is relevant and may be empty. A [visual "
        "content] unit may be classified non_numeric when "
        "the image has no numeric claim; otherwise classify it uncertain because it has "
        "no exact source text from which a target can be verified.\n\n"
        "TARGET EXTRACTION\n"
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
        "semantic_profile records only what the document says. comparison_contract separately "
        "defines what external evidence may vary and still be a direct comparator. Return one "
        "rule for every semantic slot. mode=exact means the same semantic concept and entity "
        "scope are required; mode=compatible means named entities or details may differ within "
        "the stated scope; mode=unconstrained means the slot does not control admission; and "
        "mode=unknown preserves genuine ambiguity for review. measure must be specified in the "
        "semantic profile and its comparison mode must be exact. For semantic slots, specified "
        "requires a non-empty value and empty other; other requires non-empty other and empty "
        "value; not_specified and unknown require both value and other to be empty. For comparison "
        "rules, exact and compatible require a non-empty scope; unconstrained requires an empty "
        "scope; unknown requires a non-empty reason. Do not make "
        "intervention exact merely because the document names its candidate: external comparator "
        "cohorts normally contain different products. Use compatible with a clear class/use scope "
        "when cross-product comparison is scientifically meaningful. Use exact only when a value "
        "is valid solely for that exact entity. The scope is threshold-neutral and must never "
        "encode whether evidence passes the target. For every "
        "semantic slot, source_refs must identify where its "
        "meaning came from: statement for the reviewed unit, or one or more exact "
        "[context:<ref>] bindings above. Asserted slots require at least one source_ref; "
        "unasserted slots require none. Conditions includes only settings that change numeric "
        "interpretation. Do not judge whether external evidence passes the target.\n\n"
        "OUTPUT\n"
        "For non-target reviews targets must be empty. For target reviews include every "
        "atomic target in the unit. Copy unit IDs exactly. Return only the schema-bound response."
    )


def _document_ledger_user_message(batch: QuantitativeLedgerBatch) -> str:
    units = "\n".join(
        f"[unit:{unit.id}] [candidate-fields:{', '.join(unit.candidate_attribute_refs)}] "
        f"[block:{unit.block_id}] {unit.quote}"
        for unit in batch.units
    )
    return (
        "AUTHORITATIVE SOURCE BLOCKS\n"
        f"{render_document_context(batch.blocks)}\n\n"
        "STATEMENT UNITS TO REVIEW\n"
        f"{units}"
    )


def _validated_targets(
    items: object,
    *,
    doc_text: str,
    semantic_context: str,
    allowed_target_block_ids: set[str] | None = None,
    canonical_semantic_provenance: bool = False,
) -> list[QuantitativeTarget]:
    """Compatibility wrapper for callers that only need admitted targets."""
    return _validated_targets_with_issues(
        items,
        doc_text=doc_text,
        semantic_context=semantic_context,
        allowed_target_block_ids=allowed_target_block_ids,
        canonical_semantic_provenance=canonical_semantic_provenance,
    ).targets


def _validated_targets_with_issues(
    items: object,
    *,
    doc_text: str,
    semantic_context: str,
    allowed_target_block_ids: set[str] | None = None,
    canonical_semantic_provenance: bool = False,
) -> _TargetMappingValidation:
    if not isinstance(items, list):
        return _TargetMappingValidation([], ("invalid_target_list",))
    # A target is an exact document fact. Field links classify product views;
    # they do not own or authorize the source assertion.
    rendered_ids = document_block_ids(doc_text)
    allowed_ids = (
        set(allowed_target_block_ids)
        if allowed_target_block_ids is not None
        else set(rendered_ids)
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
        comparison_contract = _validated_comparison_contract(
            item.get("comparison_contract")
        )
        semantic_profile = _validated_semantic_profile(item.get("semantic_profile"))
        raw_links = item.get("field_links")
        if not isinstance(raw_links, list):
            issues.append("missing_field_links")
            continue
        try:
            field_links = [
                value
                if isinstance(value, QuantitativeFieldLink)
                else QuantitativeFieldLink(**value)
                for value in raw_links
            ]
        except (TypeError, ValueError):
            issues.append("invalid_field_links")
            continue
        semantic_issues: list[str] = []
        if expression is None:
            semantic_issues.append("invalid_target_expression")
        elif expression.kind != "bound":
            semantic_issues.append("target_expression_must_be_bound")
        if role not in VALID_TARGET_ROLES:
            semantic_issues.append("invalid_target_role")
        if semantic_profile is None:
            semantic_issues.append("invalid_target_semantic_profile")
        if comparison_contract is None:
            semantic_issues.append("invalid_target_comparison_contract")
        if semantic_issues:
            issues.extend(semantic_issues)
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
        target = QuantitativeTarget(
            field_links=field_links,
            expression=expression,
            role=role,
            quote=spans[0].quote,
            doc_block_ids=list(
                dict.fromkeys(block_id for span in spans for block_id in span.block_ids)
            ),
            semantic_profile=semantic_profile,
            comparison_contract=comparison_contract,
            semantic_provenance=semantic_provenance,
            provenance_spans=spans,
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
            field_links=list({
                (link.attribute_ref, link.relation): link
                for link in [*existing.field_links, *target.field_links]
            }.values()),
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
    for batch in _source_passage_batches(passages):
        result = _map_source_passage_batch(
            (attribute,),
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
    linked_attributes: tuple[Attribute, ...],
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
        linked_attributes,
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
    raw_by_source: dict[str, dict[str, object]] = {}
    duplicate_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", "")).strip()
        if source_id not in passages:
            continue
        if source_id in raw_by_source:
            duplicate_ids.add(source_id)
            continue
        raw_by_source[source_id] = item

    output: list[Measurement] = []
    dispositions: list[SourcePassageDisposition] = []
    issues: dict[str, str] = {}
    pending: list[_ValidatedSourceDecision] = []
    for source_id, passage in passages.items():
        if source_id in duplicate_ids:
            issues[source_id] = "duplicate_source_decision"
            continue
        item = raw_by_source.get(source_id)
        if item is None:
            issues[source_id] = "missing_source_decision"
            continue
        status = str(item.get("status", "")).strip().lower()
        reason = " ".join(str(item.get("reason", "")).split())
        partition = _validated_evidence_unit_partition(
            item.get("evidence_unit_partition")
        )
        if status not in {
            "measurements_found",
            "no_relevant_measurement",
            "uncertain",
        } or not reason or partition is None:
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
                unit_partition=partition,
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
        pending.append(
            _ValidatedSourceDecision(
                source_id=source_id,
                passage=passage,
                status=status,
                reason=reason,
                partition=partition,
                measurements=tuple(validated),
            )
        )

    by_record: dict[str, list[_ValidatedSourceDecision]] = {}
    for decision in pending:
        source_record_id, _identity_status = _source_record_identity(
            decision.passage.finding
        )
        by_record.setdefault(source_record_id, []).append(decision)

    record_source_ids: dict[str, list[str]] = {}
    for source_id, passage in passages.items():
        source_record_id, _identity_status = _source_record_identity(passage.finding)
        record_source_ids.setdefault(source_record_id, []).append(source_id)

    for source_record_id, decisions in by_record.items():
        source_ids = [decision.source_id for decision in decisions]
        full_source_ids = record_source_ids[source_record_id]
        if any(source_id in issues for source_id in full_source_ids):
            for source_id in source_ids:
                issues.setdefault(source_id, "source_record_decision_incomplete")
            continue
        partition_statuses = {
            decision.partition.status for decision in decisions
        }
        if len(partition_statuses) != 1:
            for source_id in source_ids:
                issues[source_id] = "inconsistent_source_record_partition"
            continue
        partition_status = next(iter(partition_statuses))
        record_measurements = [
            measurement
            for decision in decisions
            for measurement in decision.measurements
        ]
        if partition_status == "disjoint_units" and (
            len(record_measurements) < 2
            or any(
                measurement.evidence_unit.status != "resolved"
                for measurement in record_measurements
            )
            or len({
                measurement.evidence_unit_id for measurement in record_measurements
            }) < 2
        ):
            for source_id in source_ids:
                issues[source_id] = "invalid_disjoint_evidence_unit_partition"
            continue
        for decision in decisions:
            output.extend(decision.measurements)
            dispositions.append(
                SourcePassageDisposition(
                    source_id=decision.source_id,
                    status=decision.status,
                    reason=decision.reason[:500],
                    url=decision.passage.finding.url,
                    insight_id=decision.passage.insight.id,
                )
            )
    return output, dispositions, issues


def _validated_passage_measurement(
    raw: object,
    *,
    passage: _SourcePassage,
    target: QuantitativeTarget,
    unit_partition: EvidenceUnitPartitionWire,
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
    if unit_partition.status != "disjoint_units":
        evidence_unit = EvidenceUnitIdentity(
            status=(
                "record_level"
                if unit_partition.status == "single_unit"
                else "uncertain"
            ),
            reason=unit_partition.reason,
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


def _validated_evidence_unit_partition(
    raw: object,
) -> EvidenceUnitPartitionWire | None:
    try:
        return EvidenceUnitPartitionWire.model_validate(raw)
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
    return {
        field_name
        for field_name, rule in target.comparison_contract.items()
        if rule.mode != "unconstrained"
    }


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
        for field_name, rule in target.comparison_contract.items()
        if rule.mode == "unknown"
    ]
    if ambiguous_target_axes:
        return (
            "unknown",
            "The direct-comparator scope is ambiguous for: "
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


def _comparison_contract_json(
    contract: dict[str, ComparisonRule],
) -> str:
    return json.dumps(
        {
            name: {
                "mode": rule.mode,
                "scope": rule.scope,
                "reason": rule.reason,
            }
            for name, rule in contract.items()
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _validated_document_field_links(
    raw: object,
    attributes_by_name: dict[str, Attribute],
) -> list[QuantitativeFieldLink] | None:
    """Keep only projections backed by resolved canonical document fields.

    Field links are views of an independently cited target. An invalid optional
    context projection must not erase that target, while at least one resolved
    defining or constraining projection is required for downstream use.
    """
    if not isinstance(raw, list):
        return None
    links: list[QuantitativeFieldLink] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            link = QuantitativeFieldLink(**item)
        except (TypeError, ValueError):
            continue
        attribute = attributes_by_name.get(link.attribute_ref)
        if (
            attribute is None
            or not attribute.target_resolved
            or not attribute.document_target
        ):
            continue
        links.append(link)
    links = list({
        (link.attribute_ref, link.relation): link
        for link in links
    }.values())
    if not any(link.relation in {"defines", "constrains"} for link in links):
        return None
    return links


_TARGET_MAPPING_ISSUE_LABELS = {
    "invalid_target_expression": "invalid normalized numeric expression",
    "target_expression_must_be_bound": "document target is not a directional or exact bound",
    "invalid_target_role": "invalid target role",
    "invalid_target_semantic_profile": "incomplete semantic profile",
    "invalid_target_comparison_contract": "incomplete direct-comparator policy",
    "invalid_field_links": "no resolved defining or constraining field link",
    "invalid_target_quote": "target excerpt is not an exact short source excerpt",
    "invalid_semantic_provenance": "semantic dimensions are not tied to canonical source context",
    "invalid_target_provenance": "target excerpt is not tied to its source block",
    "missing_target_mapping": "missing atomic target mapping",
}


def _target_mapping_issue_text(issues: list[str]) -> str:
    """Render stable contract diagnostics for one precise model retry and audit."""
    return ", ".join(
        dict.fromkeys(_TARGET_MAPPING_ISSUE_LABELS.get(issue, issue) for issue in issues)
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


def _validated_comparison_contract(
    raw: object,
) -> dict[str, ComparisonRule] | None:
    """Validate only the typed comparison policy; prose meaning remains model-owned."""
    if not isinstance(raw, dict) or set(raw) != set(QUANTITATIVE_SEMANTIC_FIELDS):
        return None
    try:
        contract = {
            field_name: ComparisonRule(**raw[field_name])
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
            if isinstance(raw.get(field_name), dict)
        }
    except (TypeError, ValueError):
        return None
    if (
        len(contract) != len(QUANTITATIVE_SEMANTIC_FIELDS)
        or contract["measure"].mode != "exact"
    ):
        return None
    return contract


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
    linked_attributes: tuple[Attribute, ...],
    *,
    target: QuantitativeTarget,
    indication: str,
    intervention_class: str,
) -> str:
    required_fields = sorted(_required_comparison_axes(target))
    linked_field_context = "\n".join(
        f"- {attribute.name}: {attribute.description}"
        for attribute in linked_attributes
    )
    return (
        "ROLE\n"
        "You extract complete numeric measurements from bounded, source-owned passages "
        "against one atomic semantic target. You interpret prose; you do not decide admission "
        "or calculate statistics.\n\n"
        "AUTHORITATIVE TARGET CONTEXT\n"
        f"- Product class: {intervention_class}\n"
        f"- Indication: {indication}\n"
        f"- Document target ID: {target.id}\n"
        f"- Target unit: {target.unit}\n"
        f"- Target role: {target.role}\n"
        f"- Target semantic profile: {_semantic_profile_json(target.semantic_profile)}\n"
        f"- Direct-comparator contract: {_comparison_contract_json(target.comparison_contract)}\n"
        "- Linked product fields are retrieval views, not claim owners:\n"
        f"{linked_field_context}\n"
        "The numeric threshold is intentionally withheld. Whether a source value passes it "
        "must never affect relevance or comparability.\n\n"
        "SOURCE DECISION\n"
        "Return exactly one decision for every immutable source ID: measurements_found, "
        "no_relevant_measurement, or uncertain. Extract only complete statements measuring "
        "the target or a meaningfully related quantity; do not enumerate every number. Each "
        "measurement needs the shortest self-contained exact quote preserving the number, "
        "measured property or outcome, and material qualifiers. If no such exact span exists, "
        "return uncertain rather than a measurement. Never import missing meaning from a title, "
        "an Insight, background knowledge, or another source.\n\n"
        "EVIDENCE-UNIT PARTITION\n"
        "Classify all measurements from the same supplied source_record together, including "
        "measurements appearing in different source passages. Return the same partition status "
        "for every source decision sharing that source_record. Use single_unit "
        "when they describe one record-level population or are alternative/repeated estimates "
        "from the same people. Use disjoint_units only when the passage explicitly establishes "
        "mutually exclusive, non-overlapping arms or cohorts. A parent population and any of its "
        "subgroups overlap and are never disjoint. Use overlapping_or_uncertain when independence "
        "cannot be proved from the passage. For disjoint_units, give every measurement a resolved "
        "evidence_unit identifying its arm/cohort. Otherwise use record_level or uncertain and do "
        "not assert group/cohort labels. Group/cohort identity describes who contributed the "
        "observation—not endpoint, timepoint, statistic, or analysis method. Do not invent labels.\n\n"
        "NUMERIC NORMALIZATION\n"
        "expression is your semantic normalization of the exact quote. Convert written quantities "
        "and directional prose without changing magnitude. Use the target unit only for the same "
        "unit meaning; otherwise retain a concise source unit. Kinds are point_estimate, range, "
        "bound, confidence_interval, count, rate, other, or unknown. Point estimates/counts/rates "
        "use value; ranges/confidence intervals use lower and upper; bounds use value and comparator. "
        "Never split a range or confidence interval. A dose, exposure condition, storage temperature, "
        "visit time, follow-up duration, or sample size alone is not an outcome measurement. For "
        "example, 'stored for 6 weeks at 60 C' is not thermostability evidence unless the same quote "
        "states the retained stability, potency, or performance.\n\n"
        "SEMANTIC MAPPING\n"
        "Return one semantic_assessment per measurement. source_ownership=yes only when the claim "
        "is a result or record fact owned by this source. Use no for another study's result quoted "
        "as background, general background, an unsupported assertion, or a merely planned outcome; "
        "use unknown when ownership is unclear. A registered protocol may own an explicit design "
        "fact such as its stated regimen even without posted outcomes, but it does not own a planned "
        "outcome result. "
        f"Return exactly these target-constrained dimensions: {json.dumps(required_fields)}. "
        "Do not assess unconstrained dimensions. Each dimension contains source={state,value,other} "
        "and compatibility={state,reason}. yes means direct comparison is semantically valid; no "
        "means a material conflict; unknown means supplied context is insufficient. Clinical disease "
        "is not infection or parasitemia, and a follow-up window is not automatically a point estimate "
        "at its endpoint. Apply each dimension's comparison mode and scope exactly: exact requires "
        "the same entity-level meaning; compatible permits differences explicitly allowed by the "
        "scope; unconstrained dimensions are omitted from this task. A different product name is not "
        "a conflict when the rule is compatible and both products fall within its scope. Numeric "
        "magnitude is never a relevance criterion. Explain every no or "
        "unknown concisely; yes may have an empty reason.\n\n"
        "OUTPUT\n"
        "Use no_relevant_measurement when no complete relevant statement exists. Use uncertain when "
        "a measurement may exist but cannot be mapped faithfully. Return only the schema-bound response."
    )


def _measurement_user_message(passages: list[_SourcePassage]) -> str:
    lines = ["BOUNDED SOURCE PASSAGES"]
    for passage in passages:
        finding = passage.finding
        published = finding.published_at.isoformat() if finding.published_at else "unknown"
        source_record_id, _identity_status = _source_record_identity(finding)
        lines.append(
            f"[source:{passage.id}] "
            f"source_record={source_record_id} | "
            f"url={finding.url} | lane={finding.excerpt_source_lane or finding.source} | "
            f"published={published} | title={finding.title}"
        )
        lines.append(f"    passage: {passage.text}")
    lines.append("\nOUTPUT REQUIREMENT\nReturn one complete decision for every source passage now.")
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


def _source_passage_batches(
    passages: list[_SourcePassage],
) -> list[list[_SourcePassage]]:
    """Pack source records without splitting their passages across model calls."""
    by_record: dict[str, list[_SourcePassage]] = {}
    for passage in passages:
        source_record_id, _identity_status = _source_record_identity(passage.finding)
        by_record.setdefault(source_record_id, []).append(passage)

    batches: list[list[_SourcePassage]] = []
    current: list[_SourcePassage] = []
    current_record_count = 0
    for record_passages in by_record.values():
        if current and current_record_count >= SOURCE_BATCH_SIZE:
            batches.append(current)
            current = []
            current_record_count = 0
        current.extend(record_passages)
        current_record_count += 1
    if current:
        batches.append(current)
    return batches


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
