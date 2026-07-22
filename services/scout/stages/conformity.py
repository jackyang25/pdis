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

Self-gating: returns None for non-quantitative variables or when no comparable
measurements are found. Pure stdlib; no R or numpy.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import re
from pathlib import Path
from statistics import fmean, stdev
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from services.searcher import Finding

from ..context import document_block_ids, limit_document_context, validated_block_ids
from ..models import Attribute, ConformityScore, Insight, LLMClientProtocol, Measurement

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
MAX_FINDING_EXCERPT_CHARS = 6000
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

COMPARABILITY_AXES = (
    "endpoint",
    "population",
    "intervention",
    "regimen",
    "time_horizon",
    "statistic",
)
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
    """Return a calibration ledger, or None when no grounded numeric target exists."""
    if not insights or (
        attribute.target_resolved and not attribute.document_target
    ):
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

    (
        target_value,
        comparator,
        unit,
        target_label,
        target_quote,
        doc_block_ids,
        candidates,
    ) = extracted
    measurements, excluded_measurements = _partition_cohort(candidates)
    if not measurements:
        return ConformityScore(
            attribute_ref=attribute.name,
            target_value=target_value,
            comparator=comparator,
            unit=unit,
            target_label=target_label,
            target_quote=target_quote,
            target_meeting_count=0,
            target_meeting_rate=0.0,
            verdict="No validated claim-compatible comparators",
            calibration_status="insufficient",
            doc_block_ids=doc_block_ids,
            excluded_measurements=excluded_measurements,
        )

    _attach_dates(measurements, insights)
    return _combine(
        attribute.name,
        target_value,
        comparator,
        unit,
        target_label,
        target_quote,
        doc_block_ids,
        measurements,
        excluded_measurements,
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
    attribute_ref: str,
    target_value: float,
    comparator: str,
    unit: str,
    target_label: str,
    target_quote: str,
    doc_block_ids: list[str],
    measurements: list[Measurement],
    excluded_measurements: list[Measurement],
) -> ConformityScore:
    benchmark_values = sorted(measurement.value for measurement in measurements)
    benchmark_count = len(benchmark_values)
    met_target = [
        _meets_target(value, target_value, comparator)
        for value in benchmark_values
    ]
    target_meeting_count = sum(met_target)
    target_meeting_rate = target_meeting_count / benchmark_count
    target_percentile = _empirical_percentile(benchmark_values, target_value)
    ambition_percentile = (
        1.0 - target_percentile if comparator == "<=" else target_percentile
    )

    return ConformityScore(
        attribute_ref=attribute_ref,
        target_value=target_value,
        comparator=comparator,
        unit=unit,
        target_label=target_label,
        target_quote=target_quote,
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
        doc_block_ids=doc_block_ids,
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
    return value <= target if comparator == "<=" else value >= target


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
) -> tuple[float, str, str, str, str, list[str], list[Measurement]] | None:
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
    if not _is_finite_number(target) or comparator not in {">=", "<="}:
        return None
    unit = str(parsed.get("unit", "")).strip()
    if not unit:
        return None
    target_label = str(parsed.get("target_label", "")).strip()
    target_quote = str(parsed.get("target_quote", "")).strip()
    target_block_ids = (
        list(attribute.block_ids)
        if attribute.target_resolved
        else validated_block_ids(
            parsed.get("doc_block_ids"), document_block_ids(doc_text)
        )
    )
    target_source_text = _text_for_blocks(doc_text, target_block_ids)
    if (
        not target_block_ids
        or not target_quote
        or not _quote_in_text(target_quote, target_source_text)
        or not _number_supported(float(target), target_quote)
        or not _unit_supported_by_quote(unit, target_quote)
        or not _comparator_supported(comparator, target_quote)
    ):
        return None

    candidates: list[Measurement] = []
    for item in parsed.get("measurements", []) or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not _is_finite_number(value):
            continue
        measurement_unit = str(item.get("unit", "")).strip()
        if not measurement_unit:
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
        finding = next(
            (
                finding
                for finding in insight.supporting_findings
                if finding.url == url
            ),
            None,
        )
        if finding is None or not finding.excerpt:
            continue
        source_quote = str(item.get("source_quote", "")).strip()
        if (
            not source_quote
            or not _quote_in_text(source_quote, finding.excerpt)
            or not _number_supported(float(value), source_quote)
            or not _unit_supported_by_quote(measurement_unit, source_quote)
        ):
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
        comparability, comparability_reasons = _parse_comparability(
            item.get("comparability")
        )
        source_record_id, source_identity_status = _source_record_identity(finding)
        exclusion_reasons: list[str] = []
        if _canonical_unit(measurement_unit) != _canonical_unit(unit):
            exclusion_reasons.append(
                f"incompatible unit: {measurement_unit} versus target unit {unit}"
            )
        candidates.append(
            Measurement(
                value=float(value),
                unit=measurement_unit,
                evidence_form=evidence_form,
                development_phase=development_phase,
                source_record_type=source_record_type,
                url=url,
                insight_id=insight.id,
                source_quote=source_quote,
                source_record_id=source_record_id,
                source_identity_status=source_identity_status,
                comparability=comparability,
                comparability_reasons=comparability_reasons,
                exclusion_reasons=exclusion_reasons,
            )
        )
    return (
        float(target),
        comparator,
        unit,
        target_label,
        target_quote,
        target_block_ids,
        candidates,
    )


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
        f"Definition: {attribute.description}\n"
        f"Canonical document target: {attribute.document_target or '(not stated)'}\n"
        f"Canonical target blocks: {', '.join(attribute.block_ids) or '(none)'}\n\n"
        f"Document-specific interpretation:\n{framing}\n\n"
        "Task:\n"
        "1. Decide if the canonical document target is QUANTITATIVE - i.e. it states a "
        "numeric target with a clear direction (e.g. efficacy >= 80%, cost <= $1.50, "
        "duration >= 12 months). If it is not numeric, set is_quantitative=false.\n"
        "2. If quantitative, pick the SINGLE most decision-relevant binding value for this "
        "unit. Documents may state several population-specific, optimal/threshold, timeline, "
        "cost, or capacity values. Follow the document-specific interpretation above and "
        "choose the go/no-go constraint; give its value, its comparator "
        "(\">=\" when higher is better, \"<=\" when lower is better), the unit, and a short "
        "target_label naming exactly which target you chose (e.g. \"adult threshold <=1.0 mL\"). "
        "Return target_quote copied verbatim from the cited document block, including enough "
        "surrounding text to establish the value, unit, and direction. Return doc_block_ids "
        "containing the exact [block:<id>] markers for that target. The verifier rejects a "
        "quote, value, unit, comparator, or block that is not supported by that text.\n"
        "3. From the external-evidence insights, extract each source's reported numeric candidate "
        "for THIS variable. Do not convert units or percentages; preserve and return the source's "
        "own unit. Return an otherwise on-topic candidate even when one claim dimension or its "
        "unit differs, then label that difference in step 4 so the deterministic exclusion ledger "
        "can explain it. Do not return arbitrary numbers from unrelated topics. Use ONE value per "
        "DISTINCT source. "
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
        "   Include source_quote copied verbatim from that URL's supplied excerpt and containing "
        "the numeric value and unit. Include the source URL and insight_index. The URL MUST "
        "appear under that numbered insight; never invent or rewrite a URL.\n"
        "4. Compare each candidate with the exact document claim on six independent axes. "
        "For every axis return relation = same, compatible, not_applicable, different, or "
        "unknown, plus a short reason grounded only in the supplied target/source text:\n"
        "   endpoint: the same outcome or measurable construct.\n"
        "   population: the same decision-relevant population.\n"
        "   intervention: the same product/intervention or a valid comparator for this claim.\n"
        "   regimen: the same dose/schedule/implementation conditions, or irrelevant.\n"
        "   time_horizon: the same follow-up or operational time window, or irrelevant.\n"
        "   statistic: the same statistic/denominator (e.g. mean vs median, risk vs rate).\n"
        "Use unknown when the excerpts do not establish an axis. Do not infer missing details. "
        "Deterministic code—not you—will decide inclusion.\n\n"
        "Discovery-track labels are retrieval provenance only and must not affect extraction.\n\n"
        "Return ONLY JSON. No markdown, no commentary. Format:\n"
        '{"is_quantitative": true, "target_value": 80, "comparator": ">=", '
        '"unit": "%", "target_label": "threshold >=80%", '
        '"target_quote": "Minimum efficacy: at least 80%", "doc_block_ids": ["b-0001"], '
        '"measurements": [{"value": 75, "unit": "%", "evidence_form": "randomized_trial", '
        '"development_phase": "phase_3", "source_record_type": "peer_reviewed", '
        '"insight_index": 0, "url": "https://...", '
        '"source_quote": "Efficacy was 75% in the target population", '
        '"comparability": {"endpoint": {"relation": "same", "reason": "same endpoint"}, '
        '"population": {"relation": "same", "reason": "same population"}, '
        '"intervention": {"relation": "same", "reason": "same product"}, '
        '"regimen": {"relation": "not_applicable", "reason": "not part of this claim"}, '
        '"time_horizon": {"relation": "same", "reason": "same follow-up"}, '
        '"statistic": {"relation": "same", "reason": "same proportion"}}}]}\n'
        "If not quantitative: {\"is_quantitative\": false}"
    )


def _user_message(attribute: Attribute, doc_text: str, insights: list[Insight]) -> str:
    doc_text = limit_document_context(doc_text)
    lines = [
        "Document text:",
        doc_text,
        "",
        f"Variable: {attribute.name}",
        f"Definition: {attribute.description}",
        f"Canonical document target: {attribute.document_target or '(not stated)'}",
        f"Canonical target blocks: {', '.join(attribute.block_ids) or '(none)'}",
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
            if finding.excerpt:
                excerpt = finding.excerpt[:MAX_FINDING_EXCERPT_CHARS]
                if len(finding.excerpt) > MAX_FINDING_EXCERPT_CHARS:
                    excerpt += "...[source excerpt clipped]"
                lines.append(f"      excerpt: {excerpt}")
    lines.append("\nExtract the structured numeric evidence now.")
    return "\n".join(lines)


def _parse_comparability(raw: object) -> tuple[dict[str, str], dict[str, str]]:
    payload = raw if isinstance(raw, dict) else {}
    relations: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for axis in COMPARABILITY_AXES:
        item = payload.get(axis)
        item = item if isinstance(item, dict) else {}
        relation = str(item.get("relation", "unknown")).strip().lower()
        reason = str(item.get("reason", "")).strip()
        if relation not in COMPARABILITY_RELATIONS or not reason:
            relation = "unknown"
        relations[axis] = relation
        reasons[axis] = reason
    return relations, reasons


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
    r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?"
)


def _number_supported(value: float, quote: str) -> bool:
    for token in _NUMBER_RE.findall(quote):
        try:
            parsed = float(token.replace(",", ""))
        except ValueError:
            continue
        if math.isclose(parsed, value, rel_tol=1e-9, abs_tol=1e-9):
            return True
    return False


def _unit_supported_by_quote(unit: str, quote: str) -> bool:
    canonical = _canonical_unit(unit)
    folded = html.unescape(quote).casefold()
    aliases = {
        "%": ("%", "percent", "percentage", "pct"),
        "usd": ("$", "usd", "us dollar", "u.s. dollar"),
    }
    if canonical in aliases:
        return any(alias in folded for alias in aliases[canonical])
    normalized_quote = re.sub(r"[\s._-]+", "", folded)
    return bool(canonical) and canonical in normalized_quote


def _comparator_supported(comparator: str, quote: str) -> bool:
    folded = _normalize_quote(quote)
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
