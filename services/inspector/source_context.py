"""Retain section ownership while supplying its same-slide visual context."""

from services.chunker import ContentBlock


def with_slide_overviews(
    selected: list[ContentBlock], source: list[ContentBlock],
) -> list[ContentBlock]:
    """Add retained overviews only for explicitly selected slides/documents.

    An overview does not map the rest of a mixed-topic slide into the section.
    This same selection defines both model input and allowed citation scope.
    """
    ids = {block.id for block in selected}
    slides = {
        (block.doc_id, block.structural_meta["slide"])
        for block in selected
        if type(block.structural_meta.get("slide")) is int
        and block.structural_meta["slide"] > 0
    }
    return [
        block for block in source
        if block.id in ids or (
            block.image is not None
            and block.structural_meta.get("visual_scope") == "full_slide"
            and type(block.structural_meta.get("slide")) is int
            and (block.doc_id, block.structural_meta["slide"]) in slides
        )
    ]
