"""Stage: classify the precedent / novelty of one document unit.

Resolves the ambiguity in a low evidence assessment. A unit with little or no
supporting evidence can be one of two OPPOSITE things:

  - NOVEL (white space): nobody has tried this approach yet.
  - DISCONFIRMED: the approach HAS been tried and failed / been contradicted.
    This is a genuine caution.

How to READ a novel result is doc-type-specific and supplied by the config's
`precedent_framing`: for a TPP, white space is expected and often intended; for
an IPDP, an unprecedented plan commitment is a feasibility risk to surface.

The evidence dimension alone cannot tell these apart (both score low). This
stage reads the SAME per-variable insights - including the disconfirming
insights surfaced by the counterfactual query track - and labels which story
applies.

One LLM call per variable. Self-gating: returns None when there are no insights,
because absence of retrieved evidence is NOT proof of novelty (it may be a
search miss), so we decline to guess rather than fake a 'novel' verdict.
"""

from __future__ import annotations

import json
import logging
import re

from services.searcher import Finding

from ..models import (
    Attribute,
    Insight,
    LLMClientProtocol,
    PrecedentSignal,
    VALID_PRECEDENT,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 16000
# Lockstep with the other doc-reading stages so a target near the end of a long
# doc is never cut off in one stage but not another.
MAX_DOC_CONTEXT_CHARS = 120000


def classify_precedent(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> PrecedentSignal | None:
    """Classify whether this variable's target/approach has precedent.

    Returns None for variables with no web evidence: with nothing retrieved we
    cannot distinguish genuine novelty from a search miss, so we decline to
    label rather than invent a 'novel' verdict."""
    if not insights:
        return None

    supporting_findings = _dedupe_findings(
        finding for insight in insights for finding in insight.supporting_findings
    )
    system_prompt = _system_prompt(
        attribute=attribute,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
    )
    user_message = _user_message(attribute, doc_text, insights)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    parsed = _parse(raw)
    if not parsed:
        logger.warning(
            "precedent_classifier produced no parsable JSON for %s; retrying once",
            attribute.name,
        )
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        parsed = _parse(raw)

    if not parsed:
        return PrecedentSignal(
            attribute_ref=attribute.name,
            precedent="unknown",
            reason="classification failed",
            supporting_findings=supporting_findings,
        )

    precedent = str(parsed.get("precedent", "")).strip().lower()
    if precedent not in VALID_PRECEDENT:
        precedent = "unknown"
    reason = str(parsed.get("reason", "")).strip() or "no rationale returned"
    return PrecedentSignal(
        attribute_ref=attribute.name,
        precedent=precedent,
        reason=reason,
        supporting_findings=supporting_findings,
    )


# Generic, doc-agnostic fallback. The real interpretive stance is supplied per
# document type by the config's `precedent_framing`; this is only used if a
# config omits it. No doc-type-specific assumptions live here.
_GENERIC_PRECEDENT_FRAMING = (
    "Where supporting evidence is thin, distinguish genuine novelty (no prior "
    "attempt at this target/approach) from a target that has been tried and failed."
)


def _system_prompt(
    *,
    attribute: Attribute,
    indication: str,
    intervention_class: str,
    framing: str = "",
) -> str:
    framing = (
        (framing.strip() or _GENERIC_PRECEDENT_FRAMING)
        .replace("{intervention_class}", intervention_class)
        .replace("{indication}", indication)
    )
    return (
        "You classify the PRECEDENT of ONE variable's target/approach: has it "
        "been attempted before, and if the evidence is thin, is that because the "
        "approach is genuinely new or because it has been tried and failed?\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        + framing + "\n\n"
        "Choose exactly ONE precedent label:\n"
        "- established: prior products/approaches already pursue this target/method for "
        "this (or a closely comparable) indication.\n"
        "- emerging: no direct precedent for this exact target, but adjacent or analogous "
        "evidence exists (e.g. the same platform/mechanism proven elsewhere).\n"
        "- novel: the surrounding area appears in the evidence, but there is NO prior "
        "attempt at this specific target/approach AND no evidence it has failed - genuine "
        "white space. Use this only when the insights give enough context to be confident "
        "the approach is absent, not merely unsearched.\n"
        "- disconfirmed: the evidence shows this target/approach HAS been tried and failed, "
        "stalled, or been contradicted (null/failed trials, withdrawals, waning, safety "
        "signals). This is the one caution flag.\n"
        "- unknown: the insights are too sparse or off-point to judge precedent.\n\n"
        "Honesty rules:\n"
        "- Absence of evidence is NOT proof of novelty. If you simply found little, prefer "
        "'unknown' over 'novel'. Reserve 'novel' for when the evidence covers the space yet "
        "shows no prior attempt.\n"
        "- 'disconfirmed' requires actual counter-evidence, not merely weak support.\n"
        "- Judge the target/approach, not whether the number is ambitious.\n\n"
        "reason: one sentence (<=25 words) citing the specific evidence (or its telling "
        "absence) behind your label.\n\n"
        "Return ONLY JSON. No markdown, no commentary. Format:\n"
        '{"precedent": "novel", "reason": "..."}'
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
    lines.append("\nClassify the precedent now.")
    return "\n".join(lines)


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
