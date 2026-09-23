"""Original source material shared by Screener's selection and assessment stages."""
from __future__ import annotations

from services.chunker import ContentBlock
from shared.document_metadata import extraction_context
from shared.vocabulary import search_term

_GROUP_KEYS = ("page", "slide", "table_index")


def review_context(indication: str, intervention_class: str) -> str:
    return (
        "Selected review context (user-supplied, not evidence):\n"
        f"Disease / condition: {search_term(indication)}\n"
        f"Intervention class: {search_term(intervention_class)}"
    )


def format_blocks(blocks: list[ContentBlock]) -> str:
    return "\n\n".join(_format_block(block) for block in blocks) or "(none)"


def _format_block(block: ContentBlock) -> str:
    headings = " > ".join(block.heading_stack) if block.heading_stack else "none"
    metadata = [f"{key}: {value}" for _, key, value in _groups(block)]
    extraction = extraction_context(block.structural_meta)
    if extraction:
        metadata.append(extraction)
    suffix = " | " + " | ".join(metadata) if metadata else ""
    return (
        f"[{block.id} | {block.doc_id} | {block.block_type} | "
        f"headings: {headings}{suffix}]\n{block.content}"
    )


def image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks if block.image
    ]


def _groups(block: ContentBlock) -> list[tuple[str, str, int | str]]:
    # Only parser-authored structural identities create a relationship. Zero is
    # a valid table index; missing metadata must never join unrelated blocks.
    table_group = block.structural_meta.get("table_group")
    has_table_group = isinstance(table_group, str) and bool(table_group)
    groups = [(block.doc_id, key, value) for key in _GROUP_KEYS
              if not (key == "table_index" and has_table_group)
              and type(value := block.structural_meta.get(key)) is int]
    if has_table_group:
        groups.append((block.doc_id, "table_group", table_group))
    return groups


def expand_selection(
    blocks: list[ContentBlock], selected_ids: list[str],
) -> list[ContentBlock]:
    """Keep complete explicit tables/pages/slides, in original source order."""
    by_id = {block.id: block for block in blocks}
    unknown = set(selected_ids) - by_id.keys()
    if unknown:
        raise ValueError(f"Selected blocks not supplied: {sorted(unknown)}")
    members: dict[tuple[str, str, int | str], list[str]] = {}
    for block in blocks:
        for group in _groups(block):
            members.setdefault(group, []).append(block.id)
    selected = set(selected_ids)
    pending = list(selected)
    visited_groups = set()
    while pending:
        for group in _groups(by_id[pending.pop()]):
            if group in visited_groups:
                continue
            visited_groups.add(group)
            for identifier in members[group]:
                if identifier not in selected:
                    selected.add(identifier)
                    pending.append(identifier)
    return [block for block in blocks if block.id in selected]
