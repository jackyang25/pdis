from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Literal

from shared.batching import budgeted_batches, map_ordered

from services.chunker import ContentBlock

from ..models import AlignmentConfig, AlignmentUnit, LLMClientProtocol

logger = logging.getLogger(__name__)


def extract_units(
    blocks: list[ContentBlock],
    *,
    document_role: Literal["reference", "comparison"],
    source_type: str,
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int,
    max_workers: int | None = None,
) -> list[AlignmentUnit]:
    if not blocks:
        return []
    batches = budgeted_batches(
        blocks,
        max_items=config.extraction_batch_blocks,
        max_chars=config.extraction_batch_characters,
        size_of=_rendered_size,
    )
    worker_budget = max_workers or config.max_parallel_calls

    def run(batch: list[ContentBlock]) -> list[dict[str, Any]]:
        return _extract_batch(
            batch,
            source_type=source_type,
            document_role=document_role,
            config=config,
            llm_client=llm_client,
            max_tokens=max_tokens,
        )

    raw_units = [
        item
        for group in map_ordered(batches, run, workers=worker_budget)
        for item in group
    ]

    doc_id = blocks[0].doc_id
    allowed_ids = {block.id for block in blocks}
    allowed_types = {item.name for item in config.unit_types}
    merged: dict[tuple[str, str], AlignmentUnit] = {}
    for item in raw_units:
        statement = _clean_text(item.get("statement"))
        unit_type = item.get("unit_type")
        block_ids = _valid_string_list(item.get("block_ids"), allowed_ids)
        if not statement or unit_type not in allowed_types or not block_ids:
            continue
        key = (str(unit_type), _normalize(statement))
        existing = merged.get(key)
        if existing:
            existing.block_ids = _unique([*existing.block_ids, *block_ids])
            continue
        unit_id = _stable_id(doc_id, str(unit_type), statement)
        merged[key] = AlignmentUnit(
            id=unit_id,
            document_role=document_role,
            document_id=doc_id,
            unit_type=unit_type,  # type: ignore[arg-type]
            statement=statement,
            block_ids=block_ids,
        )
    return list(merged.values())


def _extract_batch(
    blocks: list[ContentBlock],
    *,
    source_type: str,
    document_role: str,
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> list[dict[str, Any]]:
    labels = "\n".join(
        f'- "{item.name}": {item.description}' for item in config.unit_types
    )
    role_description = config.document_roles.get(
        source_type, config.document_roles.get("default", "Product-development document.")
    )
    system_prompt = f"""You extract traceable units from one product-development document.

Document role: {document_role}
Document type: {source_type} — {role_description}

Extract only explicit, checkable content that another development artifact could preserve, change, conflict with, omit, or introduce. Do not infer unstated commitments. Exclude generic background, instructions, headers, and purely descriptive prose unless it states a target, activity, milestone, requirement, dependency, or risk response.

Choose exactly one unit_type from this closed vocabulary:
{labels}

Every unit must cite one or more exact block IDs supplied below. Never invent an ID. Keep statements faithful and independently understandable. Split compound statements only when their parts could change independently.

Return only the schema-bound response.
"""
    user_message = "Document blocks:\n\n" + _format_blocks(blocks)
    images = _image_inputs(blocks)
    allowed_ids = {block.id for block in blocks}
    allowed_types = {item.name for item in config.unit_types}
    schema = _unit_schema(sorted(allowed_ids), sorted(allowed_types))
    for attempt in range(2):
        parsed = llm_client.call_structured(
            system_prompt,
            user_message
            + (
                "\n\nThe previous response failed the unit contract. Return one "
                "complete, schema-bound response."
                if attempt
                else ""
            ),
            max_tokens,
            schema_name="aligner_document_units",
            schema=schema,
            images=images or None,
        )
        try:
            if not isinstance(parsed, dict):
                raise ValueError("model returned no structured units")
            units = parsed.get("units")
            if not isinstance(units, list):
                raise ValueError("units must be a list")
            cleaned: list[dict[str, Any]] = []
            for item in units:
                if not isinstance(item, dict):
                    raise ValueError("Every extracted unit must be an object")
                statement = _clean_text(item.get("statement"))
                unit_type = item.get("unit_type")
                raw_block_ids = item.get("block_ids")
                if not isinstance(raw_block_ids, list) or any(
                    not isinstance(block_id, str) or block_id not in allowed_ids
                    for block_id in raw_block_ids
                ):
                    raise ValueError("Extracted unit cited an unknown block ID")
                block_ids = list(dict.fromkeys(raw_block_ids))
                if not statement or unit_type not in allowed_types or not block_ids:
                    raise ValueError("Extracted unit violated the closed unit contract")
                cleaned.append(
                    {
                        "statement": statement,
                        "unit_type": unit_type,
                        "block_ids": block_ids,
                    }
                )
            return cleaned
        except (ValueError, AttributeError) as exc:
            if attempt:
                logger.error("Aligner unit extraction failed its contract after retry: %s", exc)
    raise RuntimeError(
        f"Aligner unit extraction failed for the {document_role} document"
    )


def _unit_schema(
    allowed_block_ids: list[str],
    allowed_unit_types: list[str],
) -> dict[str, Any]:
    """Close the extraction contract in the schema instead of in prose checks."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["units"],
        "properties": {
            "units": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["statement", "unit_type", "block_ids"],
                    "properties": {
                        "statement": {"type": "string"},
                        "unit_type": {"type": "string", "enum": allowed_unit_types},
                        "block_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": allowed_block_ids},
                        },
                    },
                },
            }
        },
    }


def _rendered_size(block: ContentBlock) -> int:
    """Approximate the characters one block contributes to a request."""
    return len(block.content or "") + len(block.id) + 80


def _format_blocks(blocks: list[ContentBlock]) -> str:
    parts: list[str] = []
    for block in blocks:
        context = " > ".join(block.heading_stack)
        label = block.section_label or ""
        metadata = " | ".join(value for value in (context, label) if value)
        content = block.content.strip() if block.content else "[visual block]"
        parts.append(f"[{block.id}] ({block.block_type}{'; ' + metadata if metadata else ''})\n{content}")
    return "\n\n".join(parts)


def _image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image is not None
    ]


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _valid_string_list(value: Any, allowed: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique([item for item in value if isinstance(item, str) and item in allowed])


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _stable_id(doc_id: str, unit_type: str, statement: str) -> str:
    # Provenance may expand when the same statement appears in another batch;
    # semantic identity must not change when that lineage is merged.
    payload = "\0".join([doc_id, unit_type, _normalize(statement)])
    return f"unit_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
