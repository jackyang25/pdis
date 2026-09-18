"""Build deterministic portable assets for document visual blocks."""

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
        if "unsupported_document_visual" in block.structural_meta.get(
            "extraction_warnings", []
        ):
            continue
        rel_id = block.structural_meta.pop("image_rel_id", None)
        owner = block.structural_meta.get("document_part", "/word/document.xml")
        part = related.get((owner, rel_id)) if rel_id else None
        if part is None:
            block.content = "[image unavailable]"
            _add_extraction_warning(block, "document_image_unavailable")
            continue
        source_media_type = (getattr(part, "content_type", "") or "").lower()
        try:
            image_bytes = part.blob
        except Exception as exc:  # noqa: BLE001 - one corrupt asset is isolated
            logger.warning("Could not read image bytes for %s: %s", block.id, exc)
            block.content = "[image unavailable]"
            _add_extraction_warning(block, "document_image_unavailable")
            continue

        block.image = image_asset_from_bytes(image_bytes, source_media_type)
        if block.image is None:
            block.content = f"[image unavailable: {source_media_type or 'unknown format'}]"
            _add_extraction_warning(block, "document_image_unavailable")
            continue
        block.content = "[image]"
    return blocks


def image_asset_from_bytes(
    data: bytes,
    source_media_type: str,
    *,
    data_media_type: str | None = None,
) -> ImageAsset | None:
    """Normalize bytes while retaining their original document-media provenance."""
    if not data:
        return None
    source_media_type = (source_media_type or "").lower()
    data_media_type = (data_media_type or source_media_type).lower()
    media_type = "image/jpeg" if data_media_type == "image/jpg" else data_media_type
    image_bytes = data
    if data_media_type not in PASSTHROUGH_TYPES:
        converted = _convert_raster_to_png(data) or rasterize_to_png(
            data, data_media_type
        )
        if converted is None:
            return None
        image_bytes = converted
        media_type = "image/png"
    width, height = _pixel_size(image_bytes)
    return ImageAsset(
        media_type=media_type,
        data_base64=base64.b64encode(image_bytes).decode("ascii"),
        sha256=hashlib.sha256(image_bytes).hexdigest(),
        source_media_type=source_media_type or media_type,
        width=width,
        height=height,
    )


def image_asset_byte_size(asset: ImageAsset) -> int:
    """Return the decoded canonical asset size without allocating another copy."""
    payload = asset.data_base64
    padding = len(payload) - len(payload.rstrip("="))
    return len(payload) * 3 // 4 - padding


def _pixel_size(data: bytes) -> tuple[int, int]:
    """The image's own dimensions, read from its header.

    `Image.open` is lazy: it parses the header and stops, so this costs no decode. A
    format Pillow cannot read returns zeros rather than raising - the size is a hint for
    reserving layout, and a document that parses is worth more than one that fails over
    an image whose box we cannot pre-measure.
    """
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception:  # noqa: BLE001 - an unreadable header is not a parse failure
        return 0, 0


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

        document = Document(file_path)
        return {
            (str(owner.partname), rel_id): target
            for owner in document.part.package.parts
            for rel_id, target in owner.related_parts.items()
        }
    except Exception as exc:  # noqa: BLE001 - parse output remains usable
        logger.warning("Could not reopen %s for image assets: %s", file_path, exc)
        return None


def _add_extraction_warning(block: ContentBlock, warning: str) -> None:
    warnings = block.structural_meta.setdefault("extraction_warnings", [])
    if warning not in warnings:
        warnings.append(warning)
