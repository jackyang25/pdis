"""Stage: assess weight of evidence for one document unit (attribute/claim)."""

from __future__ import annotations

import json
import logging
import re

from services.searcher import Finding

from ..context import document_block_ids, limit_document_context, validated_block_ids
from ..models import (
    Attribute,
    EvidenceAssessment,
    Insight,
    LLMClientProtocol,
    VALID_EVIDENCE_STRENGTHS,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000


def assess_evidence(
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
) -> EvidenceAssessment:
    """Assess whether external evidence grounds the document target for one unit."""
    system_prompt = _system_prompt(
        attribute=attribute,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
    )
    user_message = _user_message(attribute, doc_text, insights)

    raw = llm_client.call(
        system_prompt, user_message, max_tokens=max_tokens, images=images
    )
    parsed = _parse(raw)
    if not parsed or not _has_valid_lineage(parsed, insights):
        logger.warning("evidence_assessor produced no parsable JSON for %s; retrying once", attribute.name)
        raw = llm_client.call(
            system_prompt, user_message, max_tokens=max_tokens, images=images
        )
        parsed = _parse(raw)

    if not parsed or not _has_valid_lineage(parsed, insights):
        return _failed_assessment(attribute.name)

    strength = str(parsed.get("strength", "")).strip().lower()
    if strength not in VALID_EVIDENCE_STRENGTHS:
        strength = "unknown"
    reason = str(parsed.get("reason", "")).strip() or "assessment failed"
    doc_target = str(parsed.get("doc_target", "")).strip()
    selected = _selected_insights(parsed, insights)
    supporting_findings = _dedupe_findings(
        finding for insight in selected for finding in insight.supporting_findings
    )
    return EvidenceAssessment(
        attribute_ref=attribute.name,
        strength=strength,
        reason=reason,
        doc_target=doc_target,
        doc_block_ids=validated_block_ids(
            parsed.get("doc_block_ids"), document_block_ids(doc_text)
        ),
        supporting_insight_ids=[insight.id for insight in selected],
        supporting_findings=supporting_findings,
    )


def _system_prompt(
    *,
    attribute: Attribute,
    indication: str,
    intervention_class: str,
    framing: str = "",
) -> str:
    framing = (
        framing.strip()
        or "Assess the document's stated target or commitment against the external evidence "
        "without assuming a particular document type."
    ).replace("{intervention_class}", intervention_class).replace(
        "{indication}", indication
    )
    return (
        "You assess weight of evidence for ONE variable.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        f"Document-specific interpretation:\n{framing}\n\n"
        "Task:\n"
        "1. Locate this variable's target value in the document text. If no target is stated, handle that gracefully and note it in the reason.\n"
        "If no external-evidence insights are supplied, still extract doc_target and doc_block_ids, "
        "but return strength=unknown with no supporting insight indices.\n"
        "2. Identify which claim form applies:\n"
        "   - IMPROVEMENT TARGET: judge whether the improvement over the current baseline is justified and achievable.\n"
        "   - THRESHOLD OR CONSTRAINT: judge whether current products or evidence show the bar can be met; already meeting it is support, not weakness.\n"
        "   - PLAN COMMITMENT OR ASSUMPTION: judge whether external benchmarks support its feasibility, timing, scale, cost, or requirements.\n"
        "3. Weigh the actual cited evidence by directness, study design, population/product comparability, regulatory relevance, and limitations.\n\n"
        "Strength enum (apply to the claim form above):\n"
        "- well_grounded: strong, directly comparable evidence supports achievability, justification, or feasibility.\n"
        "- partial: the target is plausibly supported, but the evidence has gaps.\n"
        "- thin: evidence is sparse, indirect, or preclinical-only.\n"
        "- unsupported: no evidence supports the target being achievable or justified. Do NOT use this merely because a threshold target is unambitious or already met - that is well_grounded.\n"
        "- unknown: the evidence cannot be assessed.\n\n"
        "Also return doc_target: a SHORT phrase stating ONLY what THIS document targets for "
        "this field (e.g. \"co-administration with routine child/adult vaccines\"). Quote the "
        "document, do not mix in external evidence. Empty string if the document states no target.\n"
        "Return doc_block_ids containing the exact [block:<id>] markers supporting doc_target. "
        "Return supporting_insight_indices containing ONLY the numbered insights actually used "
        "for the grounding judgment; do not cite every available insight.\n"
        "Discovery-track labels are retrieval provenance only. Never treat a counterfactual "
        "or precedent track as proof of the insight's meaning or strength.\n"
        "reason: one sentence (<=25 words) giving ONLY your evidence judgment - do NOT restate "
        "the document target (that is doc_target's job).\n\n"
        "Return ONLY JSON. No markdown, no commentary. Format:\n"
        '{"strength": "partial", "doc_target": "...", "doc_block_ids": ["b-0001"], '
        '"supporting_insight_indices": [0, 2], "reason": "..."}'
    )


def _user_message(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
) -> str:
    doc_text = limit_document_context(doc_text)
    lines = [
        "Document text:",
        doc_text,
        "",
        f"Variable: {attribute.name}",
        f"Definition: {attribute.description}",
        "",
        "External-evidence insights for this variable:",
    ]
    for i, insight in enumerate(insights):
        urls = ", ".join(f.url for f in insight.supporting_findings)
        lines.append(f"[{i}] ({insight.id}) {insight.statement}")
        if insight.query_tracks:
            lines.append(f"    discovery tracks: {', '.join(insight.query_tracks)}")
        if urls:
            lines.append(f"    sources: {urls}")
    lines.append("\nAssess the evidence now.")
    return "\n".join(lines)


def _failed_assessment(
    attribute_ref: str,
) -> EvidenceAssessment:
    return EvidenceAssessment(
        attribute_ref=attribute_ref,
        strength="unknown",
        reason="assessment failed",
        supporting_findings=[],
    )


def _selected_insights(parsed: dict, insights: list[Insight]) -> list[Insight]:
    raw = parsed.get("supporting_insight_indices", []) or []
    indices = list(
        dict.fromkeys(
            item
            for item in raw
            if isinstance(item, int)
            and not isinstance(item, bool)
            and 0 <= item < len(insights)
        )
    )
    return [insights[index] for index in indices]


def _has_valid_lineage(parsed: dict, insights: list[Insight]) -> bool:
    strength = str(parsed.get("strength", "")).strip().lower()
    return strength == "unknown" or bool(_selected_insights(parsed, insights))


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
