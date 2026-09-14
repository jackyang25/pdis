"""Stage: classify each Insight against the uploaded document(s).

One request per Insight, because the answer is a per-item relation and an
unrelated Insight in the same prompt can sway it. Input: doc excerpts + one
Insight. Output: one Match (relation + reason) per input Insight, in input
order. Throughput comes from pipeline-level fan-out.

Relations (closed enum):
  - contradicts : external finding disagrees with what the doc says
  - extends     : external finding adds new info the doc lacks
  - confirms    : external finding supports what the doc says
  - unrelated   : external finding doesn't speak to anything in the doc

If parsing fails, every Insight is wrapped as Match(insight, "unrelated",
"classifier failed"). The pipeline never raises here - drift is a quality
layer over Insights, not a load-bearing stage.
"""

from __future__ import annotations

import logging

from ..ai import request_structured
from shared.batching import fixed_batches
from ..ai_contracts import drift_batch
from ..context import (
    BLOCK_ID_JSON_INSTRUCTION,
    document_block_ids,
    limit_document_context,
    validated_block_ids,
)
from ..models import Insight, LLMClientProtocol, Match, VALID_RELATIONS
from ..prompt_primitives import RELATIONSHIP_PRIMITIVE

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 24000
# Per-item scope: one relation per insight, so an unrelated insight can never
# sit in this decision's prompt. Speed comes from pipeline-level fan-out.
INSIGHTS_PER_REQUEST = 1


def classify_drift(
    doc_excerpts: list[str],
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Match]:
    if not insights:
        return []
    if len(insights) > INSIGHTS_PER_REQUEST:
        matches: list[Match] = []
        for batch in fixed_batches(insights, INSIGHTS_PER_REQUEST):
            matches.extend(
                classify_drift(
                    doc_excerpts,
                    batch,
                    llm_client,
                    indication=indication,
                    intervention_class=intervention_class,
                    framing=framing,
                    images=images,
                    max_tokens=max_tokens,
                )
            )
        return matches

    system_prompt = build_system_prompt(
        indication=indication,
        intervention_class=intervention_class,
        framing=framing,
    )
    user_message = _user_message(doc_excerpts, insights)
    allowed_block_ids = document_block_ids("\n".join(doc_excerpts))
    contract = drift_batch(len(insights), sorted(allowed_block_ids))

    parsed = _validated_matches(request_structured(
        llm_client,
        contract,
        system_prompt,
        user_message,
        max_tokens=max_tokens,
        images=images,
        task="fast",
    ))
    if not _has_complete_lineage(parsed, len(insights), allowed_block_ids):
        logger.warning(
            "drift_classifier expected %d complete traced entries, got %d; retrying once",
            len(insights), len(parsed),
        )
        parsed = _validated_matches(request_structured(
            llm_client,
            contract,
            system_prompt,
            user_message,
            max_tokens=max_tokens,
            images=images,
            task="fast",
        ))

    by_index: dict[int, dict] = {
        p["index"]: p for p in parsed if isinstance(p.get("index"), int)
    }
    matches: list[Match] = []
    for i, insight in enumerate(insights):
        entry = by_index.get(i, {})
        relation = str(entry.get("relation", "")).strip().lower()
        reason = str(entry.get("reason", "")).strip()
        block_ids = validated_block_ids(
            entry.get("doc_block_ids"), allowed_block_ids
        )
        if relation not in VALID_RELATIONS or not reason:
            relation = "unrelated"
            reason = reason or "Classifier returned no validated relation rationale."
        elif relation != "unrelated" and allowed_block_ids and not block_ids:
            relation = "unrelated"
            reason = "Relation rejected because it lacked valid document-block lineage."
        matches.append(
            Match(
                insight=insight,
                relation=relation,
                reason=reason,
                doc_block_ids=block_ids,
            )
        )
    return matches


def _has_complete_lineage(
    parsed: list[dict],
    insight_count: int,
    allowed_block_ids: set[str],
) -> bool:
    indices = [entry.get("index") for entry in parsed]
    if sorted(
        index
        for index in indices
        if isinstance(index, int) and not isinstance(index, bool)
    ) != list(range(insight_count)):
        return False
    for entry in parsed:
        relation = str(entry.get("relation", "")).strip().lower()
        if relation not in VALID_RELATIONS or not str(entry.get("reason", "")).strip():
            return False
        if (
            relation != "unrelated"
            and allowed_block_ids
            and not validated_block_ids(entry.get("doc_block_ids"), allowed_block_ids)
        ):
            return False
    return True


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
        "- Do not invent doc content not present in the excerpts.\n\n"
        "- Discovery-track labels are retrieval provenance only; they never determine the relation.\n\n"
        "OUTPUT CONTRACT\n"
        "Return every decision in the schema-bound `matches` array. "
        "Every Insight index from the input MUST appear exactly once in the output."
    )


def _user_message(doc_excerpts: list[str], insights: list[Insight]) -> str:
    doc_text = limit_document_context("\n\n=== DOC ===\n".join(doc_excerpts))
    lines = ["Document excerpts:", doc_text, "", "Insights:"]
    for i, ins in enumerate(insights):
        lines.append(
            f"[{i}] ({ins.id}; variable={ins.attribute_ref or 'unknown'}) {ins.statement}"
        )
        if ins.query_tracks:
            lines.append(f"    discovery tracks: {', '.join(ins.query_tracks)}")
    lines.append("\nClassify each Insight now.")
    return "\n".join(lines)


def _validated_matches(parsed: object) -> list[dict]:
    if not isinstance(parsed, list):
        return []
    return [p for p in parsed if isinstance(p, dict)]
