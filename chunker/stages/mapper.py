from __future__ import annotations

import json
import logging
import re

from ..models import ContentBlock, DocumentTypeConfig, LLMClientProtocol


logger = logging.getLogger(__name__)

VALID_CONFIDENCES = {"high", "medium", "low"}


class MapperResponseError(ValueError):
    """Raised when the mapper cannot produce a usable label response."""


def label_blocks(
    blocks: list[ContentBlock],
    config: DocumentTypeConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> list[ContentBlock]:
    """
    Phase 2 section labeling using an injected LLM client.

    Args:
        blocks: List of ContentBlock objects from the parser
        config: Document-type config with taxonomy and rules
        llm_client: Object with a call(system_prompt, user_message, max_tokens) method
        max_tokens: Maximum tokens allowed in each mapper response

    Returns:
        Same blocks with section_label and label_confidence filled in
    """
    _clear_labels(blocks)
    if len(blocks) >= 200:
        logger.warning("Labeling %s blocks at once may degrade results", len(blocks))

    system_prompt, user_message = build_prompts(blocks, config)
    raw_response = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)

    try:
        labels = _parse_label_response(raw_response)
    except ValueError:
        logger.warning("Mapper response was not valid JSON; retrying once")
        raw_response = llm_client.call(
            system_prompt,
            user_message,
            max_tokens=max_tokens,
        )
        try:
            labels = _parse_label_response(raw_response)
        except ValueError:
            logger.warning("Mapper response was still invalid after retry")
            raise MapperResponseError("Mapper response was invalid after retry")

    return _merge_labels(blocks, labels, config)


def build_prompts(
    blocks: list[ContentBlock],
    config: DocumentTypeConfig,
) -> tuple[str, str]:
    """Build the system prompt and user message for section labeling."""
    final_taxonomy = _final_taxonomy(config)
    disambiguation = _final_disambiguation(config)
    system_prompt = "\n\n".join(
        [
            _base_system_prompt(),
            config.preamble.strip(),
            _format_taxonomy(final_taxonomy),
            _format_disambiguation(disambiguation),
            _output_format_prompt(),
        ]
    )
    user_message = "\n\n".join(_format_block(block) for block in blocks)
    return system_prompt, user_message


def _final_taxonomy(config: DocumentTypeConfig) -> list[dict[str, str]]:
    taxonomy = list(config.section_taxonomy)
    if config.include_metadata_label:
        taxonomy.append(
            {
                "name": "Document Metadata",
                "description": (
                    "Page numbers, version stamps, headers, footers, template "
                    "metadata, and other formatting artifacts that are about "
                    "the document itself, not the TPP content."
                ),
            }
        )
    if config.include_other_label:
        taxonomy.append(
            {
                "name": "Other",
                "description": (
                    "Real content that does not fit any taxonomy section above. "
                    "Use sparingly; prefer a taxonomy section when there's a "
                    "reasonable fit."
                ),
            }
        )
    return taxonomy


def _final_disambiguation(config: DocumentTypeConfig) -> list[str]:
    disambiguation = list(config.disambiguation)
    if config.include_metadata_label:
        disambiguation.append(
            "Blocks containing page numbers, version stamps, template metadata, "
            "headers, footers, or formatting artifacts should be labeled "
            "'Document Metadata', not forced into a content section."
        )
    if config.include_other_label:
        disambiguation.append(
            "If a block is real content but does not fit any taxonomy section, "
            "label it 'Other'. Do not force-fit content into the wrong section."
        )
    return disambiguation


def _base_system_prompt() -> str:
    return """You are labeling document blocks with normalized section names.

You will receive an ordered list of blocks extracted from a document.
For each block, return its id and the section_label it belongs to.

Rules:
- Every block must receive exactly one section_label.
- This is a classification task only. Do not provide medical advice,
  clinical recommendations, safety assessment, or interpretation.
- Do not evaluate, endorse, transform, or generate medical claims.
  Only assign section labels to already-written source text.
- Group adjacent blocks under the same label when they share a topic,
  even if a heading boundary falls between them.
- Prefer semantic fit over literal heading text. A paragraph discussing
  target population details under a heading called "Executive Summary"
  should still be labeled "Executive Summary (Core Variables)" if it
  appears within that table section.
- Use the heading_stack as a strong signal but not the final word.
- Heading blocks should be labeled with the section they introduce,
  not treated as a separate category.
- Do not invent section labels outside the provided taxonomy."""


def _format_taxonomy(section_taxonomy: list[dict[str, str]]) -> str:
    lines = ["Section taxonomy:"]
    lines.extend(
        f'- "{section["name"]}" - {section["description"]}'
        for section in section_taxonomy
    )
    return "\n".join(lines)


def _format_disambiguation(disambiguation: list[str]) -> str:
    lines = ["Disambiguation rules:"]
    lines.extend(f"- {rule.strip()}" for rule in disambiguation)
    return "\n".join(lines)


def _output_format_prompt() -> str:
    return """Return ONLY valid JSON. No markdown fences, no preamble, no explanation.
Format:
[
  {"id": "doc-001/b-0000", "section_label": "Introduction", "confidence": "high"},
  {"id": "doc-001/b-0001", "section_label": "Introduction", "confidence": "high"}
]

Every block id from the input must appear exactly once in the output.
Every section_label must be an exact label from the taxonomy above.
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


def _parse_label_response(raw_response: str) -> list[dict[str, str]]:
    response_text = _extract_json_array(_strip_markdown_fences(raw_response).strip())
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid mapper response preview: %s", _response_preview(raw_response))
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


def _extract_json_array(response_text: str) -> str:
    decoder = json.JSONDecoder()
    for start_index, char in enumerate(response_text):
        if char != "[":
            continue
        try:
            parsed, end_index = decoder.raw_decode(response_text[start_index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return response_text[start_index : start_index + end_index]
    return response_text


def _response_preview(raw_response: str, max_length: int = 500) -> str:
    compact_response = " ".join(raw_response.split())
    if len(compact_response) <= max_length:
        return compact_response
    return f"{compact_response[:max_length]}..."


def _merge_labels(
    blocks: list[ContentBlock],
    labels: list[dict[str, str]],
    config: DocumentTypeConfig,
) -> list[ContentBlock]:
    block_ids = {block.id for block in blocks}
    valid_section_labels = {section["name"] for section in _final_taxonomy(config)}
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
        logger.warning(
            "Mapper response included %s unexpected block ids",
            len(extra_ids),
        )

    for block in blocks:
        label = labels_by_id.get(block.id)
        if label is None:
            _set_block_mapping_error(block)
            continue

        section_label = label["section_label"]
        confidence = label["confidence"]
        if section_label not in valid_section_labels:
            logger.warning("Invalid section label for %s: %s", block.id, section_label)
            _set_block_mapping_error(block)
            continue
        if confidence not in VALID_CONFIDENCES:
            logger.warning("Invalid confidence for %s: %s", block.id, confidence)
            _set_block_mapping_error(block)
            continue

        block.section_label = section_label
        block.label_confidence = confidence

    return blocks


def _clear_labels(blocks: list[ContentBlock]) -> None:
    for block in blocks:
        block.section_label = None
        block.label_confidence = None


def _set_block_mapping_error(block: ContentBlock) -> None:
    block.section_label = "Mapping Error"
    block.label_confidence = "low"
