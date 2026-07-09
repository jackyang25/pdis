"""Renders the source document (parsed blocks) into readable text for Ask.

The Ask assistant reads the distilled *result* lazily through the navigator's
tools, but the source *document* is small, so it is given whole - as one
readable, provenance-annotated string dropped into the system prompt. This is
the document counterpart to `navigator.overview`: a single function that turns
the block list into something the model can read and cite.

Kept deliberately tiny and self-contained: blocks in, text out. No knowledge of
result types or the agent loop.
"""

from __future__ import annotations

from typing import Any

# Guard against a pathologically large document blowing the context window. Real
# TPPs/IPDPs sit well under this; if one ever exceeds it we truncate rather than
# fail (the tail is dropped, with a marker).
MAX_DOCUMENT_CHARS = 120_000


def render(blocks: list[dict[str, Any]]) -> str:
    """Render ordered blocks as readable text: section headings as they change,
    then each block's content tagged with its id so the model can cite it."""
    lines: list[str] = []
    last_heading = ""
    for block in blocks:
        content = str(block.get("content", "")).strip()
        if not content:
            continue
        heading = " > ".join(block.get("heading_stack") or [])
        if heading and heading != last_heading:
            lines.append(f"\n## {heading}")
            last_heading = heading
        block_id = block.get("id", "")
        lines.append(f"[{block_id}] {content}" if block_id else content)

    text = "\n".join(lines).strip()
    if len(text) > MAX_DOCUMENT_CHARS:
        text = text[:MAX_DOCUMENT_CHARS] + "\n...[document truncated]"
    return text or "(the document has no readable text)"
