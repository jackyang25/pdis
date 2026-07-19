"""Stage: combined weight-of-evidence conformity score for ONE quantitative variable.

A transparent, reproducible complement to the qualitative `evidence_assessor`.
Where sources report comparable numbers against a doc-stated target (e.g.
efficacy >= 80%), this:

  1. (LLM) extracts the doc target + comparator, each source's reported value,
     evidence form, development phase, and source-record type.
  2. (math) weights each source from those orthogonal axes x recency (publish
     date), converts each reported value into directional alignment with the
     target (normal model around the threshold), and combines them into one
     non-calibrated alignment score with an uncertainty band and verdict.

Self-gating: returns None for non-quantitative variables or when no comparable
measurements are found. Pure stdlib (statistics.NormalDist) - no R, no numpy.

Inspired by credal/Bayesian evidence-combining (Arnborg 2006; Karlsson 2011),
implemented as a reliability-weighted combination to stay simple and dependency
free while preserving the key properties: source weighting, recency decay, and
shrinkage toward "uncertain" when evidence is thin.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from statistics import NormalDist

import yaml

from services.searcher import Finding

from ..context import document_block_ids, limit_document_context, validated_block_ids
from ..models import Attribute, ConformityScore, Insight, LLMClientProtocol, Measurement

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
MAX_MEASUREMENTS = 40
# Keep in lockstep with drift_classifier / evidence_assessor so all three
# doc-reading stages see the SAME baseline and a target near the end of a long
# doc is never cut off in one stage but not another.

_METHODOLOGY_PATH = Path(__file__).resolve().parents[1] / "configs" / "evidence_methodology.yaml"
with _METHODOLOGY_PATH.open("r", encoding="utf-8") as _methodology_file:
    _METHODOLOGY = yaml.safe_load(_methodology_file) or {}

EVIDENCE_FORM_WEIGHTS: dict[str, float] = _METHODOLOGY["evidence_form_weights"]
PHASE_MULTIPLIERS: dict[str, float] = _METHODOLOGY["development_phase_multipliers"]
SOURCE_RECORD_MULTIPLIERS: dict[str, float] = _METHODOLOGY[
    "source_record_multipliers"
]
VALID_EVIDENCE_FORMS = set(EVIDENCE_FORM_WEIGHTS)
VALID_PHASES = set(PHASE_MULTIPLIERS)
VALID_SOURCE_RECORD_TYPES = set(SOURCE_RECORD_MULTIPLIERS)

RECENCY_HALFLIFE_MONTHS = float(_METHODOLOGY["recency_halflife_months"])
NEUTRAL_RECENCY = float(_METHODOLOGY["neutral_recency"])
RELATIVE_MEASUREMENT_SD = float(_METHODOLOGY["relative_measurement_sd"])
EVIDENCE_SATURATION = float(_METHODOLOGY["evidence_saturation"])


def score_conformity(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ConformityScore | None:
    """Return a combined conformity score, or None if the variable is not
    quantitative / has no comparable numeric evidence."""
    if not insights:
        return None

    extracted = _extract_measurements(
        attribute,
        doc_text,
        insights,
        llm_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
        images=images,
        max_tokens=max_tokens,
    )
    if extracted is None:
        return None

    target_value, comparator, unit, target_label, doc_block_ids, measurements = extracted
    measurements = _dedupe_measurements(measurements)
    if not measurements:
        return None

    _attach_weights(measurements, insights)
    return _combine(
        attribute.name,
        target_value,
        comparator,
        unit,
        target_label,
        doc_block_ids,
        measurements,
    )


def _dedupe_measurements(measurements: list[Measurement]) -> list[Measurement]:
    """Collapse duplicate sources so one source can't be counted multiple times
    (which would inflate confidence). Dedup by URL when present, else by
    (value, study-design axes)."""
    seen: set = set()
    out: list[Measurement] = []
    for m in measurements:
        key = m.url or (
            m.value,
            m.unit,
            m.evidence_form,
            m.development_phase,
            m.source_record_type,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# ---------------------------------------------------------------------------
# Combination math (pure, deterministic)
# ---------------------------------------------------------------------------


def _combine(
    attribute_ref: str,
    target_value: float,
    comparator: str,
    unit: str,
    target_label: str,
    doc_block_ids: list[str],
    measurements: list[Measurement],
) -> ConformityScore:
    sd = max(abs(target_value) * RELATIVE_MEASUREMENT_SD, 1e-6)

    weights: list[float] = []
    probs: list[float] = []
    for m in measurements:
        # Per-source noise: stronger sources are tighter around their value.
        quality = _methodology_weight(m)
        source_sd = sd / math.sqrt(max(quality, 0.1))
        probs.append(_p_conform(m.value, target_value, comparator, source_sd))
        weights.append(max(m.weight, 1e-6))

    total_weight = sum(weights)
    mean = sum(w * p for w, p in zip(weights, probs)) / total_weight
    variance = sum(w * (p - mean) ** 2 for w, p in zip(weights, probs)) / total_weight
    spread = math.sqrt(variance)

    # Shrink toward 0.5 ("uncertain") when total weighted evidence is thin.
    saturation = min(1.0, total_weight / EVIDENCE_SATURATION)
    conformity = saturation * mean + (1 - saturation) * 0.5

    # Band widens with source disagreement and with thin evidence.
    margin = spread + (1 - saturation) * 0.25
    lower = _clamp(conformity - margin)
    upper = _clamp(conformity + margin)

    return ConformityScore(
        attribute_ref=attribute_ref,
        target_value=target_value,
        comparator=comparator,
        unit=unit,
        target_label=target_label,
        conformity=round(conformity, 3),
        lower=round(lower, 3),
        upper=round(upper, 3),
        verdict=_verdict(conformity),
        doc_block_ids=doc_block_ids,
        measurements=measurements,
    )


def _p_conform(value: float, target: float, comparator: str, sd: float) -> float:
    """Probability the true value meets the target, given a noisy observation."""
    dist = NormalDist(mu=value, sigma=sd)
    if comparator == "<=":
        return dist.cdf(target)            # conform if true value <= target
    return 1.0 - dist.cdf(target)          # ">=": conform if true value >= target


def _verdict(conformity: float) -> str:
    if conformity >= 0.75:
        return "Strong alignment with the target"
    if conformity >= 0.55:
        return "Moderate alignment with the target"
    if conformity <= 0.25:
        return "Strong misalignment with the target"
    if conformity <= 0.45:
        return "Moderate misalignment with the target"
    return "Mixed / indeterminate alignment"


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _attach_weights(measurements: list[Measurement], insights: list[Insight]) -> None:
    """Fill each measurement's recency (from the matching finding's publish date)
    and final reliability x recency weight."""
    published_by_url = {
        f.url: f.published_at
        for insight in insights
        for f in insight.supporting_findings
    }
    for m in measurements:
        published = published_by_url.get(m.url)
        m.age_months = _age_months(published)
        # Date honesty: when the source has no real date, use a neutral recency
        # weight rather than inventing an age. age_months stays None so the UI
        # can show "date unknown" instead of a fake number.
        recency = (
            NEUTRAL_RECENCY
            if m.age_months is None
            else math.exp(-m.age_months / RECENCY_HALFLIFE_MONTHS)
        )
        reliability = _methodology_weight(m)
        m.weight = round(reliability * recency, 4)


def _methodology_weight(measurement: Measurement) -> float:
    evidence_form = EVIDENCE_FORM_WEIGHTS.get(
        measurement.evidence_form, EVIDENCE_FORM_WEIGHTS["other"]
    )
    phase = PHASE_MULTIPLIERS.get(
        measurement.development_phase, PHASE_MULTIPLIERS["unknown"]
    )
    source_record = SOURCE_RECORD_MULTIPLIERS.get(
        measurement.source_record_type, SOURCE_RECORD_MULTIPLIERS["unknown"]
    )
    return min(1.0, evidence_form * phase * source_record)


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


def _extract_measurements(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str,
    images: list[dict[str, str]] | None,
    max_tokens: int,
) -> tuple[float, str, str, str, list[str], list[Measurement]] | None:
    system_prompt = _system_prompt(
        attribute, indication, intervention_class, framing=framing
    )
    user_message = _user_message(attribute, doc_text, insights)

    raw = llm_client.call(
        system_prompt, user_message, max_tokens=max_tokens, images=images
    )
    parsed = _parse(raw)
    if parsed is None:
        return None

    if not parsed.get("is_quantitative"):
        return None
    target = parsed.get("target_value")
    comparator = str(parsed.get("comparator", "")).strip()
    if not isinstance(target, (int, float)) or comparator not in {">=", "<="}:
        return None
    unit = str(parsed.get("unit", "")).strip()
    if not unit:
        return None
    target_label = str(parsed.get("target_label", "")).strip()
    target_block_ids = validated_block_ids(
        parsed.get("doc_block_ids"), document_block_ids(doc_text)
    )

    measurements: list[Measurement] = []
    for item in parsed.get("measurements", []) or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)):
            continue
        measurement_unit = str(item.get("unit", "")).strip()
        # Never silently convert dimensional values. Incompatible units remain
        # visible in the source insight but cannot enter the numeric combiner.
        if (
            not measurement_unit
            or _canonical_unit(measurement_unit) != _canonical_unit(unit)
        ):
            continue
        insight_index = item.get("insight_index")
        if (
            not isinstance(insight_index, int)
            or isinstance(insight_index, bool)
            or not 0 <= insight_index < len(insights)
        ):
            continue
        insight = insights[insight_index]
        url = str(item.get("url", "")).strip()
        allowed_urls = {finding.url for finding in insight.supporting_findings}
        if not url or url not in allowed_urls:
            continue
        evidence_form = str(item.get("evidence_form", "other")).strip().lower()
        if evidence_form not in VALID_EVIDENCE_FORMS:
            evidence_form = "other"
        development_phase = str(
            item.get("development_phase", "unknown")
        ).strip().lower()
        if development_phase not in VALID_PHASES:
            development_phase = "unknown"
        source_record_type = str(
            item.get("source_record_type", "unknown")
        ).strip().lower()
        if source_record_type not in VALID_SOURCE_RECORD_TYPES:
            source_record_type = "unknown"
        measurements.append(
            Measurement(
                value=float(value),
                unit=measurement_unit,
                evidence_form=evidence_form,
                development_phase=development_phase,
                source_record_type=source_record_type,
                url=url,
                insight_id=insight.id,
            )
        )
        if len(measurements) >= MAX_MEASUREMENTS:
            break

    return float(target), comparator, unit, target_label, target_block_ids, measurements


def _system_prompt(
    attribute: Attribute,
    indication: str,
    intervention_class: str,
    *,
    framing: str = "",
) -> str:
    framing = (
        framing.strip()
        or "Interpret the numeric statement according to the uploaded document's own role; "
        "do not assume it is either an aspirational target or a plan commitment."
    ).replace("{intervention_class}", intervention_class).replace(
        "{indication}", indication
    )
    return (
        "You extract structured numeric evidence for ONE variable so a "
        "downstream calculator can combine it.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        f"Document-specific interpretation:\n{framing}\n\n"
        "Task:\n"
        "1. Decide if this variable is QUANTITATIVE - i.e. the document states a "
        "numeric target with a clear direction (e.g. efficacy >= 80%, cost <= $1.50, "
        "duration >= 12 months). If it is not numeric, set is_quantitative=false.\n"
        "2. If quantitative, pick the SINGLE most decision-relevant binding value for this "
        "unit. Documents may state several population-specific, optimal/threshold, timeline, "
        "cost, or capacity values. Follow the document-specific interpretation above and "
        "choose the go/no-go constraint; give its value, its comparator "
        "(\">=\" when higher is better, \"<=\" when lower is better), the unit, and a short "
        "target_label naming exactly which target you chose (e.g. \"adult threshold <=1.0 mL\").\n"
        "Return doc_block_ids containing the exact [block:<id>] markers for that target.\n"
        "3. From the external-evidence insights, extract each source's reported numeric value for "
        "THIS variable. Count ONLY values already expressed in the SAME unit as the target; "
        "do not convert units or percentages, and include that unit on every measurement. "
        "The deterministic parser rejects a measurement whose unit differs. Count ONLY values that measure THIS "
        "product/indication's target. Do NOT include a value from a DIFFERENT indication, "
        "disease, or product class even when the unit matches (e.g. the same platform's "
        "result in another disease) - that is analogous precedent, not a measurement of "
        "this target, and must be excluded. Use ONE value per DISTINCT source. "
        "Treat the same underlying content as a single source: collapse the same "
        "announcement across languages, mirror/republished pages, and a PubMed record "
        "and its PMC full-text into ONE measurement (do not count it multiple times). "
        "Emit separate measurements ONLY for genuinely independent sources. Skip "
        "insights with no comparable number. Label each source on THREE separately defined axes:\n"
        "   evidence_form: evidence_synthesis, randomized_trial, nonrandomized_trial, "
        "observational_study, implementation_evidence, regulatory_review, registry_record, other.\n"
        "   development_phase: phase_1, phase_2, phase_3, phase_4, not_applicable, unknown.\n"
        "   source_record_type: peer_reviewed, preprint, regulatory, registry, "
        "company_report, unknown.\n"
        "Do not collapse these axes: a Phase 3 randomized trial can be a preprint, and a "
        "registry record may describe any phase.\n"
        "   Include the source URL and insight_index for each measurement. The URL MUST "
        "appear under that numbered insight; never invent or rewrite a URL.\n\n"
        "Discovery-track labels are retrieval provenance only and must not affect extraction.\n\n"
        "Return ONLY JSON. No markdown, no commentary. Format:\n"
        '{"is_quantitative": true, "target_value": 80, "comparator": ">=", '
        '"unit": "%", "target_label": "threshold >=80%", "doc_block_ids": ["b-0001"], '
        '"measurements": [{"value": 75, "unit": "%", "evidence_form": "randomized_trial", '
        '"development_phase": "phase_3", "source_record_type": "peer_reviewed", '
        '"insight_index": 0, "url": "https://..."}]}\n'
        "If not quantitative: {\"is_quantitative\": false}"
    )


def _user_message(attribute: Attribute, doc_text: str, insights: list[Insight]) -> str:
    doc_text = limit_document_context(doc_text)
    lines = [
        "Document text:",
        doc_text,
        "",
        f"Variable: {attribute.name}",
        "",
        "External-evidence insights for this variable:",
    ]
    for i, insight in enumerate(insights):
        lines.append(f"[{i}] ({insight.id}) {insight.statement}")
        if insight.query_tracks:
            lines.append(f"    discovery tracks: {', '.join(insight.query_tracks)}")
        for finding in insight.supporting_findings:
            published = finding.published_at.isoformat() if finding.published_at else "unknown"
            lines.append(
                f"    source: {finding.url} | lane={finding.source} | published={published} "
                f"| title={finding.title}"
            )
    lines.append("\nExtract the structured numeric evidence now.")
    return "\n".join(lines)


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
