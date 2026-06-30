"""Stage: combined weight-of-evidence conformity score for ONE quantitative variable.

A transparent, reproducible complement to the qualitative `evidence_assessor`.
Where sources report comparable numbers against a doc-stated target (e.g.
efficacy >= 80%), this:

  1. (LLM) extracts the doc target + comparator and each source's reported value
     and source type.
  2. (math) weights each source by reliability (source type) x recency (publish
     date), converts each reported value into a probability the true value meets
     the target (normal model around the threshold), and combines them into one
     conformity probability with an uncertainty band and a verdict.

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
from statistics import NormalDist

from services.searcher import Finding

from ..models import Attribute, ConformityScore, Insight, LLMClientProtocol, Measurement

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
MAX_MEASUREMENTS = 40
# Keep in lockstep with drift_classifier / evidence_assessor so all three
# doc-reading stages see the SAME baseline and a target near the end of a long
# doc is never cut off in one stage but not another.
MAX_DOC_CONTEXT_CHARS = 120000

# Reliability weight per source type (evidence hierarchy). Human-owned domain
# numbers: strongest direct evidence ~1.0, weakest/indirect ~0.4. The LLM
# classifies each source into one of these types; unknown -> "other".
SOURCE_WEIGHTS: dict[str, float] = {
    "systematic_review_meta_analysis": 0.95,
    "rct_phase3": 0.95,
    "regulatory_assessment": 0.90,
    "rct_phase2": 0.80,
    "clinical_trial_registry": 0.70,
    "observational_study": 0.65,
    "program_effectiveness": 0.60,
    "preprint": 0.55,
    "other": 0.50,
    "press_release": 0.40,
}
VALID_SOURCE_TYPES = set(SOURCE_WEIGHTS)

RECENCY_HALFLIFE_MONTHS = 36.0       # recency weight halves ~every 3 years
NEUTRAL_RECENCY = 0.5               # recency weight when a source has no date (don't fake an age)
RELATIVE_MEASUREMENT_SD = 0.10      # per-source noise ~10% of target, scaled by reliability
EVIDENCE_SATURATION = 2.0            # total weight at which evidence is "enough"


def score_conformity(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
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
        max_tokens=max_tokens,
    )
    if extracted is None:
        return None

    target_value, comparator, unit, target_label, measurements = extracted
    measurements = _dedupe_measurements(measurements)
    if not measurements:
        return None

    _attach_weights(measurements, insights)
    return _combine(
        attribute.name, target_value, comparator, unit, target_label, measurements
    )


def _dedupe_measurements(measurements: list[Measurement]) -> list[Measurement]:
    """Collapse duplicate sources so one source can't be counted multiple times
    (which would inflate confidence). Dedup by URL when present, else by
    (value, source_type)."""
    seen: set = set()
    out: list[Measurement] = []
    for m in measurements:
        key = m.url or (m.value, m.source_type)
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
    measurements: list[Measurement],
) -> ConformityScore:
    sd = max(abs(target_value) * RELATIVE_MEASUREMENT_SD, 1e-6)

    weights: list[float] = []
    probs: list[float] = []
    for m in measurements:
        # Per-source noise: stronger sources are tighter around their value.
        quality = SOURCE_WEIGHTS.get(m.source_type, SOURCE_WEIGHTS["other"])
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
        return "Strong evidence the target is met"
    if conformity >= 0.55:
        return "Moderate evidence the target is met"
    if conformity <= 0.25:
        return "Strong evidence the target is NOT met"
    if conformity <= 0.45:
        return "Moderate evidence the target is NOT met"
    return "Mixed / indeterminate evidence"


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
        reliability = SOURCE_WEIGHTS.get(m.source_type, SOURCE_WEIGHTS["other"])
        m.weight = round(reliability * recency, 4)


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
    max_tokens: int,
) -> tuple[float, str, str, str, list[Measurement]] | None:
    system_prompt = _system_prompt(attribute, indication, intervention_class)
    user_message = _user_message(attribute, doc_text, insights)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
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
    target_label = str(parsed.get("target_label", "")).strip()

    measurements: list[Measurement] = []
    for item in parsed.get("measurements", []) or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)):
            continue
        source_type = str(item.get("source_type", "other")).strip().lower()
        if source_type not in VALID_SOURCE_TYPES:
            source_type = "other"
        measurements.append(
            Measurement(
                value=float(value),
                source_type=source_type,
                url=str(item.get("url", "")).strip(),
            )
        )
        if len(measurements) >= MAX_MEASUREMENTS:
            break

    return float(target), comparator, unit, target_label, measurements


def _system_prompt(attribute: Attribute, indication: str, intervention_class: str) -> str:
    return (
        "You extract structured numeric evidence for ONE variable so a "
        "downstream calculator can combine it.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        "Task:\n"
        "1. Decide if this variable is QUANTITATIVE - i.e. the document states a "
        "numeric target with a clear direction (e.g. efficacy >= 80%, cost <= $1.50, "
        "duration >= 12 months). If it is not numeric, set is_quantitative=false.\n"
        "2. If quantitative, pick the SINGLE most binding target to score against. "
        "Documents often state several (e.g. pediatric vs adult, optimal vs threshold). "
        "Choose the broadest/threshold (go/no-go) value, give its value, its comparator "
        "(\">=\" when higher is better, \"<=\" when lower is better), the unit, and a short "
        "target_label naming exactly which target you chose (e.g. \"adult threshold <=1.0 mL\").\n"
        "3. From the web insights, extract each source's reported numeric value for "
        "THIS variable (same unit as the target). Count ONLY values that measure THIS "
        "product/indication's target. Do NOT include a value from a DIFFERENT indication, "
        "disease, or product class even when the unit matches (e.g. the same platform's "
        "result in another disease) - that is analogous precedent, not a measurement of "
        "this target, and must be excluded. Use ONE value per DISTINCT source. "
        "Treat the same underlying content as a single source: collapse the same "
        "announcement across languages, mirror/republished pages, and a PubMed record "
        "and its PMC full-text into ONE measurement (do not count it multiple times). "
        "Emit separate measurements ONLY for genuinely independent sources. Skip "
        "insights with no comparable number. Classify each source into one source_type "
        "from this list:\n"
        "   systematic_review_meta_analysis, rct_phase3, rct_phase2, "
        "regulatory_assessment, clinical_trial_registry, observational_study, "
        "program_effectiveness, preprint, press_release, other.\n"
        "   Include the source URL for each measurement.\n\n"
        "Return ONLY JSON. No markdown, no commentary. Format:\n"
        '{"is_quantitative": true, "target_value": 80, "comparator": ">=", '
        '"unit": "%", "target_label": "threshold >=80%", '
        '"measurements": [{"value": 75, "source_type": "rct_phase3", '
        '"url": "https://..."}]}\n'
        "If not quantitative: {\"is_quantitative\": false}"
    )


def _user_message(attribute: Attribute, doc_text: str, insights: list[Insight]) -> str:
    if len(doc_text) > MAX_DOC_CONTEXT_CHARS:
        doc_text = doc_text[:MAX_DOC_CONTEXT_CHARS] + "\n...[truncated]"
    lines = [
        "Document text:",
        doc_text,
        "",
        f"Variable: {attribute.name}",
        "",
        "Web insights for this variable:",
    ]
    for i, insight in enumerate(insights):
        urls = ", ".join(f.url for f in insight.supporting_findings)
        lines.append(f"[{i}] {insight.statement}")
        if urls:
            lines.append(f"    sources: {urls}")
    lines.append("\nExtract the structured numeric evidence now.")
    return "\n".join(lines)


def _parse(raw: str) -> dict | None:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_object(text))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


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
