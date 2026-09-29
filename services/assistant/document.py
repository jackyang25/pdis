"""The documents source: find, read, page and view parsed blocks by exact ID."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from shared.chat import LabelledImage, ToolOutput
from shared.document_metadata import extraction_context

from . import limits, sources
from .workspace import Visual, WorkspaceIndex, doc_id_of, location_of

UNAVAILABLE = sources.unavailable("Source document")

# The browser tags a re-uploaded version with 6 hex digits, 14 when those collide.
_VERSION = re.compile(r"^(?P<base>.+)@[0-9a-f]{6}(?:[0-9a-f]{8})?$")
# Parser facts about what extraction could not keep. Each is drawn from a closed
# vocabulary, so a document contributes a bounded number of distinct lines.
_LIMITATION_KEYS = ("extraction_warnings", "unsupported_visual_kind")


@dataclass
class VisualBudget:
    """How many images one question may still view."""

    remaining: int = limits.MAX_VISUALS_PER_QUESTION
    viewed: int = 0
    withheld: int = 0

    def take(self, wanted: int) -> int:
        granted = max(0, min(wanted, self.remaining))
        self.remaining -= granted
        self.viewed += granted
        self.withheld += wanted - granted
        return granted


def overview(index: WorkspaceIndex) -> str:
    """Return document names, block ranges, and a compact heading map."""
    if not index.documents:
        return "No source documents are held."
    lines = [f"{len(index.blocks)} parsed blocks across {len(index.documents)} document(s)."]
    for doc in index.documents:
        members = index.blocks_of(doc.doc_id)
        tag = " (user-supplied attachment)" if doc.user_supplied else ""
        visuals = f"; {len(doc.visuals)} visual(s): {visual_ranges(doc.visuals)}" if doc.visuals else ""
        readers = _readers(index, doc.doc_id)
        line = f"- {doc.doc_id}{_version_note(index, doc.doc_id)}{tag}: {len(members)} blocks{visuals}"
        lines.append(line + (f"; read by: {', '.join(readers)}" if readers else ""))
        # Only the document's limitations, never a block's location: a slide number or
        # note ID per block made this one line per slide, so the map grew with the deck.
        for limitation in dict.fromkeys(
            extraction_context({key: meta[key] for key in _LIMITATION_KEYS if key in meta})
            for meta in (block.get("structural_meta") or {} for block in members)
        ):
            if limitation:
                lines.append(f"  extraction: {limitation}")
        if doc.headings:
            shown = doc.headings[: limits.MAP_HEADINGS_PER_DOCUMENT]
            more = len(doc.headings) - len(shown)
            lines.append(f"  headings: {' | '.join(shown)}" + (f" … +{more} more" if more else ""))
    return "\n".join(lines)


def visual_ranges(visuals: tuple[Visual, ...]) -> str:
    """Where a document's visuals are, as compressed ranges: "slides 1–3, 5; 2 unplaced"."""
    by_kind: dict[str, list[int]] = {}
    unplaced = 0
    for visual in visuals:
        kind, _, number = visual.location.partition(" ")
        if number.isdigit():
            by_kind.setdefault(kind, []).append(int(number))
        else:
            unplaced += 1
    parts = []
    for kind, numbers in by_kind.items():
        runs, numbers = [], sorted(set(numbers))
        start = prev = numbers[0]
        for n in numbers[1:] + [None]:
            if n is not None and n == prev + 1:
                prev = n
                continue
            runs.append(str(start) if start == prev else f"{start}–{prev}")
            if n is not None:
                start = prev = n
        parts.append(f"{kind}s {', '.join(runs)}")
    if unplaced:
        parts.append(f"{unplaced} unplaced")
    return "; ".join(parts)


def _readers(index: WorkspaceIndex, doc_id: str) -> list[str]:
    return [f"{entry.result_type} ({entry.label})" for entry in index.results if doc_id in entry.doc_ids]


def _version_note(index: WorkspaceIndex, doc_id: str) -> str:
    match = _VERSION.match(doc_id)
    if not match:
        return ""
    siblings = sum(1 for doc in index.documents if (m := _VERSION.match(doc.doc_id)) and m["base"] == match["base"])
    return f" (one of {siblings} versions of {match['base']})"


def find(index: WorkspaceIndex, query: Any, doc_id: str | None = None) -> str:
    """Locate document blocks by search term and return IDs with local snippets."""
    if not index.blocks:
        return UNAVAILABLE
    term = sources.search_term(query)
    if term is None:
        return sources.EMPTY_QUERY
    if doc_id is not None and index.document(doc_id) is None:
        return f"(document not found: {doc_id})"
    scope = index.blocks_of(doc_id) if doc_id is not None else list(index.blocks.values())
    hits, owners = [], []
    for block in scope:
        heading = " > ".join(block.get("heading_stack") or [])
        text = f"{heading}\n{block.get('content') or ''}"
        found = text.lower().find(term.lower())
        if found >= 0:
            hits.append(sources.Hit(
                id=str(block["id"]), label=heading, snippet=sources.snippet(text, found, len(term)),
                note=extraction_context(block.get("structural_meta") or {}),
            ))
            owners.append(doc_id_of(block))
    overflow = None
    if len(hits) > limits.MAX_FIND_HITS:
        rest = Counter(owners[limits.MAX_FIND_HITS :])
        overflow = ("…[" + ", ".join(f"{count} more in {owner}" for owner, count in rest.items())
                    + "; narrow with doc_id]")
    return sources.render_hits(hits, limits.MAX_FIND_HITS, overflow=overflow)


def get(index: WorkspaceIndex, block_ids: list[str], *, start_char: int = 0) -> str:
    """Read exact blocks. Large individual blocks can be paged with start_char."""
    if not index.blocks:
        return UNAVAILABLE
    requested = list(dict.fromkeys(str(value) for value in block_ids if value))
    if not requested:
        return "(no block ids supplied)"
    start_char, output, used = max(0, start_char), [], 0
    for block_id in requested:
        block = index.block(block_id)
        if block is None:
            output.append(f"[{block_id}] (block not found)")
            continue
        content = str(block.get("content") or "")
        chunk = content[start_char : start_char + limits.MAX_BLOCK_CHARS]
        rendered = f"{_header(block)}\n{chunk}"
        if start_char + len(chunk) < len(content):
            rendered += f"\n…[block continues; call again with start_char={start_char + len(chunk)}]"
        if output and used + len(rendered) > limits.MAX_READ_CHARS:
            output.append("…[tool output budget reached; request remaining block ids separately]")
            break
        output.append(rendered)
        used += len(rendered)
    return "\n\n".join(output)


def get_range(index: WorkspaceIndex, doc_id: str, *, start: int = 0, count: int = limits.MAX_RANGE_BLOCKS) -> str:
    """Read an ordered document slice for broad review and summarization."""
    if not index.blocks:
        return UNAVAILABLE
    members = index.blocks_of(doc_id)
    if not members:
        return f"(document not found: {doc_id})"
    start, count = max(0, start), max(1, min(count, limits.MAX_RANGE_BLOCKS))
    selected = members[start : start + count]
    rendered = get(index, [str(block["id"]) for block in selected])
    if start + len(selected) < len(members):
        rendered += f"\n\n…[document continues; call again with start={start + len(selected)}]"
    return rendered


def view(index: WorkspaceIndex, block_ids: list[str], budget: VisualBudget) -> ToolOutput:
    """Return each block's retained image labelled with its exact ID and location.

    An image block's own content is only "[image]", so each one also lists the IDs of
    the text blocks on the same slide or page, for read_document to read.
    """
    if not index.blocks:
        return ToolOutput(UNAVAILABLE)
    requested = list(dict.fromkeys(str(value) for value in block_ids if value))
    if not requested:
        return ToolOutput("(no block ids supplied)")
    ignored = requested[limits.MAX_VISUALS_PER_CALL :]
    lines: list[str] = []
    wanted: list[tuple[dict[str, Any], LabelledImage]] = []
    for block_id in requested[: limits.MAX_VISUALS_PER_CALL]:
        block = index.block(block_id)
        if block is None:
            lines.append(f"[{block_id}] (block not found)")
            continue
        image = index.image(block_id)
        if image is None:
            lines.append(f"{_header(block)}\n(no retained image)\n{sources.truncate(str(block.get('content') or ''), limits.MAX_BLOCK_CHARS, 'use read_document')}")
            continue
        wanted.append((block, image))
    granted = budget.take(len(wanted))
    images = []
    for position, (block, image) in enumerate(wanted):
        location = _visual_location(index, str(block["id"]))
        header = _header(block, location=location)
        text = _text_beside(index, block, location)
        if position < granted:
            images.append(image)
            lines.append(f"{header}\n(image attached)\n{text}")
        else:
            lines.append(f"{header}\n(image withheld: this question's budget of "
                         f"{limits.MAX_VISUALS_PER_QUESTION} images is spent; say which you viewed)\n{text}")
    if ignored:
        lines.append(f"…[{len(ignored)} more block ids ignored; at most {limits.MAX_VISUALS_PER_CALL} per call]")
    return ToolOutput("\n\n".join(lines), tuple(images))


def _visual_location(index: WorkspaceIndex, block_id: str) -> str:
    """The index's own record of where a visual sits, for headers `extraction_context` cannot phrase this way."""
    for doc in index.documents:
        for visual in doc.visuals:
            if visual.block_id == block_id:
                return visual.location
    return ""


def _text_beside(index: WorkspaceIndex, block: dict[str, Any], location: str) -> str:
    """The IDs of the other text blocks sharing a visual's slide or page."""
    if not location:
        return "(no slide or page recorded, so no text beside it to list)"
    kind = location.partition(" ")[0]
    own = str(block["id"])
    beside = [
        str(other["id"]) for other in index.blocks_of(doc_id_of(block))
        if str(other["id"]) != own and index.image(str(other["id"])) is None and location_of(other) == location
    ]
    if not beside:
        return f"(no other text blocks on this {kind})"
    listed = ", ".join(f"[{block_id}]" for block_id in beside[: limits.MAX_TEXT_BESIDE_VISUAL])
    hidden = len(beside) - limits.MAX_TEXT_BESIDE_VISUAL
    if hidden > 0:
        listed += f" …[{hidden} more on this {kind}; read them with read_document_range]"
    return f"text on this {kind}: {listed}"


def _header(block: dict[str, Any], *, location: str = "") -> str:
    heading = " > ".join(block.get("heading_stack") or [])
    header = f"[{block['id']}]" + (f" heading={heading}" if heading else "")
    if location:
        header += f" ({location})"
    extraction = extraction_context(block.get("structural_meta") or {})
    return header + (f" | {extraction}" if extraction else "")
