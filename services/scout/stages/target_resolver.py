"""Bind a canonical investigation-unit definition to its document target.

Dynamic providers already extract the target and its exact blocks. Fixed
providers supply only a stable definition, so this stage locates the matching
document statement. Both paths leave this stage with the same resolved
``Attribute`` contract.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from ..ai import request_structured
from ..ai_contracts import TARGET_BINDING
from ..context import (
    BLOCK_ID_JSON_INSTRUCTION,
    document_block_ids,
    limit_document_context,
    validated_block_ids,
)
from ..models import (
    ENTITY_TYPES,
    Attribute,
    EvidenceEntity,
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
    parsed = request_structured(
        llm_client,
        TARGET_BINDING,
        _system_prompt(attribute),
        _user_message(document_context),
        max_tokens=max_tokens,
        images=images,
    )
    binding = _validated_binding(parsed, allowed_ids)
    if binding is None:
        logger.warning(
            "target_resolver produced no valid cited binding for %s; retrying once",
            attribute.name,
        )
        parsed = request_structured(
            llm_client,
            TARGET_BINDING,
            _system_prompt(attribute),
            _user_message(document_context),
            max_tokens=max_tokens,
            images=images,
        )
        binding = _validated_binding(parsed, allowed_ids)

    if binding is None:
        # Never propagate a model-authored target without exact block lineage.
        # An unresolved binding is represented as a safe absent target;
        # downstream stages can still provide field-level coverage without
        # treating unsupported synthesis as document fact.
        return replace(
            attribute,
            document_target="",
            block_ids=[],
            entities=[],
            target_resolved=True,
        )
    target, block_ids, entities = binding
    return replace(
        attribute,
        document_target=target,
        block_ids=block_ids,
        entities=entities,
        target_resolved=True,
    )


def _validated_binding(
    parsed: object,
    allowed_ids: set[str],
) -> tuple[str, list[str], list[EvidenceEntity]] | None:
    """Parse one binding and reject a non-empty target without exact lineage."""
    if not isinstance(parsed, dict):
        return None
    target = str(parsed.get("document_target", "")).strip()
    if not target:
        return "", [], []
    block_ids = validated_block_ids(parsed.get("block_ids"), allowed_ids)
    if not block_ids:
        return None
    return target, block_ids, parse_evidence_entities(parsed.get("entities"))


def _system_prompt(attribute: Attribute) -> str:
    return (
        "You bind ONE fixed evaluation definition to the uploaded document.\n\n"
        f"Unit: {attribute.name}\n"
        f"Definition: {attribute.description}\n\n"
        "Locate only the document's concrete target, constraint, assumption, or "
        "commitment for this unit. Preserve numbers, dates, comparators, and "
        "qualifiers. Do not add external evidence or infer a target the document "
        "does not state. The binding must be DIRECTLY about this unit: do not reuse a "
        "nearby target for a neighboring variable, and do not treat a possible downstream "
        "implication as the document's target for this unit. If the document has only a "
        "related target for another unit, return no target. Extract only explicitly named "
        "entities whose type is one of: "
        f"{', '.join(sorted(ENTITY_TYPES - {'other'}))}. Include an "
        "identifier only when the document states it. Return the blocks supporting "
        "the target. "
        f"{BLOCK_ID_JSON_INSTRUCTION} If "
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
