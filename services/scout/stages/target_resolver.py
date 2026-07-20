"""Bind a canonical investigation-unit definition to its document target.

Dynamic providers already extract the target and its exact blocks. Fixed
providers supply only a stable definition, so this stage locates the matching
document statement. Both paths leave this stage with the same resolved
``Attribute`` contract.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

from ..context import document_block_ids, limit_document_context, validated_block_ids
from ..models import (
    ENTITY_TYPES,
    Attribute,
    LLMClientProtocol,
    parse_evidence_entities,
)

logger = logging.getLogger(__name__)

# GPT-5 reasoning tokens share the completion budget with visible JSON.  A
# 2,000-token cap can therefore end during reasoning before the model emits a
# single character.  Keep this aligned with Scout's other bounded document
# reasoning stages; the value is a ceiling, not a requested output length.
DEFAULT_MAX_TOKENS = 16000


def resolve_document_target(
    attribute: Attribute,
    document_context: str,
    llm_client: LLMClientProtocol,
    *,
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Attribute:
    """Return a resolved unit without changing its definition semantics."""
    if attribute.target_resolved:
        return attribute
    if attribute.definition_mode == "dynamic":
        # Dynamic extraction is required to bind its own claim. Treat a missing
        # target as intentionally absent rather than invoking another stage with
        # a subtly different extraction responsibility.
        return replace(attribute, target_resolved=True)

    allowed_ids = document_block_ids(document_context)
    raw = llm_client.call(
        _system_prompt(attribute),
        _user_message(document_context),
        max_tokens=max_tokens,
        images=images,
    )
    parsed = _parse(raw)
    if parsed is None:
        logger.warning(
            "target_resolver produced no parsable JSON for %s; retrying once",
            attribute.name,
        )
        raw = llm_client.call(
            _system_prompt(attribute),
            _user_message(document_context),
            max_tokens=max_tokens,
            images=images,
        )
        parsed = _parse(raw)

    if parsed is None:
        return replace(attribute, target_resolved=True)
    target = str(parsed.get("document_target", "")).strip()
    block_ids = validated_block_ids(parsed.get("block_ids"), allowed_ids)
    entities = parse_evidence_entities(parsed.get("entities"))
    if not target:
        block_ids = []
        entities = []
    return replace(
        attribute,
        document_target=target,
        block_ids=block_ids,
        entities=entities,
        target_resolved=True,
    )


def _system_prompt(attribute: Attribute) -> str:
    return (
        "You bind ONE fixed evaluation definition to the uploaded document.\n\n"
        f"Unit: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        "Locate only the document's concrete target, constraint, assumption, or "
        "commitment for this unit. Preserve numbers, dates, comparators, and "
        "qualifiers. Do not add external evidence or infer a target the document "
        "does not state. Extract only explicitly named entities whose type is one of: "
        f"{', '.join(sorted(ENTITY_TYPES - {'other'}))}. Include an "
        "identifier only when the document states it. Return the exact [block:<id>] "
        "markers supporting the target. If "
        "the document states no target for this unit, return an empty target and "
        "empty block_ids/entities.\n\n"
        "Return ONLY JSON: "
        '{"document_target": "...", "block_ids": ["document/b-0001"], '
        '"entities": [{"name": "...", "entity_type": "protein", '
        '"identifier": "optional document-stated ID"}]}'
    )


def _user_message(document_context: str) -> str:
    return (
        "Relevant uploaded-document blocks:\n"
        f"{limit_document_context(document_context)}\n\n"
        "Bind the unit to its document target now."
    )


def _parse(raw: str) -> dict | None:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_object(text))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_fences(value: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", value, re.DOTALL)
    return match.group(1) if match else value


def _extract_json_object(value: str) -> str:
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return value[index : index + end]
    raise ValueError("no JSON object")
