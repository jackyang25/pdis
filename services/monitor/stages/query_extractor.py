"""Stage 1: derive web search queries from doc content + the 4 primitives.

Single LLM call. Input is a summary of the uploaded docs plus the
primitives (org/source_type/intervention_class/indication) plus the
config's domain-specific guidance. Output is a list of search query
strings to feed into searcher.
"""

from __future__ import annotations

import json
import logging
import re

from ..models import MonitorTypeConfig, OpenAIClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 2000
MAX_DOC_CONTEXT_CHARS = 8000


def extract_queries(
    doc_excerpts: list[str],
    config: MonitorTypeConfig,
    llm_client: OpenAIClientProtocol,
    *,
    indication: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Return a list of search queries grounded in doc content + primitives."""
    system_prompt = _build_system_prompt(config, indication=indication)
    user_message = _build_user_message(doc_excerpts, config)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    queries = _parse_queries(raw)
    if not queries:
        logger.warning("query_extractor produced no parsable queries; retrying once")
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        queries = _parse_queries(raw)

    return queries[: config.num_queries]


def _build_system_prompt(config: MonitorTypeConfig, *, indication: str) -> str:
    return "\n\n".join([
        "You generate web search queries to surface up-to-date information "
        "relevant to a product profile document.",
        f"Product class: {config.intervention_class}. Indication: {indication}.",
        config.query_extraction_guidance.strip(),
        f"Return EXACTLY {config.num_queries} queries as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words. Example:\n"
        '["FDA RSV vaccine approval 2025", "Phase 3 RSV vaccine efficacy elderly"]',
    ])


def _build_user_message(doc_excerpts: list[str], config: MonitorTypeConfig) -> str:
    joined = "\n\n=== DOC ===\n".join(doc_excerpts)
    if len(joined) > MAX_DOC_CONTEXT_CHARS:
        joined = joined[:MAX_DOC_CONTEXT_CHARS] + "\n...[truncated]"
    return f"Document content:\n\n{joined}\n\nGenerate the queries now."


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
