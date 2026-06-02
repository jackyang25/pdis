"""Stage 1: derive web search queries from one TPP attribute variable.

Each attribute is treated as a self-contained topic. The monitor pipeline
calls this stage once per attribute and feeds the resulting focused queries
into searcher.
"""

from __future__ import annotations

import json
import logging
import re

from ..models import Attribute, LLMClientProtocol, MonitorTypeConfig

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 1000


def extract_queries_for_variable(
    attribute: Attribute,
    config: MonitorTypeConfig,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    queries_per_variable: int,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Generate web search queries focused on a single TPP attribute variable."""
    system_prompt = _system_prompt_for_variable(
        config,
        indication=indication,
        attribute=attribute,
        queries_per_variable=queries_per_variable,
    )
    user_message = _user_message_for_variable(attribute)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    queries = _parse_queries(raw)
    if not queries:
        logger.warning(
            "query_extractor produced no parsable queries for %r; retrying once",
            attribute.name,
        )
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        queries = _parse_queries(raw)

    return queries[:queries_per_variable]


def _system_prompt_for_variable(
    config: MonitorTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    queries_per_variable: int,
) -> str:
    parts = [
        "You generate web search queries to surface up-to-date information "
        f"relevant to ONE TPP variable: {attribute.name}.",
        f"Product class: {config.intervention_class}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must be about the specific TPP variable named above and "
        "nothing else. This document has separate variables for efficacy, safety, "
        "dosing, duration, cost, etc. - do NOT pull those topics into this variable's "
        "queries unless THIS variable IS that topic. The domain guidance below tells you "
        "HOW to search (which sources, recency, modalities); it does not widen the SUBJECT "
        "beyond this one variable. Example: for the variable \"Indication\", search the "
        "disease/target-population scope (e.g. which products are indicated for the "
        "disease) - not efficacy percentages or dosing schedules.",
        config.query_extraction_guidance.strip(),
    ]
    if config.priority_sources:
        parts.append(
            "When relevant, try to name priority sources in the query text "
            "(regulatory agencies, registries, literature, key companies): "
            + ", ".join(config.priority_sources)
            + "."
        )
    if config.modalities:
        parts.append(
            "Relevant platform technologies to consider when they bear on "
            "the variable topic: "
            + ", ".join(config.modalities)
            + "."
        )
    parts.append(
        f"Return EXACTLY {queries_per_variable} quer"
        f"{'y' if queries_per_variable == 1 else 'ies'} as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words. Each query must be "
        f"specific to the {attribute.name} variable. Example:\n"
        '["FDA EMA RSV vaccine efficacy safety 2025"]'
    )
    return "\n\n".join(parts)


def _user_message_for_variable(attribute: Attribute) -> str:
    return (
        f"TPP variable: {attribute.name}\n"
        f"What this variable covers: {attribute.description}\n\n"
        "Generate the queries for this variable now."
    )


def _parse_queries(raw: str) -> list[str]:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_array(text))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(q).strip() for q in parsed if str(q).strip()]


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
