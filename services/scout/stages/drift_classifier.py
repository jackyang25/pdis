"""Stage: classify one Insight against the document claim it was retrieved for.

One request per Insight, because the answer is a per-item relation and an
unrelated Insight in the same prompt can sway it. Input: the variable's canonical
binding and one Insight with the records it rests on. Output: one Match.
Throughput comes from pipeline-level fan-out.

Relations (closed enum):
  - contradicts : external finding disagrees with what the doc says
  - extends     : external finding adds new info the doc lacks
  - confirms    : external finding supports what the doc says
  - unrelated   : external finding doesn't speak to anything in the doc

An answer that stays invalid after one retry, is cut off twice, is refused, or
whose provider fails keeps its Insight as a ``not_assessed`` Match with the
failure's code, never as ``unrelated``: no relation was obtained, and "off-topic"
is a claim about the evidence.
"""

from __future__ import annotations

from shared.ai import RECORDABLE_FAILURES, Effort, ModelTask, failure_code

from ..ai import request_validated
from ..ai_contracts import drift_relation
from ..context import BLOCK_ID_JSON_INSTRUCTION, document_block_ids, validated_block_ids
from ..insight_evidence import binding_message, render_insight_evidence
from ..models import NOT_ASSESSED, Insight, LLMClientProtocol, Match, VALID_RELATIONS
from ..prompt_primitives import RELATIONSHIP_PRIMITIVE

# Per-item scope: one relation per insight, so an unrelated insight can never
# sit in this decision's prompt. Speed comes from pipeline-level fan-out.
INSIGHTS_PER_REQUEST = 1
#: The reasoning tier at low effort, by measurement (README, Call policy). On 30 real
#: RSV insights the fast tier filed three comparator shortfalls as `contradicts`, which
#: question 2 forbids, and nine comparator results as `confirms` for an unnamed product;
#: the reasoning tier at low and at medium effort agreed on all 30, at a median 2.8 s per
#: call against 2.3 s. Medium effort changed nothing and spent twenty times the reasoning.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "low"
#: The answer is one relation, one sentence and a few block IDs; the rest is room
#: for reasoning. A cut-off reply is asked again as `shared.ai.after_truncation` says.
MAX_TOKENS = 8000


def classify_drift(
    binding: str,
    insight: Insight,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    images: list[dict[str, str]] | None = None,
    max_tokens: int = MAX_TOKENS,
) -> Match:
    """One Match for one Insight, from its own request.

    ``binding`` is the variable's canonical binding, the same for every insight of
    the variable, so it leads the request; the insight follows the images.
    """
    allowed_block_ids = document_block_ids(binding)

    def parse(parsed: object) -> Match:
        if not isinstance(parsed, dict):
            raise ValueError("no structured relation was returned")
        relation = str(parsed.get("relation", "")).strip().lower()
        reason = str(parsed.get("reason", "")).strip()
        if relation not in VALID_RELATIONS or not reason:
            raise ValueError("a relation from the closed list and a reason are required")
        block_ids = validated_block_ids(parsed.get("doc_block_ids"), allowed_block_ids)
        if relation != "unrelated" and allowed_block_ids and not block_ids:
            raise ValueError("a relation other than unrelated must cite document blocks")
        return Match(insight=insight, relation=relation, reason=reason, doc_block_ids=block_ids)

    try:
        return request_validated(
            llm_client,
            drift_relation(sorted(allowed_block_ids)),
            build_system_prompt(
                indication=indication,
                intervention_class=intervention_class,
                framing=framing,
            ),
            binding_message(binding),
            max_tokens=max_tokens,
            parse=parse,
            failure=f"Drift classification failed for {insight.id}",
            images=images,
            trailing_text=_insight_message(insight),
            task=TASK,
            effort=EFFORT,
        )
    except RECORDABLE_FAILURES as exc:
        return Match(
            insight=insight,
            relation=NOT_ASSESSED,
            reason=str(exc),
            failure_code=failure_code(exc),
        )


# Generic, doc-agnostic fallback. The real interpretive stance is supplied per
# document type by the config's `drift_framing`; this is only used if a config
# omits it. No doc-type-specific assumptions live here.
_GENERIC_DRIFT_FRAMING = (
    "You compare external-evidence insights against a {intervention_class} "
    "product-development document targeting {indication}. The document states "
    "intended targets or plans; treat external evidence about current or "
    "standard-of-care products as context for assessing them."
)


def build_system_prompt(
    *, indication: str, intervention_class: str, framing: str = ""
) -> str:
    framing = (
        (framing.strip() or _GENERIC_DRIFT_FRAMING)
        .replace("{intervention_class}", intervention_class)
        .replace("{indication}", indication)
    )
    return (
        "ROLE\n"
        "Classify the logical relationship between each external-evidence Insight and the "
        "canonical document claim. This is NOT a screen for whether the external product "
        "would satisfy the document's specification. Ask whether the evidence refutes the "
        "document assertion, not whether the external product has different features.\n\n"
        "DOCUMENT FRAMING\n"
        + framing + "\n\n"
        "SHARED PRIMITIVE\n"
        + RELATIONSHIP_PRIMITIVE + "\n\n"
        "DECISION PROCEDURE\n"
        "Work through these four questions IN ORDER and stop at the first that answers "
        "yes. Each Insight gets exactly one relation. Do not weigh the four labels "
        "against each other and pick a favourite - answer the questions.\n\n"
        "  1. Does the Insight have no substantive bearing on this assertion, its "
        "feasibility, or its relevant context - administrative noise, an unrelated "
        "endpoint, or only commentary about what the search "
        "did not find, with no external fact? -> unrelated\n"
        "  2. Establish that the evidence applies to the subject of the assertion. A named "
        "external product must not be assumed to be the document's unnamed intended product. "
        "For a target, a different product's nonconformance is extends, not contradicts. "
        "Only a demonstrated barrier applying to the intended target itself can refute its "
        "feasibility. For a factual or universal assertion, use its explicitly stated scope. "
        "Failure to meet a specification by an alternative product is NOT evidence "
        "that the intended product cannot meet it. Within the established subject, "
        "time, and conditions, does the Insight establish a fact incompatible with "
        "the specific assertion or constraint? -> contradicts\n"
        "  3. Does the Insight show the target HAS been achieved or otherwise holds? "
        "-> confirms\n"
        "  4. Otherwise it bears on the claim without settling it. -> extends\n\n"
        "Rules:\n"
        "- Question 2 is narrow on purpose. Check the assertion before applying document "
        "framing: a specific factual statement remains factual even inside an aspirational "
        "document. Evidence about a DIFFERENT population, comparator, product, setting, "
        "or endpoint normally adds context (extends) or is off-topic (unrelated). "
        "Exception: an explicit universal claim covers every member of its stated scope, "
        "so a counterexample within that scope can contradict it. Do not infer universality.\n"
        "- Missing public confirmation, no matching search result, or an excerpt omitting "
        "a date does not establish that the document is wrong. If an Insight mixes such "
        "search commentary with an external fact, classify the external fact alone. "
        "An explicit source statement of non-approval, failure, or absence is different: "
        "it may contradict a claim about the same subject and time, but a current "
        "not-yet status alone does not refute a future expectation.\n"
        "- Question 3 wins even when the Insight also adds new facts. Supporting evidence "
        "that happens to be informative is still confirms; do not downgrade it to extends "
        "because it taught you something.\n"
        "- Never use confirms merely because a comparator failed, fell below a target, or "
        "demonstrates why the target would be useful. That is contextual evidence and is "
        "extends. Keep relation to the document separate from precedent outcome.\n"
        "- Reason is one short sentence (max ~25 words) explaining the choice and citing "
        "the relevant doc topic concisely. For contradicts, name the specific assertion "
        "and the incompatible external fact; merely listing different features is not a "
        "contradiction rationale. If that incompatibility requires an unsupported assumption, "
        "use extends for on-topic evidence.\n"
        "- doc_block_ids must contain the document blocks that the relation compares "
        "against. Use an empty list only when no document block applies. "
        f"{BLOCK_ID_JSON_INSTRUCTION}\n"
        "- At question 1, shared product class or indication alone does not establish "
        "relevance to the specific claim. An external fact that informs its feasibility "
        "or provides a relevant alternative or benchmark is on-topic even if not "
        "mentioned in the document; continue to question 2.\n"
        "- Each supporting record shows its source, evidence class, publication date and "
        "the opening of its excerpt. Establish the time and subject at question 2 from "
        "them, not from the Insight's wording alone; a date stated only to the year "
        "covers the whole year. An excerpt marked as a search engine's summary describes "
        "the source rather than quoting it.\n"
        "- Do not invent document content not present in the binding.\n\n"
        "- Discovery-track labels are retrieval provenance only; they never determine the relation.\n\n"
        "OUTPUT CONTRACT\n"
        "Return one decision for the one Insight supplied, in the schema-bound `match` "
        "object."
    )


def _insight_message(insight: Insight) -> str:
    return (
        "\n\nInsight to classify, with the records it rests on:\n"
        + render_insight_evidence(insight, label=f"({insight.id})")
        + "\n\nClassify this Insight now."
    )
