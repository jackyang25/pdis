"""Build deterministic portable assets for document visual blocks."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import logging
from io import BytesIO
from pathlib import Path

from ..models import ContentBlock, ImageAsset
from . import rasterizer

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
    Retained images carry the same bounds as rendered pages: none over the
    per-image pixel limit, and no more than the per-document encoded-byte limit in
    total, so later images past that limit are marked unavailable.
    """
    if Path(file_path).suffix.lower() != ".docx":
        return blocks
    image_blocks = [block for block in blocks if block.block_type == "image"]
    if not image_blocks:
        return blocks

    related = _load_related_parts(file_path)
    if related is None:
        return blocks

    resolved: list[tuple[ContentBlock, bytes, str]] = []
    for block in image_blocks:
        if "unsupported_document_visual" in block.structural_meta.get(
            "extraction_warnings", []
        ):
            continue
        rel_id = block.structural_meta.pop("image_rel_id", None)
        owner = block.structural_meta.get("document_part", "/word/document.xml")
        part = related.get((owner, rel_id)) if rel_id else None
        if part is None:
            _mark_unavailable(block, "[image unavailable]")
            continue
        source_media_type = (getattr(part, "content_type", "") or "").lower()
        try:
            image_bytes = part.blob
        except Exception as exc:  # noqa: BLE001 - one corrupt asset is isolated
            logger.warning("Could not read image bytes for %s: %s", block.id, exc)
            _mark_unavailable(block, "[image unavailable]")
            continue
        resolved.append((block, image_bytes, source_media_type))

    assets = bounded_image_assets(
        image_assets_from_bytes([(data, media) for _, data, media in resolved])
    )
    for (block, _, source_media_type), asset in zip(resolved, assets):
        if asset is None:
            _mark_unavailable(
                block, f"[image unavailable: {source_media_type or 'unknown format'}]"
            )
            continue
        block.image = asset
        block.content = "[image]"
    return blocks


def bounded_image_assets(
    assets: list[ImageAsset | None],
) -> list[ImageAsset | None]:
    """Drop, in order, each asset that would take one document past the byte bound."""
    retained = 0
    bounded: list[ImageAsset | None] = []
    for asset in assets:
        if asset is not None:
            size = image_asset_byte_size(asset)
            if retained + size > rasterizer.MAX_RENDERED_BYTES:
                logger.warning("Image exceeds the per-document encoded-image limit")
                asset = None
            else:
                retained += size
        bounded.append(asset)
    return bounded


def image_asset_from_bytes(
    data: bytes,
    source_media_type: str,
    *,
    data_media_type: str | None = None,
) -> ImageAsset | None:
    """Normalize bytes while retaining their original document-media provenance."""
    return image_assets_from_bytes(
        [(data, source_media_type)], data_media_type=data_media_type
    )[0]


def image_assets_from_bytes(
    items: list[tuple[bytes, str]],
    *,
    data_media_type: str | None = None,
) -> list[ImageAsset | None]:
    """Normalize many images, converting each distinct vector payload once.

    Identical bytes share one conversion, and every vector image that needs the
    office renderer goes through one LibreOffice start rather than one each. An
    image over the per-image pixel bound is ``None``, as an unreadable one is.
    """
    by_digest: dict[tuple[str, str, str], ImageAsset | None] = {}
    keys: list[tuple[str, str, str] | None] = []
    vectors: dict[tuple[str, str, str], bytes] = {}
    for data, source_media_type in items:
        if not data:
            keys.append(None)
            continue
        source = (source_media_type or "").lower()
        declared = (data_media_type or source).lower()
        key = (hashlib.sha256(data).hexdigest(), source, declared)
        keys.append(key)
        if key in by_digest or key in vectors:
            continue
        if declared in PASSTHROUGH_TYPES:
            media = "image/jpeg" if declared == "image/jpg" else declared
            by_digest[key] = _bounded_asset(data, media, source)
            continue
        converted = _convert_raster_to_png(data)
        if converted is not None:
            by_digest[key] = _bounded_asset(converted, "image/png", source)
        else:
            vectors[key] = data

    if vectors:
        pending = list(vectors.items())
        rendered = rasterizer.rasterize_many_to_png(
            [(data, key[2]) for key, data in pending]
        )
        for (key, _), png in zip(pending, rendered):
            by_digest[key] = (
                _bounded_asset(png, "image/png", key[1]) if png is not None else None
            )

    # Each block owns its asset object; identical images share only the conversion.
    return [
        dataclasses.replace(asset)
        if key is not None and (asset := by_digest[key]) is not None
        else None
        for key in keys
    ]


def _bounded_asset(
    image_bytes: bytes, media_type: str, source_media_type: str
) -> ImageAsset | None:
    width, height = _pixel_size(image_bytes)
    if width * height > rasterizer.MAX_RENDER_PIXELS_PER_PAGE:
        logger.warning("Image of %sx%s exceeds the per-image pixel limit", width, height)
        return None
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
            # The header gives the size without decoding; refuse before allocating.
            if image.width * image.height > rasterizer.MAX_RENDER_PIXELS_PER_PAGE:
                return None
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


def _mark_unavailable(block: ContentBlock, content: str) -> None:
    block.content = content
    _add_extraction_warning(block, "document_image_unavailable")


def _add_extraction_warning(block: ContentBlock, warning: str) -> None:
    warnings = block.structural_meta.setdefault("extraction_warnings", [])
    if warning not in warnings:
        warnings.append(warning)
