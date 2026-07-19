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
from concurrent.futures import ThreadPoolExecutor

from ..context import document_block_ids, validated_block_ids
from ..models import Attribute, LLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8000
UNIT_CONTEXT_CHARS = 350_000
UNIT_EXTRACTION_WORKERS = 4


def extract_units(
    doc_text: str,
    *,
    intervention_class: str,
    source_type: str,
    indication: str,
    llm_client: LLMClientProtocol,
    images_by_block_id: dict[str, str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Attribute]:
    """Extract the document's checkable units. Returns `Attribute`s (name unique
    within the run, used as the downstream `attribute_ref`)."""
    if not doc_text.strip():
        return []
    system_prompt = _system_prompt(intervention_class, source_type, indication)
    chunks = _document_chunks(doc_text)

    def extract_chunk(indexed: tuple[int, str]) -> list[Attribute]:
        chunk_index, chunk = indexed
        user_message = _user_message(chunk)
        allowed_block_ids = document_block_ids(chunk)
        images = [
            {"block_id": block_id, "data_url": image}
            for block_id, image in (images_by_block_id or {}).items()
            if block_id in allowed_block_ids
        ]
        raw = llm_client.call(
            system_prompt,
            user_message,
            max_tokens=max_tokens,
            images=images or None,
        )
        chunk_units = _parse(raw, allowed_block_ids)
        if not chunk_units:
            logger.warning(
                "unit_extractor produced no parsable units for chunk %d; retrying once",
                chunk_index,
            )
            raw = llm_client.call(
                system_prompt,
                user_message,
                max_tokens=max_tokens,
                images=images or None,
            )
            chunk_units = _parse(raw, allowed_block_ids)
        return chunk_units

    workers = max(1, min(UNIT_EXTRACTION_WORKERS, len(chunks)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(extract_chunk, enumerate(chunks)))
    units = [unit for chunk_units in results for unit in chunk_units]
    return _dedupe(units)


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
        "- block_ids: the exact [block:<id>] markers containing that claim.\n\n"
        "Return ONLY a JSON array. No markdown, no commentary:\n"
        '[{"name": "...", "description": "...", "block_ids": ["b-0001"]}]'
    )


def _user_message(doc_text: str) -> str:
    return f"Document:\n{doc_text}\n\nExtract the checkable units now."


def _document_chunks(doc_text: str) -> list[str]:
    """Split only between annotated blocks; no document text is discarded."""
    rendered_blocks = re.split(r"\n\n(?=\[block:[^\]]+\])", doc_text)
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for rendered_block in rendered_blocks:
        separator = 2 if current else 0
        if current and current_chars + separator + len(rendered_block) > UNIT_CONTEXT_CHARS:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
            separator = 0
        current.append(rendered_block)
        current_chars += separator + len(rendered_block)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _parse(raw: str, allowed_block_ids: set[str]) -> list[Attribute]:
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
        out.append(
            Attribute(
                name=_slug(str(item.get("name", ""))),
                description=description,
                block_ids=validated_block_ids(item.get("block_ids"), allowed_block_ids),
            )
        )
    return out


def _dedupe(units: list[Attribute]) -> list[Attribute]:
    """Ensure names are unique (they become the downstream attribute_ref)."""
    exact: dict[tuple[str, str], Attribute] = {}
    collapsed: list[Attribute] = []
    for unit in units:
        key = (unit.name, " ".join(unit.description.lower().split()))
        existing = exact.get(key)
        if existing is not None:
            existing.block_ids = list(
                dict.fromkeys([*existing.block_ids, *unit.block_ids])
            )
            continue
        exact[key] = unit
        collapsed.append(unit)

    seen: set[str] = set()
    out: list[Attribute] = []
    for unit in collapsed:
        name = unit.name
        i = 2
        while name in seen:
            name = f"{unit.name}_{i}"
            i += 1
        seen.add(name)
        out.append(
            Attribute(name=name, description=unit.description, block_ids=unit.block_ids)
        )
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
