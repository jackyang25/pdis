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

One call per variable. A variable no insight reached is recorded ``no_evidence`` on
both axes without a call: absence of retrieved evidence is not proof that no
precedent exists (it may be a search miss), so no model is asked to guess, and the
variable is kept rather than dropped. An answer that stays invalid after one retry,
is refused, or whose provider fails keeps the variable with both axes
``not_assessed`` and the failure's code: ``unknown`` is the model's statement that
the evidence is too sparse.
"""

from __future__ import annotations

from shared.ai import RECORDABLE_FAILURES, Effort, ModelTask, failure_code

from ..ai import request_validated
from ..ai_contracts import precedent_assessment
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
    Insight,
    LLMClientProtocol,
    PrecedentSignal,
    VALID_PRECEDENT,
    VALID_PRECEDENT_OUTCOMES,
)

#: One signal per variable: both axes are judgements about the variable's set.
VARIABLES_PER_REQUEST = 1
#: The reasoning tier at low effort, by measurement (README, Call policy): the fast tier
#: called two of four outcomes `favorable` that both reasoning efforts called `mixed`;
#: low effort matched medium at a median 2.9 s against 4.2 s.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "low"
#: Two labels, one sentence and two index lists; the rest is reasoning room.
MAX_TOKENS = 16000


def classify_precedent(
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
) -> PrecedentSignal:
    """Classify whether this variable's target/approach has precedent."""
    if not attribute.document_target:
        raise ValueError(f"{attribute.name} has no document target to classify")
    if not insights:
        return no_evidence_precedent(attribute)

    def parse(parsed: object) -> PrecedentSignal:
        if not isinstance(parsed, dict):
            raise ValueError("no structured classification was returned")
        precedent = str(parsed.get("precedent", "")).strip().lower()
        outcome = str(parsed.get("outcome", "")).strip().lower()
        reason = str(parsed.get("reason", "")).strip()
        if precedent not in VALID_PRECEDENT or outcome not in VALID_PRECEDENT_OUTCOMES:
            raise ValueError("precedent and outcome must come from their closed lists")
        if not reason:
            raise ValueError("a reason is required")
        coverage_insights = selected_insights(parsed.get("coverage_insight_indices"), insights)
        outcome_insights = selected_insights(parsed.get("outcome_insight_indices"), insights)
        if precedent != "unknown" and not coverage_insights:
            raise ValueError("a coverage other than unknown must cite its insights")
        if outcome != "unknown" and not outcome_insights:
            raise ValueError("an outcome other than unknown must cite its insights")
        selected = list({
            insight.id: insight for insight in [*coverage_insights, *outcome_insights]
        }.values())
        return PrecedentSignal(
            attribute_ref=attribute.name,
            precedent=precedent,
            outcome=outcome,
            reason=reason,
            doc_block_ids=list(attribute.block_ids),
            coverage_insight_ids=[insight.id for insight in coverage_insights],
            outcome_insight_ids=[insight.id for insight in outcome_insights],
            supporting_insight_ids=[insight.id for insight in selected],
            supporting_findings=supporting_findings(selected),
        )

    try:
        return request_validated(
            llm_client,
            precedent_assessment(len(insights)),
            build_system_prompt(
                attribute=attribute,
                indication=indication,
                intervention_class=intervention_class,
                framing=framing,
            ),
            binding_message(binding),
            max_tokens=max_tokens,
            parse=parse,
            failure=f"Precedent classification failed for {attribute.name}",
            images=images,
            trailing_text=insights_message(insights, "Classify the precedent now."),
            task=TASK,
            effort=EFFORT,
        )
    except RECORDABLE_FAILURES as exc:
        return not_assessed_precedent(attribute, str(exc), failure_code(exc))


def not_assessed_precedent(attribute: Attribute, reason: str, code: str) -> PrecedentSignal:
    """The record for a variable a stage obtained no precedent for, on both axes: this
    one's call, or the reading of its evidence before it."""
    return PrecedentSignal(
        attribute_ref=attribute.name,
        precedent=NOT_ASSESSED,
        outcome=NOT_ASSESSED,
        reason=reason,
        doc_block_ids=list(attribute.block_ids),
        failure_code=code,
    )


def no_evidence_precedent(attribute: Attribute) -> PrecedentSignal:
    """The record for a variable no insight reached, on both axes, with no model reason."""
    return PrecedentSignal(
        attribute_ref=attribute.name,
        precedent=NO_EVIDENCE,
        outcome=NO_EVIDENCE,
        doc_block_ids=list(attribute.block_ids),
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
        "Each insight lists the records it rests on with their source, evidence class, "
        "publication date and the opening of their excerpt. Read who attempted what, and "
        "when, from those records; an excerpt marked as a search engine's summary "
        "describes a source rather than quoting it.\n\n"
        "Discovery-track labels are retrieval provenance only; classify the stated evidence, "
        "not the track name. Return only the schema-bound response."
    )
