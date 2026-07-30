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
        "canonical document claim.\n\n"
        "DOCUMENT FRAMING\n"
        + framing + "\n\n"
        "SHARED PRIMITIVE\n"
        + RELATIONSHIP_PRIMITIVE + "\n\n"
        "DECISION PROCEDURE\n"
        "For each Insight, choose ONE relation describing how the Insight relates to "
        "the document content:\n"
        "  - contradicts: directly incompatible with the same claim, candidate, or configuration.\n"
        "  - extends: adds relevant facts, benchmarks, limitations, or gaps not stated in the claim.\n"
        "  - confirms: directly supports the claim or its achievability.\n"
        "  - unrelated: does not meaningfully bear on the claim.\n\n"
        "Rules:\n"
        "- Each Insight gets exactly one relation. Pick the strongest applicable one in "
        "the order contradicts > extends > confirms > unrelated.\n"
        "- Reserve contradicts for evidence that the target itself cannot be achieved, the same "
        "candidate or configuration failed, or a stated fact is wrong. A different comparator "
        "value is normally a benchmark or gap and therefore extends the claim.\n"
        "- Never use 'confirms' merely because a comparator failed, fell below a target, or "
        "demonstrates why the target would be useful. That is contextual evidence and is "
        "normally 'extends'. Keep relation to the document separate from precedent outcome.\n"
        "- Reason is one short sentence (max ~25 words) explaining the choice and citing "
        "the relevant doc topic concisely.\n"
        "- doc_block_ids must contain the document blocks that the relation compares "
        "against. Use an empty list only when no document block applies. "
        f"{BLOCK_ID_JSON_INSTRUCTION}\n"
        "- Prefer 'extends' over 'unrelated' when the Insight is on-topic for the "
        "product class and indication, even if the document doesn't explicitly "
        "mention it. Reserve 'unrelated' for genuinely off-topic findings: "
        "a different disease, a different product class, or administrative noise.\n"
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
