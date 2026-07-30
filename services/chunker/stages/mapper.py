from __future__ import annotations

import logging

from shared.ai import request_structured

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
        llm_client: Object implementing the schema-bound ``call_structured`` contract.
        max_tokens: Maximum tokens allowed in each mapper response

    Returns:
        Same blocks with section_label filled in
    """
    _clear_labels(blocks)
    if len(blocks) >= 200:
        logger.warning("Labeling %s blocks at once may degrade results", len(blocks))

    system_prompt, user_message = build_prompts(blocks, config)
    images = [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]
    schema = _label_schema(blocks, config)
    last_error = "model returned no structured labels"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior response failed the mapping contract: "
                f"{last_error}. Return exactly one label for every supplied block ID."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            schema_name="chunker_section_labels",
            schema=schema,
            max_tokens=max_tokens,
            images=images or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured labels")
            labels = _parse_label_payload(payload)
            return _merge_labels(blocks, labels, config)
        except ValueError as exc:
            last_error = str(exc)
    raise MapperResponseError(f"Mapper response was invalid after retry: {last_error}")


def _label_schema(
    blocks: list[ContentBlock],
    config: DocumentTypeConfig,
) -> dict[str, object]:
    count = len(blocks)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["labels"],
        "properties": {
            "labels": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "section_label", "confidence"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "enum": [block.id for block in blocks],
                        },
                        "section_label": {
                            "type": "string",
                            "enum": [section["name"] for section in _final_taxonomy(config)],
                        },
                        "confidence": {
                            "type": "string",
                            "enum": sorted(VALID_CONFIDENCES),
                        },
                    },
                },
            }
        },
    }


def _parse_label_payload(payload: object) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("labels"), list):
        raise ValueError("Mapper response must contain a labels list")
    labels: list[dict[str, str]] = []
    for item in payload["labels"]:
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
                    "the document itself, not its substantive content."
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
    return """Return one structured labels list with id, section_label, and confidence.
Every block id from the input must appear exactly once.
Every section_label must be an exact label from the taxonomy above.
Confidence must be one of: "high", "medium", "low"."""


def _format_block(block: ContentBlock) -> str:
    header_parts = [block.id, block.block_type]

    if block.block_type == "heading":
        heading_level = block.structural_meta.get("heading_level")
        header_parts.append(f"level: {heading_level}")
    else:
        header_parts.append(f"headings: {_format_heading_stack(block.heading_stack)}")

    if block.block_type == "table_row":
        column_headers = block.structural_meta.get("column_headers", [])
        if column_headers:
            header_parts.append(f"cols: {', '.join(column_headers)}")

    return f"[{' | '.join(header_parts)}]\n<content>{block.content}</content>"


def _format_heading_stack(heading_stack: list[str]) -> str:
    if not heading_stack:
        return "none"
    return " > ".join(f'"{heading}"' for heading in heading_stack)


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
        seen_ids.add(block_id)
        labels_by_id[block_id] = label

    missing_ids = block_ids - labels_by_id.keys()
    if missing_ids:
        raise ValueError(f"Mapper response omitted {len(missing_ids)} block IDs")

    extra_ids = labels_by_id.keys() - block_ids
    if extra_ids:
        raise ValueError(f"Mapper response included {len(extra_ids)} unknown block IDs")

    if len(seen_ids) != len(labels):
        raise ValueError("Mapper response contains duplicate block IDs")

    for block in blocks:
        label = labels_by_id.get(block.id)
        if label is None:
            raise ValueError(f"Mapper response omitted block ID {block.id}")

        section_label = label["section_label"]
        confidence = label["confidence"]
        if section_label not in valid_section_labels:
            raise ValueError(f"Invalid section label for {block.id}: {section_label}")
        if confidence not in VALID_CONFIDENCES:
            raise ValueError(f"Invalid confidence for {block.id}: {confidence}")

        block.section_label = section_label

    return blocks


def _clear_labels(blocks: list[ContentBlock]) -> None:
    for block in blocks:
        block.section_label = None
