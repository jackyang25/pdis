"""PPTX parser producing the same ordered, citable block contract as DOCX."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any
from zipfile import BadZipFile

from pptx import Presentation
from pptx.exc import PackageNotFoundError
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from ..models import ContentBlock, ImageAsset
from . import rasterizer
from .image_assets import (
    bounded_image_assets,
    image_asset_byte_size,
    image_asset_from_bytes,
    image_assets_from_bytes,
)
from .rasterizer import (
    RendererUnavailableError,
    RenderError,
    render_presentation_slides,
)
from .table_structure import serialize_table_row

logger = logging.getLogger(__name__)

PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
IMAGE_PLACEHOLDER = "[image]"
UNSUPPORTED_VISUAL_PLACEHOLDER = "[unsupported visual object]"
DIAGRAM_URI = "http://schemas.openxmlformats.org/drawingml/2006/diagram"


def parse_pptx(file_path: str, doc_id: str) -> list[ContentBlock]:
    """Parse slide text/tables and retain one faithful visual per slide.

    LibreOffice rendering preserves composite layout, charts, SmartArt, and
    drawing shapes. If rendering is unavailable, embedded picture bytes are
    retained instead; text and table extraction never depends on rendering.
    """
    _validate_file_path(file_path)
    try:
        presentation = Presentation(file_path)
    except (PackageNotFoundError, BadZipFile, KeyError) as exc:
        # The package's own message names the temporary path the upload was written to.
        raise ValueError(f"{doc_id}: the file is not a readable PPTX presentation.") from exc
    expected_slides = set(range(1, len(presentation.slides) + 1))
    render_warning: str | None = None
    try:
        slide_renders = render_presentation_slides(
            file_path, expected_pages=len(expected_slides)
        )
    except RendererUnavailableError as exc:
        logger.info("Presentation renderer unavailable for %s: %s", doc_id, exc)
        slide_renders = {}
        render_warning = "presentation_renderer_unavailable"
    except RenderError as exc:
        logger.warning("Presentation rendering failed for %s: %s", doc_id, exc)
        slide_renders = {}
        render_warning = "presentation_render_failed"

    if render_warning is None and set(slide_renders) != expected_slides:
        logger.warning(
            "Presentation rendering returned incomplete slide coverage for %s", doc_id
        )
        slide_renders = {}
        render_warning = "presentation_render_failed"

    slide_assets: dict[int, ImageAsset] = {}
    published_image_bytes = 0
    if render_warning is None:
        for slide_number, rendered in slide_renders.items():
            asset = image_asset_from_bytes(
                rendered,
                PPTX_MEDIA_TYPE,
                data_media_type="image/png",
            )
            if asset is None:
                logger.warning(
                    "Presentation rendering returned an unreadable slide for %s", doc_id
                )
                slide_assets = {}
                render_warning = "presentation_render_failed"
                break
            published_image_bytes += image_asset_byte_size(asset)
            if published_image_bytes > rasterizer.MAX_RENDERED_BYTES:
                logger.warning(
                    "Presentation rendering exceeded the encoded-image limit for %s",
                    doc_id,
                )
                slide_assets = {}
                render_warning = "presentation_render_failed"
                break
            slide_assets[slide_number] = asset
    blocks: list[ContentBlock] = []

    for slide_number, slide in enumerate(presentation.slides, start=1):
        slide_start = len(blocks)
        title_shape = slide.shapes.title
        title = _shape_text(title_shape) if title_shape is not None else ""
        heading_stack = [title] if title else []
        shape_records = list(
            _ordered_shapes(
                slide.shapes,
                slide_width=presentation.slide_width,
                slide_height=presentation.slide_height,
            )
        )

        if title:
            title_record = next(
                (record for record in shape_records if _is_shape(record[0], title_shape)),
                None,
            )
            blocks.append(
                _make_block(
                    doc_id=doc_id,
                    block_type="heading",
                    content=title,
                    heading_stack=heading_stack,
                    structural_meta={
                        "slide": slide_number,
                        "heading_level": 1,
                        **(title_record[2] if title_record else {}),
                    },
                    style_hint={"source": "pptx_title"},
                )
            )

        for shape, shape_path, position in shape_records:
            if _is_shape(shape, title_shape):
                continue
            common_meta = {
                "slide": slide_number,
                "shape_path": shape_path,
                **position,
            }
            if bool(getattr(shape, "has_table", False)):
                blocks.extend(
                    _table_blocks(
                        shape.table,
                        doc_id=doc_id,
                        heading_stack=heading_stack,
                        structural_meta=common_meta,
                    )
                )
                continue
            if bool(getattr(shape, "has_text_frame", False)):
                blocks.extend(
                    _text_blocks(
                        shape.text_frame,
                        doc_id=doc_id,
                        heading_stack=heading_stack,
                        structural_meta=common_meta,
                    )
                )

        notes = _speaker_notes(slide)
        if notes:
            blocks.append(
                _make_block(
                    doc_id=doc_id,
                    block_type="paragraph",
                    content=notes,
                    heading_stack=heading_stack,
                    structural_meta={"slide": slide_number, "speaker_notes": True},
                    style_hint={"source": "pptx_speaker_notes"},
                )
            )

        rendered_asset = slide_assets.get(slide_number)
        if rendered_asset is not None:
            blocks.append(
                _image_block(
                    doc_id=doc_id,
                    image=rendered_asset,
                    heading_stack=heading_stack,
                    structural_meta={
                        "slide": slide_number,
                        "visual_scope": "full_slide",
                    },
                    source="pptx_slide_render",
                )
            )
        else:
            blocks.extend(
                _embedded_picture_blocks(
                    shape_records,
                    doc_id=doc_id,
                    slide_number=slide_number,
                    heading_stack=heading_stack,
                )
            )

        # A hidden slide is still part of the document; say so rather than leave a
        # reader to assume it was presented.
        if slide._element.get("show") in {"0", "false"}:
            for block in blocks[slide_start:]:
                block.structural_meta["slide_hidden"] = True

    if not slide_assets:
        _bound_embedded_pictures(blocks)

    if render_warning is not None and all(
        block.content == UNSUPPORTED_VISUAL_PLACEHOLDER for block in blocks
    ):
        raise ValueError(
            f"{doc_id}: {render_warning}; degraded presentation parse has no retained content."
        )

    if render_warning is not None:
        for block in blocks:
            warnings = block.structural_meta.setdefault("extraction_warnings", [])
            if render_warning not in warnings:
                warnings.append(render_warning)

    image_index = 0
    for ordinal, block in enumerate(blocks):
        block.ordinal = ordinal
        block.id = f"{doc_id}/b-{ordinal:04d}"
        if block.block_type == "image":
            block.structural_meta["image_index"] = image_index
            image_index += 1
    return blocks


def _is_shape(shape: Any, other: Any) -> bool:
    """python-pptx builds a new proxy per access, so compare the XML element."""
    return other is not None and shape._element is other._element


def _validate_file_path(file_path: str) -> None:
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("file_path must be a non-empty string")
    if not file_path.lower().endswith(".pptx"):
        raise ValueError("file_path must point to a .pptx file")
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)


def _ordered_shapes(
    shapes: Iterable[Any],
    *,
    slide_width: int,
    slide_height: int,
    prefix: str = "",
    transform: tuple[float, float, float, float] = (1.0, 0.0, 1.0, 0.0),
) -> Iterable[tuple[Any, str, dict[str, float]]]:
    """Yield leaf shapes in reading order with their slide-relative position.

    A group's children are positioned in the group's own child coordinate space
    (`a:chOff`/`a:chExt`), which the group's `a:off`/`a:ext` map onto its parent, so
    positions are carried through every enclosing group to the slide.
    """
    indexed = list(enumerate(shapes))
    indexed.sort(
        key=lambda item: (
            int(getattr(item[1], "top", 0) or 0),
            int(getattr(item[1], "left", 0) or 0),
            item[0],
        )
    )
    for original_index, shape in indexed:
        path = f"{prefix}.{original_index}" if prefix else str(original_index)
        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
            yield from _ordered_shapes(
                shape.shapes,
                slide_width=slide_width,
                slide_height=slide_height,
                prefix=path,
                transform=_group_transform(shape, transform),
            )
            continue
        yield shape, path, _normalized_position(
            shape, slide_width, slide_height, transform
        )


def _group_transform(
    group: Any, outer: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Compose the group's child-to-parent mapping with its parent's mapping."""
    xfrm = group._element.grpSpPr.find(qn("a:xfrm"))
    if xfrm is None:
        return outer

    def pair(tag: str, first: str, second: str) -> tuple[int, int] | None:
        element = xfrm.find(qn(tag))
        if element is None:
            return None
        return int(element.get(first, 0)), int(element.get(second, 0))

    offset, extent = pair("a:off", "x", "y"), pair("a:ext", "cx", "cy")
    child_offset, child_extent = pair("a:chOff", "x", "y"), pair("a:chExt", "cx", "cy")
    if None in (offset, extent, child_offset, child_extent):
        return outer
    scale_x, offset_x, scale_y, offset_y = outer
    group_scale_x = extent[0] / child_extent[0] if child_extent[0] else 1.0
    group_scale_y = extent[1] / child_extent[1] if child_extent[1] else 1.0
    return (
        scale_x * group_scale_x,
        offset_x + scale_x * (offset[0] - child_offset[0] * group_scale_x),
        scale_y * group_scale_y,
        offset_y + scale_y * (offset[1] - child_offset[1] * group_scale_y),
    )


def _normalized_position(
    shape: Any,
    slide_width: int,
    slide_height: int,
    transform: tuple[float, float, float, float] = (1.0, 0.0, 1.0, 0.0),
) -> dict[str, float]:
    width = max(int(slide_width), 1)
    height = max(int(slide_height), 1)
    scale_x, offset_x, scale_y, offset_y = transform
    left = offset_x + scale_x * int(getattr(shape, "left", 0) or 0)
    top = offset_y + scale_y * int(getattr(shape, "top", 0) or 0)
    return {
        "x": round(left / width, 4),
        "y": round(top / height, 4),
        "width": round(scale_x * int(getattr(shape, "width", 0) or 0) / width, 4),
        "height": round(scale_y * int(getattr(shape, "height", 0) or 0) / height, 4),
    }


def _shape_text(shape: Any) -> str:
    if shape is None or not bool(getattr(shape, "has_text_frame", False)):
        return ""
    return "\n".join(
        paragraph.text.strip()
        for paragraph in shape.text_frame.paragraphs
        if paragraph.text.strip()
    )


def _text_blocks(
    text_frame: Any,
    *,
    doc_id: str,
    heading_stack: list[str],
    structural_meta: dict[str, Any],
) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for paragraph_index, paragraph in enumerate(text_frame.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        blocks.append(
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=text,
                heading_stack=heading_stack,
                structural_meta={
                    **structural_meta,
                    "paragraph_index": paragraph_index,
                    "bullet_level": int(getattr(paragraph, "level", 0) or 0),
                },
                style_hint={"source": "pptx_text"},
            )
        )
    return blocks


def _table_blocks(
    table: Any,
    *,
    doc_id: str,
    heading_stack: list[str],
    structural_meta: dict[str, Any],
) -> list[ContentBlock]:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    normalized = [_normalize_row(row, width) for row in rows]

    if width == 1:
        return [
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=row[0],
                heading_stack=heading_stack,
                structural_meta={**structural_meta, "row_index": row_index},
                style_hint={"source": "pptx_single_column_table"},
            )
            for row_index, row in enumerate(normalized)
            if row[0]
        ]

    headers = normalized[0]
    data_rows = normalized[1:]
    if not data_rows:
        content = " | ".join(value for value in headers if value)
        return [
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=content,
                heading_stack=heading_stack,
                structural_meta={
                    **structural_meta,
                    "row_index": 0,
                    "column_headers": headers,
                },
                style_hint={"source": "pptx_table_headers"},
            )
        ] if content else []

    blocks: list[ContentBlock] = []
    for row_index, row in enumerate(data_rows, start=1):
        content, table_cells = serialize_table_row(headers, row)
        if not content:
            continue
        blocks.append(
            _make_block(
                doc_id=doc_id,
                block_type="table_row",
                content=content,
                heading_stack=heading_stack,
                structural_meta={
                    **structural_meta,
                    "row_index": row_index,
                    "column_headers": headers,
                    "table_cells": table_cells,
                },
                style_hint={"source": "pptx_table_row"},
            )
        )
    return blocks


def _normalize_row(row: list[str], width: int) -> list[str]:
    return row[:width] + [""] * max(0, width - len(row))


def _speaker_notes(slide: Any) -> str:
    if not bool(getattr(slide, "has_notes_slide", False)):
        return ""
    try:
        text_frame = slide.notes_slide.notes_text_frame
    except (AttributeError, ValueError):
        return ""
    return "\n".join(
        paragraph.text.strip()
        for paragraph in text_frame.paragraphs
        if paragraph.text.strip()
    )


def _embedded_picture_blocks(
    shape_records: list[tuple[Any, str, dict[str, float]]],
    *,
    doc_id: str,
    slide_number: int,
    heading_stack: list[str],
) -> list[ContentBlock]:
    """Retain a slide's own pictures and flag the visuals only a render could show.

    Without a full-slide render a chart, SmartArt diagram or embedded object has no
    image at all, so it gets the same unsupported-visual block DOCX gives one rather
    than vanishing.
    """
    warnings: dict[int, ContentBlock] = {}
    pictures: list[tuple[int, str, dict[str, float], bytes, str]] = []
    for order, (shape, shape_path, position) in enumerate(shape_records):
        visual_kind = _unsupported_visual_kind(shape)
        if visual_kind is not None:
            warnings[order] = _make_block(
                doc_id=doc_id,
                block_type="image",
                content=UNSUPPORTED_VISUAL_PLACEHOLDER,
                heading_stack=heading_stack,
                structural_meta={
                    "slide": slide_number,
                    "shape_path": shape_path,
                    **position,
                    "extraction_warnings": ["unsupported_document_visual"],
                    "unsupported_visual_kind": visual_kind,
                },
                style_hint={"source": "pptx_unsupported_visual"},
            )
            continue
        try:
            picture = shape.image
            data = picture.blob
            source_media_type = picture.content_type
        except (AttributeError, ValueError, KeyError):
            continue
        pictures.append((order, shape_path, position, data, source_media_type))

    placed = dict(warnings)
    assets = image_assets_from_bytes(
        [(data, media_type) for *_, data, media_type in pictures]
    )
    for (order, shape_path, position, _, _), asset in zip(pictures, assets):
        if asset is None:
            logger.warning(
                "Could not retain PPTX picture on slide %s at shape %s",
                slide_number,
                shape_path,
            )
            continue
        placed[order] = _image_block(
            doc_id=doc_id,
            image=asset,
            heading_stack=heading_stack,
            structural_meta={
                "slide": slide_number,
                "shape_path": shape_path,
                "visual_scope": "embedded_picture",
                **position,
            },
            source="pptx_picture",
        )
    return [placed[order] for order in sorted(placed)]


def _bound_embedded_pictures(blocks: list[ContentBlock]) -> None:
    """Hold retained embedded pictures to the per-document encoded-byte bound."""
    pictures = [
        block for block in blocks
        if block.block_type == "image" and block.image is not None
    ]
    for block, asset in zip(
        pictures, bounded_image_assets([block.image for block in pictures])
    ):
        if asset is None:
            block.image = None
            block.content = "[image unavailable]"
            warnings = block.structural_meta.setdefault("extraction_warnings", [])
            if "document_image_unavailable" not in warnings:
                warnings.append("document_image_unavailable")


def _unsupported_visual_kind(shape: Any) -> str | None:
    if bool(getattr(shape, "has_chart", False)):
        return "chart"
    if getattr(shape, "shape_type", None) in {
        MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT,
        MSO_SHAPE_TYPE.LINKED_OLE_OBJECT,
    }:
        return "embedded_object"
    graphic_data = shape._element.find(".//" + qn("a:graphicData"))
    if graphic_data is not None and graphic_data.get("uri") == DIAGRAM_URI:
        return "diagram"
    return None


def _image_block(
    *,
    doc_id: str,
    image: ImageAsset,
    heading_stack: list[str],
    structural_meta: dict[str, Any],
    source: str,
) -> ContentBlock:
    return ContentBlock(
        id="",
        doc_id=doc_id,
        ordinal=-1,
        block_type="image",
        content=IMAGE_PLACEHOLDER,
        heading_stack=heading_stack.copy(),
        structural_meta=structural_meta,
        style_hint={"source": source},
        image=image,
    )


def _make_block(
    *,
    doc_id: str,
    block_type: str,
    content: str,
    heading_stack: list[str],
    structural_meta: dict[str, Any],
    style_hint: dict[str, Any],
) -> ContentBlock:
    return ContentBlock(
        id="",
        doc_id=doc_id,
        ordinal=-1,
        block_type=block_type,
        content=content,
        heading_stack=heading_stack.copy(),
        structural_meta=structural_meta,
        style_hint=style_hint,
    )
