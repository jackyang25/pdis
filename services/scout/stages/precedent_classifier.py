"""Stage: classify the precedent / novelty of one document unit.

Resolves the ambiguity in a low evidence assessment by keeping two questions
orthogonal: how direct the prior work is, and what happened to that prior work.

How to READ absent precedent is doc-type-specific and supplied by the config's
`precedent_framing`: for a TPP, white space is expected and often intended; for
an IPDP, an unprecedented plan commitment is a feasibility risk to surface.

The evidence dimension alone cannot tell these apart (both score low). This
stage reads the SAME per-variable insights - including the disconfirming
insights surfaced by the counterfactual query track - and labels which story
applies.

One LLM call per variable. Self-gating: returns None when there are no insights,
because absence of retrieved evidence is NOT proof that no precedent exists (it
may be a search miss), so we decline to guess.
"""

from __future__ import annotations

import logging

from services.searcher import Finding

from ..ai import request_structured
from ..ai_contracts import precedent_assessment
from ..context import limit_document_context
from ..models import (
    Attribute,
    Insight,
    LLMClientProtocol,
    PrecedentSignal,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
)

logger = logging.getLogger(__name__)

# Matches evidence_assessor. drift_classifier runs a larger budget because its
# per-insight contract returns lineage for every supplied block.
DEFAULT_MAX_TOKENS = 16000


def classify_precedent(
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
) -> PrecedentSignal | None:
    """Classify whether this variable's target/approach has precedent.

    Returns None for variables with no external evidence: with nothing retrieved we
    cannot distinguish absent precedent from a search miss, so we decline to
    label rather than invent coverage."""
    if (
        not attribute.target_resolved
        or not attribute.document_target
        or not insights
    ):
        return None

    system_prompt = build_system_prompt(
        attribute=attribute,
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
    )
    user_message = _user_message(attribute, doc_text, insights)

    contract = precedent_assessment(len(insights))
    parsed = request_structured(
        llm_client,
        contract,
        system_prompt,
        user_message,
        max_tokens=max_tokens,
        images=images,
        task="fast",
    )
    if not isinstance(parsed, dict) or not _has_valid_lineage(parsed, insights):
        logger.warning(
            "precedent_classifier produced no parsable JSON for %s; retrying once",
            attribute.name,
        )
        parsed = request_structured(
            llm_client,
            contract,
            system_prompt,
            user_message,
            max_tokens=max_tokens,
            images=images,
            task="fast",
        )

    if not isinstance(parsed, dict) or not _has_valid_lineage(parsed, insights):
        return PrecedentSignal(
            attribute_ref=attribute.name,
            precedent="unknown",
            outcome="unknown",
            reason="classification failed",
            supporting_findings=[],
        )

    precedent = str(parsed.get("precedent", "")).strip().lower()
    if precedent not in VALID_PRECEDENT:
        precedent = "unknown"
    outcome = str(parsed.get("outcome", "")).strip().lower()
    if outcome not in VALID_PRECEDENT_OUTCOMES:
        outcome = "unknown"
    reason = str(parsed.get("reason", "")).strip() or "no rationale returned"
    coverage_insights = _selected_insights(
        parsed, insights, key="coverage_insight_indices"
    )
    outcome_insights = _selected_insights(
        parsed, insights, key="outcome_insight_indices"
    )
    selected: list[Insight] = []
    selected_ids: set[str] = set()
    for insight in [*coverage_insights, *outcome_insights]:
        if insight.id in selected_ids:
            continue
        selected_ids.add(insight.id)
        selected.append(insight)
    supporting_findings = _dedupe_findings(
        finding for insight in selected for finding in insight.supporting_findings
    )
    return PrecedentSignal(
        attribute_ref=attribute.name,
        precedent=precedent,
        outcome=outcome,
        reason=reason,
        doc_block_ids=list(attribute.block_ids),
        coverage_insight_ids=[insight.id for insight in coverage_insights],
        outcome_insight_ids=[insight.id for insight in outcome_insights],
        supporting_insight_ids=[insight.id for insight in selected],
        supporting_findings=supporting_findings,
    )


# Generic, doc-agnostic fallback. The real interpretive stance is supplied per
# document type by the config's `precedent_framing`; this is only used if a
# config omits it. No doc-type-specific assumptions live here.
_GENERIC_PRECEDENT_FRAMING = (
    "Assess how directly prior work covers this target or approach, then assess "
    "the outcome of that prior work separately."
)


def build_system_prompt(
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
        "You classify TWO PRECEDENT AXES for ONE variable's target/approach: "
        "how directly prior work covers it, and what outcomes that prior work had.\n\n"
        f"Product class: {intervention_class}. Indication: {indication}.\n"
        f"Variable: {attribute.name}\n"
        f"Definition: {attribute.description}\n"
        + framing + "\n\n"
        "Assess only the canonical document binding supplied in the user message; "
        "do not rewrite, broaden, or replace it.\n\n"
        "Return TWO independent labels. Do not collapse them into one axis.\n"
        "precedent (coverage):\n"
        "- direct: prior comparable attempts pursue this target/approach in this or a "
        "closely comparable indication.\n"
        "- adjacent: only analogous evidence exists, such as the platform in another indication.\n"
        "- none: the evidence covers the area but shows no prior attempt at this target/approach.\n"
        "- unknown: the evidence is too sparse or off-point to judge coverage.\n\n"
        "outcome (what happened to prior work):\n"
        "- favorable: prior attempts materially support feasibility or success.\n"
        "- mixed: prior outcomes conflict or show meaningful successes and limitations.\n"
        "- unfavorable: prior attempts failed, stalled, were withdrawn, or revealed material "
        "safety, durability, feasibility, or regulatory problems.\n"
        "- unknown: there is no usable prior outcome, including when precedent=none.\n\n"
        "Honesty rules:\n"
        "- Absence of evidence is NOT proof of no precedent. Prefer unknown unless the "
        "retrieved evidence actually covers the space.\n"
        "- unfavorable requires actual negative outcomes, not merely weak support.\n"
        "- Judge the target/approach, not whether the number is ambitious.\n\n"
        "reason: one sentence (<=25 words) citing the specific evidence (or its telling "
        "absence) behind your label.\n\n"
        "Return coverage_insight_indices and "
        "outcome_insight_indices separately, containing ONLY the numbered insights used "
        "for each axis. outcome_insight_indices may be empty when outcome=unknown.\n\n"
        "Discovery-track labels are retrieval provenance only; classify the stated evidence, "
        "not the track name. Return only the schema-bound response."
    )


def _user_message(
    attribute: Attribute,
    doc_text: str,
    insights: list[Insight],
) -> str:
    doc_text = limit_document_context(doc_text)
    lines = [
        "Canonical document binding (authoritative; do not reinterpret):",
        doc_text,
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


def _selected_insights(
    parsed: dict,
    insights: list[Insight],
    *,
    key: str,
) -> list[Insight]:
    raw = parsed.get(key, []) or []
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
    precedent = str(parsed.get("precedent", "")).strip().lower()
    outcome = str(parsed.get("outcome", "")).strip().lower()
    coverage_valid = precedent == "unknown" or bool(
        _selected_insights(parsed, insights, key="coverage_insight_indices")
    )
    outcome_valid = outcome == "unknown" or bool(
        _selected_insights(parsed, insights, key="outcome_insight_indices")
    )
    return coverage_valid and outcome_valid
