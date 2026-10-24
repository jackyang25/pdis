"""How a parsed document block is shown to a model, once for every tool.

Inspector, Aligner and Screener each held their own renderer and their own copy of the
image list, and the three had drifted: one named a block's headings and another did not,
so a table cell reached one tool with its section and another with nothing but its text.
The shape is one now, and what genuinely differs between the tools is an option: whether
the document is named (a run reading several), whether lines are numbered (a stage
citing line ranges), and which parser-authored groupings are listed.

Every block opens with `[block:<id>]`, the marker `shared.spans` and Scout already use, so
a model meets one address form across the suite.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Protocol, Sequence

from shared.document_metadata import extraction_context
from shared.spans import line_addressable
from shared.visuals import ImageDetail


class SourceBlock(Protocol):
    """The fields of Chunker's `ContentBlock` a renderer reads."""

    id: str
    doc_id: str
    block_type: str
    source_type: str | None
    content: str
    heading_stack: list[str]
    structural_meta: dict[str, Any]
    image: Any


def render_block(
    block: SourceBlock,
    *,
    document: bool = False,
    source_type: bool = False,
    line_numbers: bool = False,
    groups: Callable[[SourceBlock], Iterable[str]] | None = None,
    image_body: str | None = None,
) -> str:
    """One block: its address and context on the first line, then its text.

    ``document`` names the block's document, for a request spanning several.
    ``source_type`` names the document's type. ``line_numbers`` labels each line for
    stages that cite line ranges. ``groups`` lists parser-authored groupings (a page, a
    table) a stage relies on. ``image_body`` replaces an image block's placeholder text
    with what the model should do with the visual sent beside it.
    """
    header = [block.block_type]
    if document:
        header.append(f"document: {block.doc_id}")
    if source_type and block.source_type:
        header.append(f"document type: {block.source_type}")
    header.append("headings: " + (" > ".join(block.heading_stack) if block.heading_stack else "none"))
    header.extend(groups(block) if groups else ())
    lines = [f"[block:{block.id}] " + " | ".join(header)]
    location = extraction_context(block.structural_meta)
    if location:
        lines.append(f"Source location: {location}")
    if block.block_type == "image" and image_body is not None:
        lines.append(image_body)
    else:
        lines.append(line_addressable(block.content) if line_numbers else block.content)
    return "\n".join(lines)


def render_blocks(blocks: Sequence[SourceBlock], **options: Any) -> str:
    """Blocks in the order given, separated by a blank line; `(none)` when empty."""
    return "\n\n".join(render_block(block, **options) for block in blocks) or "(none)"


def image_inputs(
    blocks: Iterable[SourceBlock], *, detail: ImageDetail = "high",
) -> list[dict[str, str]]:
    """Every retained visual among ``blocks``, labelled by its block ID, at ``detail``."""
    return [
        {"block_id": block.id, "data_url": block.image.data_url(), "detail": detail}
        for block in blocks
        if block.image
    ]
