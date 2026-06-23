"""Stage: assess weight of evidence for one TPP attribute variable."""

from __future__ import annotations

import json
import logging
import re

from services.searcher import Finding

from ..models import (
    Attribute,
    EvidenceAssessment,
    Insight,
    LLMClientProtocol,
    VALID_EVIDENCE_BASIS,
    VALID_EVIDENCE_STRENGTHS,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
MAX_DOC_CONTEXT_CHARS = 60000


def assess_evidence(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> EvidenceAssessment:
    """Assess whether web evidence grounds the document target for one variable."""
    supporting_findings = _dedupe_findings(
        finding for insight in insights for finding in insight.supporting_findings
    )
    if not insights:
        return EvidenceAssessment(
            attribute_ref=attribute.name,
            strength="unknown",
            basis=[],
            reason="no web evidence found",
            supporting_findings=[],
        )

    system_prompt = _system_prompt(
        attribute=attribute,
        indication=indication,
        intervention_class=intervention_class,
    )
    user_message = _user_message(attribute, doc_text, insights)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    parsed = _parse(raw)
    if not parsed:
        logger.warning("evidence_assessor produced no parsable JSON for %s; retrying once", attribute.name)
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        parsed = _parse(raw)

    if not parsed:
        return _failed_assessment(attribute.name, supporting_findings)

    strength = str(parsed.get("strength", "")).strip().lower()
    if strength not in VALID_EVIDENCE_STRENGTHS:
        strength = "unknown"
    raw_basis = parsed.get("basis", []) or []
    basis = [
        str(item).strip().lower()
        for item in raw_basis
        if str(item).strip().lower() in VALID_EVIDENCE_BASIS
    ]
    reason = str(parsed.get("reason", "")).strip() or "assessment failed"
    return EvidenceAssessment(
        attribute_ref=attribute.name,
        strength=strength,
        basis=list(dict.fromkeys(basis)),
        reason=reason,
        supporting_findings=supporting_findings,
    )


def _system_prompt(
    *,
    attribute: Attribute,
    indication: str,
    intervention_class: str,
) -> str:
    return (
        "You assess weight of evidence for ONE TPP variable.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        "Task:\n"
        "1. Locate this variable's target value in the document text. If no target is stated, handle that gracefully and note it in the reason.\n"
        "2. First decide which KIND of target this is:\n"
        "   - COMPETITIVE (higher is better, meant to beat the field - e.g. efficacy, duration): judge whether the target is a JUSTIFIED IMPROVEMENT over the current standard of care, supported by modeling/clinical evidence.\n"
        "   - THRESHOLD (a bar to meet, often a ceiling - e.g. dose volume, cost, cold-chain/stability, presentation): judge whether the target is ACHIEVABLE and SUPPORTED by what current products/evidence show. Do NOT require it to beat the standard of care; if products already meet it, that is strong support, not weak.\n"
        "3. Weigh evidence by type: a standard-of-care anchor (what current products achieve), modeling tying the target to an outcome, study strength (clinical-trial data weighs more than preclinical/animal-model data), and regulatory precedent including national regulators.\n\n"
        "Strength enum (interpret per the target KIND above):\n"
        "- well_grounded: strong evidence supports the target - a clear, evidenced improvement (competitive) OR current products/evidence clearly meet the bar (threshold).\n"
        "- partial: the target is plausibly supported, but the evidence has gaps.\n"
        "- thin: evidence is sparse, indirect, or preclinical-only.\n"
        "- unsupported: no evidence supports the target being achievable or justified. Do NOT use this merely because a threshold target is unambitious or already met - that is well_grounded.\n"
        "- unknown: the evidence cannot be assessed.\n\n"
        "Basis enum values: standard_of_care, modeling, study_strength, regulatory_precedent.\n"
        "Use only basis values actually supported by the web evidence; basis may be empty.\n"
        "Reason is one sentence, 25 words or fewer.\n\n"
        "Return ONLY JSON. No markdown, no commentary. Format:\n"
        '{"strength": "partial", "basis": ["standard_of_care"], "reason": "..."}'
    )


def _user_message(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
) -> str:
    if len(doc_text) > MAX_DOC_CONTEXT_CHARS:
        doc_text = doc_text[:MAX_DOC_CONTEXT_CHARS] + "\n...[truncated]"
    lines = [
        "Document text:",
        doc_text,
        "",
        f"Variable: {attribute.name}",
        f"Definition: {attribute.description}",
        "",
        "Web insights for this variable:",
    ]
    for i, insight in enumerate(insights):
        urls = ", ".join(f.url for f in insight.supporting_findings)
        lines.append(f"[{i}] {insight.statement}")
        if urls:
            lines.append(f"    sources: {urls}")
    lines.append("\nAssess the evidence now.")
    return "\n".join(lines)


def _failed_assessment(
    attribute_ref: str,
    supporting_findings: list[Finding],
) -> EvidenceAssessment:
    return EvidenceAssessment(
        attribute_ref=attribute_ref,
        strength="unknown",
        basis=[],
        reason="assessment failed",
        supporting_findings=supporting_findings,
    )


def _dedupe_findings(findings) -> list[Finding]:
    seen: set[str] = set()
    out: list[Finding] = []
    for finding in findings:
        if finding.url in seen:
            continue
        seen.add(finding.url)
        out.append(finding)
    return out


def _parse(raw: str) -> dict:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_object(text))
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
