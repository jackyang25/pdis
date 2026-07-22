from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

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
    batches = _batch_blocks(
        blocks,
        max_characters=config.extraction_batch_characters,
        max_blocks=config.extraction_batch_blocks,
    )
    worker_budget = max_workers or config.max_parallel_calls
    workers = max(1, min(worker_budget, len(batches)))

    def run(batch: list[ContentBlock]) -> list[dict[str, Any]]:
        return _extract_batch(
            batch,
            source_type=source_type,
            document_role=document_role,
            config=config,
            llm_client=llm_client,
            max_tokens=max_tokens,
        )

    if len(batches) == 1:
        raw_units = run(batches[0])
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            raw_units = [item for group in executor.map(run, batches) for item in group]

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
        unit_id = _stable_id(doc_id, str(unit_type), statement, block_ids)
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

Return ONLY valid JSON in this shape:
{{"units":[{{"statement":"...","unit_type":"target|activity|milestone|requirement|dependency|risk_response","block_ids":["exact-id"]}}]}}
"""
    user_message = "Document blocks:\n\n" + _format_blocks(blocks)
    images = _image_inputs(blocks)
    for attempt in range(2):
        raw = llm_client.call(
            system_prompt,
            user_message
            + (
                "\n\nThe previous response was invalid. Return only the requested JSON object."
                if attempt
                else ""
            ),
            max_tokens=max_tokens,
            images=images or None,
        )
        try:
            parsed = json.loads(_extract_json_object(raw))
            units = parsed.get("units")
            if not isinstance(units, list):
                raise ValueError("units must be a list")
            return [item for item in units if isinstance(item, dict)]
        except (ValueError, json.JSONDecodeError, AttributeError) as exc:
            if attempt:
                logger.error("Aligner unit extraction returned invalid JSON after retry: %s", exc)
    return []


def _batch_blocks(
    blocks: list[ContentBlock], *, max_characters: int, max_blocks: int
) -> list[list[ContentBlock]]:
    batches: list[list[ContentBlock]] = []
    current: list[ContentBlock] = []
    current_characters = 0
    for block in blocks:
        size = len(block.content or "") + len(block.id) + 80
        if current and (
            len(current) >= max_blocks or current_characters + size > max_characters
        ):
            batches.append(current)
            current = []
            current_characters = 0
        current.append(block)
        current_characters += size
    if current:
        batches.append(current)
    return batches


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


def _extract_json_object(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response did not contain a JSON object")
    return text[start : end + 1]


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


def _stable_id(doc_id: str, unit_type: str, statement: str, block_ids: list[str]) -> str:
    payload = "\0".join([doc_id, unit_type, _normalize(statement), *sorted(block_ids)])
    return f"unit_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
