"""The 'extract' unit provider: pull a document's checkable units from the doc.

For doc types without a fixed attribute vocabulary (e.g. an IPDP), an LLM reads
the document and extracts its own testable assertions - milestones, timelines,
cost/feasibility assumptions, regulatory expectations - and returns them as
`Attribute`s (name + description), the SAME shape the vocabulary provider yields.
So everything downstream (search → drift → evidence → conformity → precedent) is
unchanged; only where the units come from differs.

Self-gating / robust: an unreadable doc or unparsable reply yields no units,
which the pipeline treats like "no attributes" (empty result).
"""

from __future__ import annotations

import json
import logging
import re

from ..models import Attribute, LLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8000
MAX_DOC_CONTEXT_CHARS = 120000
MAX_UNITS = 60


def extract_units(
    doc_text: str,
    *,
    intervention_class: str,
    source_type: str,
    indication: str,
    llm_client: LLMClientProtocol,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Attribute]:
    """Extract the document's checkable units. Returns `Attribute`s (name unique
    within the run, used as the downstream `attribute_ref`)."""
    if not doc_text.strip():
        return []
    system_prompt = _system_prompt(intervention_class, source_type, indication)
    user_message = _user_message(doc_text)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    units = _parse(raw)
    if not units:
        logger.warning("unit_extractor produced no parsable units; retrying once")
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        units = _parse(raw)
    return _dedupe(units)[:MAX_UNITS]


def _system_prompt(intervention_class: str, source_type: str, indication: str) -> str:
    return (
        "You extract the CHECKABLE UNITS from a product-development document so a "
        "downstream tool can test each against real-world evidence.\n\n"
        f"Document type: {source_type}. Product class: {intervention_class}. Indication: {indication}.\n\n"
        "A unit is a concrete assertion the document makes that could be confirmed or "
        "challenged by external evidence - a milestone with a date, a timeline, a cost or "
        "volume projection, a regulatory expectation, a feasibility or efficacy assumption, "
        "a manufacturing or access plan. Skip pure background, narrative, and boilerplate "
        "that makes no testable claim.\n\n"
        "For each unit return:\n"
        "- name: a short snake_case label, unique within the document (e.g. "
        '"regulatory_approval_timeline", "cogs_per_dose_target").\n'
        "- description: one sentence stating the specific claim/target, grounded in the "
        "document (include the number/date where the doc gives one).\n\n"
        "Return ONLY a JSON array. No markdown, no commentary:\n"
        '[{"name": "...", "description": "..."}]'
    )


def _user_message(doc_text: str) -> str:
    if len(doc_text) > MAX_DOC_CONTEXT_CHARS:
        doc_text = doc_text[:MAX_DOC_CONTEXT_CHARS] + "\n...[truncated]"
    return f"Document:\n{doc_text}\n\nExtract the checkable units now."


def _parse(raw: str) -> list[Attribute]:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_array(text))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[Attribute] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        out.append(Attribute(name=_slug(str(item.get("name", ""))), description=description))
    return out


def _dedupe(units: list[Attribute]) -> list[Attribute]:
    """Ensure names are unique (they become the downstream attribute_ref)."""
    seen: set[str] = set()
    out: list[Attribute] = []
    for unit in units:
        name = unit.name
        i = 2
        while name in seen:
            name = f"{unit.name}_{i}"
            i += 1
        seen.add(name)
        out.append(Attribute(name=name, description=unit.description))
    return out


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "unit"


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
