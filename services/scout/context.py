"""Document-context rendering and exact block provenance for Scout.

Every reasoning stage receives explicit ``[block:<id>]`` markers so model
citations can be validated. Long documents are split only between complete
blocks; canonical field views are rendered only from their verified spans.
"""

from __future__ import annotations

import re
from typing import Iterable

from services.chunker import ContentBlock

from .models import Attribute

WHOLE_DOCUMENT_CONTEXT_CHARS = 500_000
DOCUMENT_CHUNK_CHARS = 350_000

_BLOCK_ID_RE = re.compile(r"\[block:([^\]]+)\]")
_BLOCK_MARKER_RE = re.compile(r"^\[block:([^\]]+)\]$")
_RENDERED_BLOCK_CONTENT_RE = re.compile(
    r"(?m)^\[block:([^\]]+)\][^\n]*\n(.*?)(?=\n\n\[block:|\Z)",
    re.DOTALL,
)

# One canonical JSON contract shared by every Scout prompt that asks a model to
# cite document blocks. Rendered context uses ``[block:<id>]`` markers, while
# structured outputs carry the bare ID. Keeping this wording centralized avoids
# a producer/validator mismatch across query generation and reasoning stages.
BLOCK_ID_JSON_INSTRUCTION = (
    "For every JSON block-ID array, copy only the complete bare ID from inside a "
    "supplied [block:<id>] marker (for example, \"document/b-0001\"). Do not include "
    "the [block:...] wrapper, shorten the ID, or invent an ID."
)


def render_document_context(blocks: Iterable[ContentBlock]) -> str:
    """Render ordered blocks with stable IDs and lightweight structural context."""
    return "\n\n".join(_render_block(block) for block in blocks)


def chunk_document_context(
    document_context: str,
    *,
    max_chars: int = DOCUMENT_CHUNK_CHARS,
) -> list[str]:
    """Split rendered context only between complete annotated blocks."""
    if not document_context.strip():
        return []
    rendered_blocks = re.split(r"\n\n(?=\[block:[^\]]+\])", document_context)
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for rendered_block in rendered_blocks:
        separator = 2 if current else 0
        if current and current_chars + separator + len(rendered_block) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
            separator = 0
        current.append(rendered_block)
        current_chars += separator + len(rendered_block)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def select_binding_context(
    blocks: list[ContentBlock],
    attribute: Attribute,
) -> str:
    """Render raw exact blocks owned by a canonical field binding.

    This is the fact-verification view: stages that exact-quote or revalidate
    document facts need the original bytes/text. It may still contain adjacent
    table cells, so qualitative reasoning must use
    :func:`render_canonical_binding` instead.
    """
    owned = set(attribute.block_ids)
    if not owned:
        return ""
    return render_document_context(block for block in blocks if block.id in owned)


def render_canonical_binding(attribute: Attribute) -> str:
    """Render the resolved field target with its exact provenance markers.

    Table-row blocks can contain several neighboring variables. Once the field
    resolver has produced the canonical target, downstream queries and judgments
    should reason over that target—not the rest of the coarse source row—while
    retaining the exact block IDs that authorize citations.
    """
    if not attribute.document_target or not attribute.block_ids:
        return ""
    return "\n\n".join(
        f"[block:{block_id}]\n{attribute.document_target}"
        for block_id in attribute.block_ids
    )


def limit_document_context(text: str, *, max_chars: int = WHOLE_DOCUMENT_CONTEXT_CHARS) -> str:
    """Bound already-rendered context while retaining both document boundaries."""
    if len(text) <= max_chars:
        return text
    marker = "\n\n[... middle document blocks omitted for context budget ...]\n\n"
    remaining = max(0, max_chars - len(marker))
    head = int(remaining * 0.6)
    return text[:head] + marker + text[-(remaining - head):]


def document_block_ids(text: str) -> set[str]:
    return set(_BLOCK_ID_RE.findall(text))


def rendered_block_texts(document_context: str) -> dict[str, str]:
    """Return exact block text keyed by its rendered stable ID."""
    return {
        block_id: text
        for block_id, text in _RENDERED_BLOCK_CONTENT_RE.findall(document_context)
    }


def quote_in_text(quote: str, text: str) -> bool:
    """Compare quotations after whitespace/case normalization only."""
    normalized_quote = " ".join(quote.casefold().split())
    return bool(normalized_quote) and normalized_quote in " ".join(
        text.casefold().split()
    )


def validated_block_ids(raw: object, allowed: set[str]) -> list[str]:
    """Return exact allowed IDs in model order, accepting one safe legacy form.

    The canonical JSON form is the bare ID. Older prompts ambiguously requested
    the rendered ``[block:<id>]`` marker, so an exactly wrapped marker is
    canonicalized before membership validation. No prefix, suffix, substring,
    case-folded, or fuzzy matching is permitted.
    """
    if not isinstance(raw, list):
        return []
    validated: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        value = item.strip()
        marker = _BLOCK_MARKER_RE.fullmatch(value)
        if marker:
            value = marker.group(1).strip()
        if value in allowed and value not in validated:
            validated.append(value)
    return validated


def _render_block(block: ContentBlock) -> str:
    metadata: list[str] = []
    headings = " > ".join(getattr(block, "heading_stack", []) or [])
    if headings:
        metadata.append(f"heading={headings}")
    section = getattr(block, "section_label", None)
    if section:
        metadata.append(f"section={section}")
    suffix = f" ({'; '.join(metadata)})" if metadata else ""
    return f"[block:{block.id}]{suffix}\n{block.content}"
