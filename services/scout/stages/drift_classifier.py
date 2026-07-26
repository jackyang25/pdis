"""Stage: classify each Insight against the uploaded document(s).

One LLM call. Input: doc excerpts + list of Insights. Output: a list of
Matches in the same order as the input Insights - each Insight gets
exactly one Match (relation + reason).

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
from ..ai_contracts import drift_batch
from ..context import (
    BLOCK_ID_JSON_INSTRUCTION,
    document_block_ids,
    limit_document_context,
    validated_block_ids,
)
from ..models import Insight, LLMClientProtocol, Match, VALID_RELATIONS

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 24000
INSIGHTS_BATCH_SIZE = 30


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
    if len(insights) > INSIGHTS_BATCH_SIZE:
        matches: list[Match] = []
        for start in range(0, len(insights), INSIGHTS_BATCH_SIZE):
            batch = insights[start : start + INSIGHTS_BATCH_SIZE]
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

    system_prompt = _system_prompt(
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


def _system_prompt(
    *, indication: str, intervention_class: str, framing: str = ""
) -> str:
    framing = (
        (framing.strip() or _GENERIC_DRIFT_FRAMING)
        .replace("{intervention_class}", intervention_class)
        .replace("{indication}", indication)
    )
    return (
        framing + "\n\n"
        "For each Insight, choose ONE relation describing how the Insight relates to "
        "the document content:\n"
        "  - contradicts : the Insight shows a doc TARGET is unachievable, has been tried "
        "and FAILED, or is otherwise disproven; OR it disputes a FACTUAL statement in the "
        "doc (background, standard of care, epidemiology, regulatory status). A genuine conflict.\n"
        "  - extends     : the Insight adds on-topic factual info the doc lacks - INCLUDING "
        "evidence that an existing/standard product DIFFERS FROM or FALLS SHORT OF a "
        "stated target. A target being ahead of the current standard is a GAP, not a "
        "contradiction.\n"
        "  - confirms    : the Insight supports a claim in the doc, or shows a target is met "
        "or achievable.\n"
        "  - unrelated   : the Insight doesn't meaningfully connect to anything in the doc.\n\n"
        "Rules:\n"
        "- Each Insight gets exactly one relation. Pick the strongest applicable one in "
        "the order contradicts > extends > confirms > unrelated.\n"
        "- Do NOT use 'contradicts' merely because the evidence reports a different value "
        "than a target (e.g. an existing four-dose vaccine when the target is <=3 doses, or "
        "a current product costing more than a cost target). That difference is the GAP the "
        "target aims to close -> use 'extends'. Reserve 'contradicts' for evidence that the "
        "target itself cannot be achieved / has failed, or that a stated FACT is wrong.\n"
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
