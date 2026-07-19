"""Read-only navigation over parsed source-document blocks for Ask.

The result tree and source document stay separate. Ask receives a compact
document map up front, then searches and reads exact blocks on demand. This
keeps long uploads fully reachable without silently truncating them or placing
their entire text in every model call.
"""

from __future__ import annotations

import json
from typing import Any

MAX_FIND_HITS = 40
MAX_BLOCK_CHARS = 60_000
MAX_TOOL_CHARS = 120_000
MAX_RANGE_BLOCKS = 25


def overview(blocks: list[dict[str, Any]]) -> str:
    """Return document names, block ranges, and a compact heading map."""
    by_document: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        by_document.setdefault(str(block.get("doc_id") or "document"), []).append(block)

    lines = [f"{len(blocks)} parsed blocks across {len(by_document)} document(s)."]
    for doc_id, document_blocks in by_document.items():
        ids = [str(block.get("id") or "") for block in document_blocks if block.get("id")]
        headings = list(
            dict.fromkeys(
                " > ".join(block.get("heading_stack") or [])
                for block in document_blocks
                if block.get("heading_stack")
            )
        )
        block_range = f"{ids[0]} … {ids[-1]}" if ids else "no block ids"
        visual_count = sum(1 for block in document_blocks if block.get("image"))
        visual_suffix = f", {visual_count} visual(s)" if visual_count else ""
        lines.append(
            f"- {doc_id}: {len(document_blocks)} blocks{visual_suffix} ({block_range})"
        )
        if headings:
            shown = headings[:20]
            suffix = f" … +{len(headings) - len(shown)} more" if len(headings) > len(shown) else ""
            lines.append(f"  headings: {' | '.join(shown)}{suffix}")
    return "\n".join(lines)


def find(blocks: list[dict[str, Any]], keyword: str) -> str:
    """Locate document blocks by keyword and return IDs with local snippets."""
    needle = keyword.strip().lower()
    if not needle:
        return "(empty keyword)"
    hits: list[dict[str, str]] = []
    for block in blocks:
        content = str(block.get("content") or "")
        heading = " > ".join(block.get("heading_stack") or [])
        haystack = f"{heading}\n{content}".lower()
        index = haystack.find(needle)
        if index < 0:
            continue
        start = max(0, index - 140)
        end = min(len(haystack), index + len(needle) + 220)
        # Slice the original combined text so the returned snippet preserves case.
        original = f"{heading}\n{content}"
        hits.append(
            {
                "id": str(block.get("id") or ""),
                "heading": heading,
                "snippet": " ".join(original[start:end].split()),
            }
        )
        if len(hits) >= MAX_FIND_HITS:
            break
    return json.dumps(hits, indent=2, ensure_ascii=False) if hits else "(no matches)"


def get(
    blocks: list[dict[str, Any]],
    block_ids: list[str],
    *,
    start_char: int = 0,
) -> str:
    """Read exact blocks. Large individual blocks can be paged with start_char."""
    requested = list(dict.fromkeys(str(block_id) for block_id in block_ids if block_id))
    if not requested:
        return "(no block ids supplied)"
    by_id = {str(block.get("id") or ""): block for block in blocks if block.get("id")}
    start_char = max(0, start_char)
    output: list[str] = []
    used = 0
    for block_id in requested:
        block = by_id.get(block_id)
        if block is None:
            output.append(f"[{block_id}] (block not found)")
            continue
        content = str(block.get("content") or "")
        chunk = content[start_char : start_char + MAX_BLOCK_CHARS]
        next_start = start_char + len(chunk)
        heading = " > ".join(block.get("heading_stack") or [])
        header = f"[{block_id}]" + (f" heading={heading}" if heading else "")
        rendered = f"{header}\n{chunk}"
        if next_start < len(content):
            rendered += f"\n...[block continues; call again with start_char={next_start}]"
        if output and used + len(rendered) > MAX_TOOL_CHARS:
            output.append("...[tool output budget reached; request remaining block ids separately]")
            break
        output.append(rendered)
        used += len(rendered)
    return "\n\n".join(output)


def get_range(
    blocks: list[dict[str, Any]],
    doc_id: str,
    *,
    start: int = 0,
    count: int = MAX_RANGE_BLOCKS,
) -> str:
    """Read an ordered document slice for broad review and summarization."""
    document_blocks = [
        block for block in blocks if str(block.get("doc_id") or "document") == doc_id
    ]
    if not document_blocks:
        return f"(document not found: {doc_id})"
    start = max(0, start)
    count = max(1, min(count, MAX_RANGE_BLOCKS))
    selected = document_blocks[start : start + count]
    block_ids = [str(block.get("id") or "") for block in selected if block.get("id")]
    rendered = get(blocks, block_ids)
    next_start = start + len(selected)
    if next_start < len(document_blocks):
        rendered += f"\n\n...[document continues; call again with start={next_start}]"
    return rendered
