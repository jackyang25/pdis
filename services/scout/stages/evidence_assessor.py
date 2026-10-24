"""Stage: assess weight of evidence for one document unit (attribute/claim).

One request per variable, over every insight retrieved for it: grounding is a
judgement about that set. A variable no insight reached is recorded ``no_evidence``
without a model call - nothing was there to weigh, and that is neither the model's
``unknown`` nor a failure. A model answer that stays invalid after one retry, is
refused, or whose provider fails is ``not_assessed`` with the failure's code - a
processing gap, never a grounding judgement.
"""

from __future__ import annotations

from shared.ai import RECORDABLE_FAILURES, Effort, ModelTask, failure_code

from ..ai import request_validated
from ..ai_contracts import evidence_assessment
from ..insight_evidence import (
    binding_message,
    insights_message,
    selected_insights,
    supporting_findings,
)
from ..models import (
    NO_EVIDENCE,
    NOT_ASSESSED,
    Attribute,
    EvidenceAssessment,
    Insight,
    LLMClientProtocol,
    VALID_EVIDENCE_STRENGTHS,
)

#: One assessment per variable: the answer is one judgement about the variable's set.
VARIABLES_PER_REQUEST = 1
#: The reasoning tier at low effort, by measurement (README, Call policy): one call per
#: variable, and the consequential one. All three policies gave the same four strengths
#: on real RSV evidence; low effort took a median 2.7 s, medium 6.1 s.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "low"
#: One strength, one sentence and a list of indices; the rest is reasoning room.
MAX_TOKENS = 16000


def assess_evidence(
    attribute: Attribute,
    binding: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    images: list[dict[str, str]] | None = None,
    max_tokens: int = MAX_TOKENS,
) -> EvidenceAssessment:
    """Assess whether external evidence grounds the document target for one unit."""
    if not attribute.document_target:
        raise ValueError(f"{attribute.name} has no document target to assess")
    if not insights:
        return no_evidence_assessment(attribute)

    def parse(parsed: object) -> EvidenceAssessment:
        if not isinstance(parsed, dict):
            raise ValueError("no structured assessment was returned")
        strength = str(parsed.get("strength", "")).strip().lower()
        reason = str(parsed.get("reason", "")).strip()
        if strength not in VALID_EVIDENCE_STRENGTHS or not reason:
            raise ValueError("a strength from the closed list and a reason are required")
        selected = selected_insights(parsed.get("supporting_insight_indices"), insights)
        if strength != "unknown" and not selected:
            raise ValueError("a strength other than unknown must cite the insights it used")
        return EvidenceAssessment(
            attribute_ref=attribute.name,
            strength=strength,
            reason=reason,
            doc_target=attribute.document_target,
            doc_block_ids=list(attribute.block_ids),
            supporting_insight_ids=[insight.id for insight in selected],
            supporting_findings=supporting_findings(selected),
        )

    try:
        return request_validated(
            llm_client,
            evidence_assessment(len(insights)),
            build_system_prompt(
                attribute=attribute,
                indication=indication,
                intervention_class=intervention_class,
                framing=framing,
            ),
            binding_message(binding),
            max_tokens=max_tokens,
            parse=parse,
            failure=f"Evidence assessment failed for {attribute.name}",
            images=images,
            trailing_text=insights_message(insights, "Assess the evidence now."),
            task=TASK,
            effort=EFFORT,
        )
    except RECORDABLE_FAILURES as exc:
        return EvidenceAssessment(
            attribute_ref=attribute.name,
            strength=NOT_ASSESSED,
            reason=str(exc),
            doc_target=attribute.document_target,
            doc_block_ids=list(attribute.block_ids),
            failure_code=failure_code(exc),
        )


def no_evidence_assessment(attribute: Attribute) -> EvidenceAssessment:
    """The record for a variable no insight reached: no call, and no reason to quote.

    The reason is empty because no model wrote one; the interface states the absence
    in its own voice, as Drafter does for a variable no source spoke to.
    """
    return EvidenceAssessment(
        attribute_ref=attribute.name,
        strength=NO_EVIDENCE,
        doc_target=attribute.document_target,
        doc_block_ids=list(attribute.block_ids),
    )


def build_system_prompt(
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
        f"Definition: {attribute.description}\n"
        f"Document-specific interpretation:\n{framing}\n\n"
        "Task:\n"
        "1. Assess only the canonical document binding supplied in the user message. "
        "Do not rewrite, broaden, or replace it.\n"
        "2. Identify which claim form applies:\n"
        "   - IMPROVEMENT TARGET: judge whether the improvement over the current baseline is justified and achievable.\n"
        "   - THRESHOLD OR CONSTRAINT: judge whether current products or evidence show the bar can be met; already meeting it is support, not weakness.\n"
        "   - PLAN COMMITMENT OR ASSUMPTION: judge whether external benchmarks support its feasibility, timing, scale, cost, or requirements.\n"
        "3. Weigh the actual cited evidence by directness, study design, population/product comparability, regulatory relevance, recency, and limitations. "
        "Each insight lists the records it rests on with their source, evidence class, publication date and the opening of their excerpt: read design and relevance from those, not from the insight's wording. "
        "An excerpt marked as a search engine's summary is a description of a source, weaker than the source's own text.\n\n"
        "Strength enum (apply to the claim form above):\n"
        "- well_grounded: strong, directly comparable evidence supports achievability, justification, or feasibility.\n"
        "- partial: the target is plausibly supported, but the evidence has gaps.\n"
        "- thin: evidence is sparse, indirect, or preclinical-only.\n"
        "- unsupported: no evidence supports the target being achievable or justified. Do NOT use this merely because a threshold target is unambitious or already met - that is well_grounded.\n"
        "- unknown: the evidence cannot be assessed.\n\n"
        "Return supporting_insight_indices containing ONLY the numbered insights actually used "
        "for the grounding judgment; do not cite every available insight.\n"
        "Discovery-track labels are retrieval provenance only. Never treat a counterfactual "
        "track as negative evidence by itself.\n"
        "reason: one sentence (<=25 words) giving ONLY your evidence judgment - do NOT restate "
        "the document target. Return only the schema-bound response."
    )
