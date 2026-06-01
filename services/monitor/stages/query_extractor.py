"""Stage 1: derive web search queries from one labeled doc section.

Each section is treated as a self-contained topic. The monitor pipeline
calls this stage once per section and feeds the resulting focused queries
into searcher.
"""

from __future__ import annotations

import json
import logging
import re

from ..models import MonitorTypeConfig, OpenAIClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 1000
MAX_SECTION_CONTEXT_CHARS = 4000


def extract_queries_for_section(
    section_label: str,
    section_text: str,
    config: MonitorTypeConfig,
    llm_client: OpenAIClientProtocol,
    *,
    indication: str,
    queries_per_section: int,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Generate web search queries focused on a single doc section.

    Each section is treated as a self-contained topic (e.g. "Efficacy",
    "Safety", "Storage"). The LLM sees the section's content plus the
    config's domain guidance, and emits queries scoped to that topic.
    """
    if not section_text.strip():
        return []

    system_prompt = _system_prompt_for_section(
        config,
        indication=indication,
        section_label=section_label,
        queries_per_section=queries_per_section,
    )
    user_message = _user_message_for_section(section_label, section_text)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    queries = _parse_queries(raw)
    if not queries:
        logger.warning(
            "query_extractor produced no parsable queries for section %r; retrying once",
            section_label,
        )
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        queries = _parse_queries(raw)

    return queries[:queries_per_section]


def _system_prompt_for_section(
    config: MonitorTypeConfig,
    *,
    indication: str,
    section_label: str,
    queries_per_section: int,
) -> str:
    return "\n\n".join([
        "You generate web search queries to surface up-to-date information "
        f"relevant to ONE section of a product profile document: "
        f'"{section_label}".',
        f"Product class: {config.intervention_class}. Indication: {indication}.",
        config.query_extraction_guidance.strip(),
        f"Return EXACTLY {queries_per_section} quer"
        f"{'y' if queries_per_section == 1 else 'ies'} as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words. Each query must be "
        f'specific to the "{section_label}" topic. Example:\n'
        '["FDA RSV vaccine approval 2025 elderly adults"]',
    ])


def _user_message_for_section(section_label: str, section_text: str) -> str:
    if len(section_text) > MAX_SECTION_CONTEXT_CHARS:
        section_text = section_text[:MAX_SECTION_CONTEXT_CHARS] + "\n...[truncated]"
    return (
        f"Section: {section_label}\n\n"
        f"Section content:\n\n{section_text}\n\n"
        f"Generate the queries for this section now."
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
