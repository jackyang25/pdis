from __future__ import annotations

import json
import logging
import re
from typing import Any

try:
    from .models import ContentBlock, DocumentTypeConfig
except ImportError:  # pragma: no cover - supports running files directly
    from models import ContentBlock, DocumentTypeConfig


logger = logging.getLogger(__name__)

VALID_CONFIDENCES = {"high", "medium", "low"}
MODEL_NAME = "claude-opus-4-7"


def label_blocks(
    blocks: list[ContentBlock],
    config: DocumentTypeConfig,
    api_key: str,
) -> list[ContentBlock]:
    """
    Phase 2: LLM-driven section labeling.

    Args:
        blocks: List of ContentBlock objects from the parser
        config: Document-type config with taxonomy and rules
        api_key: Anthropic API key

    Returns:
        Same blocks with section_label and label_confidence filled in
    """
    if not api_key:
        raise ValueError("api_key is required")
    if len(blocks) >= 200:
        logger.warning("Labeling %s blocks at once may degrade results", len(blocks))

    system_prompt, user_message = build_prompts(blocks, config)
    raw_response = _call_anthropic(api_key, system_prompt, user_message)

    try:
        labels = _parse_label_response(raw_response)
    except ValueError:
        logger.warning("Mapper response was not valid JSON; retrying once")
        raw_response = _call_anthropic(api_key, system_prompt, user_message)
        try:
            labels = _parse_label_response(raw_response)
        except ValueError:
            logger.warning("Mapper response was still invalid after retry")
            return _label_unknown(blocks)

    return _merge_labels(blocks, labels, config)


def build_prompts(
    blocks: list[ContentBlock],
    config: DocumentTypeConfig,
) -> tuple[str, str]:
    """Build the system prompt and user message for section labeling."""
    system_prompt = "\n\n".join(
        [
            _base_system_prompt(),
            config.preamble.strip(),
            _format_taxonomy(config.section_taxonomy),
            _format_disambiguation(config.disambiguation),
            _output_format_prompt(config.allow_other),
        ]
    )
    user_message = "\n\n".join(_format_block(block) for block in blocks)
    return system_prompt, user_message


def _base_system_prompt() -> str:
    return """You are labeling document blocks with normalized section names.

You will receive an ordered list of blocks extracted from a document.
For each block, return its id and the section_label it belongs to.

Rules:
- Every block must receive exactly one section_label.
- Group adjacent blocks under the same label when they share a topic,
  even if a heading boundary falls between them.
- Prefer semantic fit over literal heading text. A paragraph discussing
  target population details under a heading called "Executive Summary"
  should still be labeled "Executive Summary (Core Variables)" if it
  appears within that table section.
- Use the heading_stack as a strong signal but not the final word.
- Do not invent section labels outside the provided taxonomy unless
  you use the "Other: [description]" escape (only if allow_other is true)."""


def _format_taxonomy(section_taxonomy: list[str]) -> str:
    lines = ["Section taxonomy (in expected document order):"]
    lines.extend(
        f"{index}. {section_label}"
        for index, section_label in enumerate(section_taxonomy, start=1)
    )
    return "\n".join(lines)


def _format_disambiguation(disambiguation: list[str]) -> str:
    lines = ["Disambiguation rules:"]
    lines.extend(f"- {rule.strip()}" for rule in disambiguation)
    return "\n".join(lines)


def _output_format_prompt(allow_other: bool) -> str:
    other_rule = (
        'or "Other: [description]" if allowed'
        if allow_other
        else "and Other labels are not allowed"
    )
    return f"""Return ONLY valid JSON. No markdown fences, no preamble, no explanation.
Format:
[
  {{"id": "doc-001/b-0000", "section_label": "Introduction", "confidence": "high"}},
  {{"id": "doc-001/b-0001", "section_label": "Introduction", "confidence": "high"}}
]

Every block id from the input must appear exactly once in the output.
Every section_label must be from the taxonomy above ({other_rule}).
Confidence must be one of: "high", "medium", "low"."""


def _format_block(block: ContentBlock) -> str:
    header_parts = [block.id, block.source_type]

    if block.source_type == "heading":
        heading_level = block.structural_meta.get("heading_level")
        header_parts.append(f"level: {heading_level}")
    else:
        header_parts.append(f"headings: {_format_heading_stack(block.heading_stack)}")

    if block.source_type == "table_row":
        column_headers = block.structural_meta.get("column_headers", [])
        if column_headers:
            header_parts.append(f"cols: {', '.join(column_headers)}")

    return f"[{' | '.join(header_parts)}]\n<content>{block.content}</content>"


def _format_heading_stack(heading_stack: list[str]) -> str:
    if not heading_stack:
        return "none"
    return " > ".join(f'"{heading}"' for heading in heading_stack)


def _call_anthropic(api_key: str, system_prompt: str, user_message: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return _message_text(message)


def _message_text(message: Any) -> str:
    parts = []
    for block in getattr(message, "content", []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _parse_label_response(raw_response: str) -> list[dict[str, str]]:
    response_text = _strip_markdown_fences(raw_response).strip()
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Mapper response was not valid JSON") from exc

    if not isinstance(parsed, list):
        raise ValueError("Mapper response must be a list")

    labels: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Mapper response items must be objects")
        labels.append(
            {
                "id": str(item.get("id", "")),
                "section_label": str(item.get("section_label", "")),
                "confidence": str(item.get("confidence", "")),
            }
        )
    return labels


def _strip_markdown_fences(raw_response: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", raw_response, re.DOTALL)
    if match:
        return match.group(1)
    return raw_response


def _merge_labels(
    blocks: list[ContentBlock],
    labels: list[dict[str, str]],
    config: DocumentTypeConfig,
) -> list[ContentBlock]:
    block_ids = {block.id for block in blocks}
    labels_by_id: dict[str, dict[str, str]] = {}
    seen_ids: set[str] = set()

    for label in labels:
        block_id = label["id"]
        if block_id in seen_ids:
            logger.warning("Duplicate label returned for block id %s", block_id)
        seen_ids.add(block_id)
        labels_by_id[block_id] = label

    missing_ids = block_ids - labels_by_id.keys()
    if missing_ids:
        logger.warning("Mapper response missing %s block ids", len(missing_ids))

    extra_ids = labels_by_id.keys() - block_ids
    if extra_ids:
        logger.warning("Mapper response included %s unknown block ids", len(extra_ids))

    for block in blocks:
        label = labels_by_id.get(block.id)
        if label is None:
            block.section_label = "Unknown"
            block.label_confidence = "low"
            continue

        section_label = label["section_label"]
        confidence = label["confidence"]
        if not _is_valid_section_label(section_label, config):
            logger.warning("Invalid section label for %s: %s", block.id, section_label)
        if confidence not in VALID_CONFIDENCES:
            logger.warning("Invalid confidence for %s: %s", block.id, confidence)
            confidence = "low"

        block.section_label = section_label
        block.label_confidence = confidence

    return blocks


def _label_unknown(blocks: list[ContentBlock]) -> list[ContentBlock]:
    for block in blocks:
        block.section_label = "Unknown"
        block.label_confidence = "low"
    return blocks


def _is_valid_section_label(
    section_label: str,
    config: DocumentTypeConfig,
) -> bool:
    if section_label in config.section_taxonomy:
        return True
    return config.allow_other and section_label.startswith("Other: ")
