"""Attach deterministic, portable image assets to parsed DOCX image blocks."""

from __future__ import annotations

import base64
import hashlib
import logging
from io import BytesIO
from pathlib import Path

from ..models import ContentBlock, ImageAsset
from .rasterizer import rasterize_to_png

logger = logging.getLogger(__name__)

PASSTHROUGH_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
}


def attach_image_assets(
    blocks: list[ContentBlock], file_path: str
) -> list[ContentBlock]:
    """Resolve DOCX relationships and attach one usable image per image block.

    Raster formats already accepted by browsers/models remain byte-identical.
    Unsupported vector formats are rasterized to PNG. Conversion is best-effort:
    a failed visual remains an honest image block without breaking the document.
    """
    if Path(file_path).suffix.lower() != ".docx":
        return blocks
    image_blocks = [block for block in blocks if block.block_type == "image"]
    if not image_blocks:
        return blocks

    related = _load_related_parts(file_path)
    if related is None:
        return blocks

    for block in image_blocks:
        rel_id = block.structural_meta.pop("image_rel_id", None)
        part = related.get(rel_id) if rel_id else None
        if part is None:
            block.content = "[image unavailable]"
            continue
        source_media_type = (getattr(part, "content_type", "") or "").lower()
        try:
            image_bytes = part.blob
        except Exception as exc:  # noqa: BLE001 - one corrupt asset is isolated
            logger.warning("Could not read image bytes for %s: %s", block.id, exc)
            block.content = "[image unavailable]"
            continue

        media_type = "image/jpeg" if source_media_type == "image/jpg" else source_media_type
        if source_media_type not in PASSTHROUGH_TYPES:
            converted = _convert_raster_to_png(image_bytes) or rasterize_to_png(
                image_bytes, source_media_type
            )
            if converted is None:
                block.content = f"[image unavailable: {source_media_type or 'unknown format'}]"
                continue
            image_bytes = converted
            media_type = "image/png"

        block.image = ImageAsset(
            media_type=media_type,
            data_base64=base64.b64encode(image_bytes).decode("ascii"),
            sha256=hashlib.sha256(image_bytes).hexdigest(),
            source_media_type=source_media_type or media_type,
        )
        block.content = "[image]"
    return blocks


def _convert_raster_to_png(data: bytes) -> bytes | None:
    """Normalize any Pillow-readable raster format without a system process."""
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            rendered = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output = BytesIO()
            rendered.save(output, format="PNG")
            return output.getvalue()
    except Exception:  # noqa: BLE001 - vector/unknown types fall through
        return None


def _load_related_parts(file_path: str):
    try:
        from docx import Document

        return Document(file_path).part.related_parts
    except Exception as exc:  # noqa: BLE001 - parse output remains usable
        logger.warning("Could not reopen %s for image assets: %s", file_path, exc)
        return None
