"""Stateless chunker pipeline.

Wires the two stages — parse (deterministic, format-specific) and an
optional LLM mapper — into a single function. No persistence; the caller
decides what to do with the output.

Library consumers should call `run_pipeline` rather than invoking
`parse_document` and `label_blocks` separately. The interface and CLI
both go through this function so orchestration lives in exactly one
place.
"""

from __future__ import annotations

from .llm_client import DEFAULT_MAX_OUTPUT_TOKENS, LLMClient
from .models import ContentBlock, DocumentTypeConfig
from .stages.mapper import label_blocks
from .stages.parser import parse_document


def run_pipeline(
    file_path: str,
    doc_id: str,
    *,
    config: DocumentTypeConfig | None = None,
    llm_client: LLMClient | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> list[ContentBlock]:
    """
    Parse a document, then optionally run the mapper to assign section labels.

    Args:
        file_path: Path to a .docx or .pdf file.
        doc_id: Identifier for this document (used in block IDs).
        config: DocumentTypeConfig for the mapper. If None (or llm_client is None),
            the mapper is skipped and `section_label` / `label_confidence` stay None.
        llm_client: LLM client for the mapper. If None, the mapper is skipped.
        max_tokens: Token budget for the mapper response.

    Returns:
        list[ContentBlock] in document order. Each block has
        `section_label` and `label_confidence` populated when the mapper ran;
        otherwise both are None.
    """
    blocks = parse_document(file_path, doc_id)
    if config is not None and llm_client is not None:
        blocks = label_blocks(blocks, config, llm_client, max_tokens=max_tokens)
    return blocks
