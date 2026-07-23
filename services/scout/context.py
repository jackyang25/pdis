"""Document-context rendering and bounded, block-aware selection for Scout.

Every reasoning stage receives explicit ``[block:<id>]`` markers so a model can
return document citations that the pipeline validates.  Long documents are
selected per variable by lexical relevance plus neighboring blocks; remaining
space is filled with evenly distributed blocks rather than silently keeping
only the beginning of the document.
"""

from __future__ import annotations

import re
from typing import Iterable

from services.chunker import ContentBlock

from .models import Attribute

ATTRIBUTE_CONTEXT_CHARS = 160_000
WHOLE_DOCUMENT_CONTEXT_CHARS = 500_000

_BLOCK_ID_RE = re.compile(r"\[block:([^\]]+)\]")
_BLOCK_MARKER_RE = re.compile(r"^\[block:([^\]]+)\]$")
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "about", "against", "and", "are", "for", "from", "into", "its",
    "that", "the", "their", "this", "through", "with", "within",
    "product", "target", "variable", "document", "evidence",
}

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


def select_resolution_context(
    blocks: list[ContentBlock],
    attribute: Attribute,
    *,
    max_chars: int = ATTRIBUTE_CONTEXT_CHARS,
) -> str:
    """Return a bounded document view used only to locate a fixed field binding.

    This relevance-selected view is intentionally broader than the field's final
    provenance boundary. Once a binding is resolved, every downstream document-
    aware stage must use :func:`select_binding_context` instead.
    """
    if not blocks:
        return ""
    rendered = [_render_block(block) for block in blocks]
    full = "\n\n".join(rendered)
    if len(full) <= max_chars:
        return full

    terms = _terms(f"{attribute.name} {attribute.description}")
    scored: list[tuple[int, int]] = []
    for index, block in enumerate(blocks):
        haystack = " ".join(
            [
                getattr(block, "content", "") or "",
                " ".join(getattr(block, "heading_stack", []) or []),
                getattr(block, "section_label", "") or "",
            ]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, index))

    selected: set[int] = set()
    # Extracted units already carry exact originating blocks. Seed those before
    # lexical selection so a long document cannot lose its own source claim.
    originating_ids = set(attribute.block_ids)
    selected.update(
        index for index, block in enumerate(blocks) if block.id in originating_ids
    )
    # Retain document boundaries when they fit. Originating blocks take
    # precedence, because they are stronger provenance than a generic preamble.
    boundary_indices = [
        *range(min(3, len(blocks))),
        *range(max(0, len(blocks) - 3), len(blocks)),
    ]
    for index in boundary_indices:
        if _selection_size(rendered, selected | {index}) <= max_chars:
            selected.add(index)

    # Add highest-signal blocks plus immediate context while respecting budget;
    # ties preserve document order. Final rendering restores document order.
    for _, index in sorted(scored, key=lambda item: (-item[0], item[1])):
        candidates = {
            i for i in (index - 1, index, index + 1)
            if 0 <= i < len(blocks)
        }
        if _selection_size(rendered, selected | candidates) <= max_chars:
            selected.update(candidates)

    # Fill unused space with an evenly distributed safety net for synonyms that
    # lexical scoring may miss.
    for index in _even_indices(len(blocks)):
        if _selection_size(rendered, selected | {index}) <= max_chars:
            selected.add(index)

    return _render_with_budget(rendered, selected, max_chars)


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


def _terms(text: str) -> set[str]:
    return {
        token
        for token in _WORD_RE.findall(text.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _even_indices(length: int) -> list[int]:
    if length <= 12:
        return list(range(length))
    # A deterministic document-wide safety net for terminology mismatches.
    return sorted({round(i * (length - 1) / 11) for i in range(12)})


def _render_with_budget(rendered: list[str], selected: set[int], max_chars: int) -> str:
    out: list[str] = []
    used = 0
    for index in sorted(selected):
        block = rendered[index]
        separator = 2 if out else 0
        remaining = max_chars - used - separator
        if remaining <= 0:
            break
        if len(block) > remaining:
            if not out:
                out.append(block[:remaining])
            break
        out.append(block)
        used += separator + len(block)
    return "\n\n".join(out)


def _selection_size(rendered: list[str], selected: set[int]) -> int:
    return sum(len(rendered[index]) for index in selected) + max(0, 2 * (len(selected) - 1))
