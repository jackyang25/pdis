"""How Aligner shows a document to a model, and how it reads a citation back.

Both stages send the same view of a document and both parse the same citation shape, and
before this they each held their own copy of the rendering. The copies were identical,
which is the point: a difference between them would be a model selecting line 4 of a
block the validator numbers differently, and the failure would look like a bad citation
rather than a bad render.
"""

from __future__ import annotations

from services.chunker import ContentBlock

from shared.references import reference_array
from shared.source_blocks import image_inputs as _image_inputs, render_blocks
from shared.spans import DocumentSpan, line_span_schema, resolved_spans

__all__ = ["format_blocks", "image_inputs", "read_spans"]

#: What an image block's text is replaced with: the visual itself is sent beside the
#: text, and it is cited by identity, never by a quoted line.
IMAGE_BODY = "Retained visual; cite visual_block_ids, not a text span."


def format_blocks(blocks: list[ContentBlock]) -> str:
    """Blocks addressed by ID, with their headings, their text addressed by line.

    Both addresses are needed: the model names a block to say which passage, and lines
    inside it to say which part of the passage. The line labels are a wire view only -
    nothing that comes back carries text, so they never reach a result. The headings are
    what tells a table cell which row and section it belongs to; without them a cell
    reading "36 months" said nothing about what lasts 36 months.
    """
    return render_blocks(blocks, source_type=True, line_numbers=True, image_body=IMAGE_BODY)


def image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    """Slide and figure images, so a bar set in a picture is readable."""
    return _image_inputs(blocks)


def read_spans(raw: object, blocks: list[ContentBlock]) -> list[DocumentSpan]:
    """The exact passages a model selected, copied out of the blocks it was shown."""
    return resolved_spans(raw, {
        block.id: block.content for block in blocks if block.block_type != "image"
    })


def citation_properties(blocks: list[ContentBlock]) -> dict:
    """Text ranges and visual identities are separate citation mechanisms."""
    text_ids = [block.id for block in blocks if block.block_type != "image"]
    visual_ids = [block.id for block in blocks if block.image is not None]
    return {
        "spans": {
            "type": "array", "items": line_span_schema(text_ids) if text_ids else {
                "type": "object", "properties": {}, "required": [], "additionalProperties": False,
            },
            **({} if text_ids else {"maxItems": 0}),
        },
        "visual_block_ids": reference_array(visual_ids),
    }


def read_visual_ids(raw: object, blocks: list[ContentBlock]) -> list[str]:
    if raw is None:
        return []
    allowed = {block.id for block in blocks if block.image is not None}
    if not isinstance(raw, list) or any(not isinstance(item, str) or item not in allowed for item in raw):
        raise ValueError("visual citation must name a retained image in the supplied document")
    return list(dict.fromkeys(raw))
