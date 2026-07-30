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

LINE_SPAN_JSON_INSTRUCTION = (
    "Document text lines are labeled [line:N] within each [block:<id>]. For every "
    "source span, select one complete bare block_id plus inclusive start_line and "
    "end_line values exactly as displayed. Do not retype or paraphrase source text; "
    "deterministic code will copy the selected lines from the original block."
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
    if (
        not attribute.document_target
        or not attribute.block_ids
        or not attribute.document_spans
    ):
        return ""
    rendered: list[str] = []
    seen: set[tuple[str, str]] = set()
    for span in attribute.document_spans:
        for block_id in span.block_ids:
            key = (block_id, span.quote)
            if key in seen:
                continue
            seen.add(key)
            rendered.append(f"[block:{block_id}]\n{span.quote}")
    return "\n\n".join(rendered)


def limit_document_context(text: str, *, max_chars: int = WHOLE_DOCUMENT_CONTEXT_CHARS) -> str:
    """Bound rendered context at block boundaries, retaining both document ends."""
    if len(text) <= max_chars:
        return text
    marker = "\n\n[... middle document blocks omitted for context budget ...]\n\n"
    rendered_blocks = re.split(r"\n\n(?=\[block:[^\]]+\])", text)
    if len(rendered_blocks) <= 1:
        remaining = max(0, max_chars - len(marker))
        head = int(remaining * 0.6)
        return text[:head] + marker + text[-(remaining - head):]

    remaining = max(0, max_chars - len(marker))
    head_budget = int(remaining * 0.6)
    tail_budget = remaining - head_budget
    head: list[str] = []
    head_chars = 0
    for block in rendered_blocks:
        added = len(block) + (2 if head else 0)
        if head and head_chars + added > head_budget:
            break
        head.append(block)
        head_chars += added
    tail: list[str] = []
    tail_chars = 0
    head_count = len(head)
    for block in reversed(rendered_blocks[head_count:]):
        added = len(block) + (2 if tail else 0)
        if tail and tail_chars + added > tail_budget:
            break
        tail.append(block)
        tail_chars += added
    tail.reverse()
    if head_count + len(tail) >= len(rendered_blocks):
        return text
    return "\n\n".join(head) + marker + "\n\n".join(tail)


def document_block_ids(text: str) -> set[str]:
    return set(_BLOCK_ID_RE.findall(text))


def rendered_block_texts(document_context: str) -> dict[str, str]:
    """Return exact block text keyed by its rendered stable ID."""
    return {
        block_id: text
        for block_id, text in _RENDERED_BLOCK_CONTENT_RE.findall(document_context)
    }


def render_line_addressable_context(document_context: str) -> str:
    """Label physical source lines without changing their canonical text.

    This wire view lets a model select source passages while deterministic code
    remains solely responsible for copying exact quotations into result data.
    """
    rendered_blocks = re.split(r"\n\n(?=\[block:[^\]]+\])", document_context)
    addressed: list[str] = []
    for rendered_block in rendered_blocks:
        lines = rendered_block.splitlines()
        if not lines:
            continue
        header, content_lines = lines[0], lines[1:]
        addressed.append(
            "\n".join(
                [header]
                + [f"[line:{index}] {line}" for index, line in enumerate(content_lines, 1)]
            )
        )
    return "\n\n".join(addressed)


def selected_source_lines(
    raw_span: object,
    source_blocks: dict[str, str],
) -> tuple[str, str] | None:
    """Resolve one model-selected line range to exact canonical source text."""
    if not isinstance(raw_span, dict):
        return None
    block_id = str(raw_span.get("block_id", "")).strip()
    if block_id not in source_blocks:
        return None
    start_line = raw_span.get("start_line")
    end_line = raw_span.get("end_line")
    if (
        isinstance(start_line, bool)
        or isinstance(end_line, bool)
        or not isinstance(start_line, int)
        or not isinstance(end_line, int)
    ):
        return None
    lines = source_blocks[block_id].splitlines()
    if not (1 <= start_line <= end_line <= len(lines)):
        return None
    quote = "\n".join(lines[start_line - 1:end_line]).strip()
    if not quote:
        return None
    return quote, block_id


def validated_block_ids(raw: object, allowed: set[str]) -> list[str]:
    """Return exact allowed bare IDs in model order."""
    if not isinstance(raw, list):
        return []
    validated: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        value = item.strip()
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
