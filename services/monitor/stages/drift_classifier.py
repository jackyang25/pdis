"""Stage: classify each Insight against the uploaded document(s).

One LLM call. Input: doc excerpts + list of Insights. Output: a list of
Matches in the same order as the input Insights - each Insight gets
exactly one Match (relation + reason).

Relations (closed enum):
  - contradicts : web finding disagrees with what the doc says
  - extends     : web finding adds new info the doc lacks
  - confirms    : web finding supports what the doc says
  - unrelated   : web finding doesn't speak to anything in the doc

If parsing fails, every Insight is wrapped as Match(insight, "unrelated",
"classifier failed"). The pipeline never raises here - drift is a quality
layer over Insights, not a load-bearing stage.
"""

from __future__ import annotations

import json
import logging
import re

from ..models import Insight, LLMClientProtocol, Match, VALID_RELATIONS

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 24000
MAX_DOC_CONTEXT_CHARS = 60000
INSIGHTS_BATCH_SIZE = 30


def classify_drift(
    doc_excerpts: list[str],
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
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
                    max_tokens=max_tokens,
                )
            )
        return matches

    system_prompt = _system_prompt(indication=indication, intervention_class=intervention_class)
    user_message = _user_message(doc_excerpts, insights)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    parsed = _parse(raw)
    if len(parsed) != len(insights):
        logger.warning(
            "drift_classifier expected %d entries, got %d; retrying once",
            len(insights), len(parsed),
        )
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        parsed = _parse(raw)

    by_index: dict[int, dict] = {
        p["index"]: p for p in parsed if isinstance(p.get("index"), int)
    }

    matches: list[Match] = []
    for i, insight in enumerate(insights):
        entry = by_index.get(i, {})
        relation = str(entry.get("relation", "")).strip().lower()
        reason = str(entry.get("reason", "")).strip()
        if relation not in VALID_RELATIONS:
            relation = "unrelated"
            reason = reason or "classifier failed"
        matches.append(Match(insight=insight, relation=relation, reason=reason))
    return matches


def _system_prompt(*, indication: str, intervention_class: str) -> str:
    return (
        f"You compare web-derived insights against a product profile document for a "
        f"{intervention_class} targeting {indication}.\n\n"
        "For each Insight, choose ONE relation describing how the Insight relates to "
        "the document content:\n"
        "  - contradicts : Insight disagrees with a claim in the doc\n"
        "  - extends     : Insight adds factual info the doc lacks but is on-topic\n"
        "  - confirms    : Insight supports a claim already in the doc\n"
        "  - unrelated   : Insight doesn't meaningfully connect to anything in the doc\n\n"
        "Rules:\n"
        "- Each Insight gets exactly one relation. Pick the strongest applicable one in "
        "the order contradicts > extends > confirms > unrelated.\n"
        "- Reason is one short sentence (max ~25 words) explaining the choice and citing "
        "the relevant doc topic concisely.\n"
        "- Prefer 'extends' over 'unrelated' when the Insight is on-topic for the "
        "product class and indication, even if the document doesn't explicitly "
        "mention it. Reserve 'unrelated' for genuinely off-topic findings: "
        "a different disease, a different product class, or administrative noise.\n"
        "- Do not invent doc content not present in the excerpts.\n\n"
        "Return ONLY valid JSON. No markdown, no preamble. Format:\n"
        "[\n"
        '  {"index": 0, "relation": "contradicts", "reason": "..."},\n'
        '  {"index": 1, "relation": "extends", "reason": "..."}\n'
        "]\n"
        "Every Insight index from the input MUST appear exactly once in the output."
    )


def _user_message(doc_excerpts: list[str], insights: list[Insight]) -> str:
    doc_text = "\n\n=== DOC ===\n".join(doc_excerpts)
    if len(doc_text) > MAX_DOC_CONTEXT_CHARS:
        doc_text = doc_text[:MAX_DOC_CONTEXT_CHARS] + "\n...[truncated]"
    lines = ["Document excerpts:", doc_text, "", "Insights:"]
    for i, ins in enumerate(insights):
        lines.append(f"[{i}] {ins.statement}")
    lines.append("\nClassify each Insight now.")
    return "\n".join(lines)


def _parse(raw: str) -> list[dict]:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_array(text))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [p for p in parsed if isinstance(p, dict)]


def _strip_fences(s: str) -> str:
    m = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", s, re.DOTALL)
    return m.group(1) if m else s


def _extract_json_array(s: str) -> str:
    decoder = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "[":
            continue
        try:
            parsed, end = decoder.raw_decode(s[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return s[i : i + end]
    return s
