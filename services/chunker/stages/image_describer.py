"""Image describer - turns an embedded figure into its textual record.

Runs after the parser and before the mapper, but only when the document-type
config sets `image_lens` (see DocumentTypeConfig). For each `image` block, it
resolves the embedded image bytes, asks the vision model to describe the figure
through the config's lens, and replaces the block's placeholder content with
that description. The image bytes never persist on the block - downstream stages
(mapper, scout, reviewer) see only text, identical in shape to any other block.

Doc-type-agnostic: the lens (what to look for) is domain content in the config;
this stage only orchestrates. Self-gating - no image blocks, a non-docx source,
or a non-raster/unreadable image leaves blocks untouched (or with the parser's
placeholder), so a failure here never breaks a run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from ..models import ContentBlock, DocumentTypeConfig
from .emf_converter import convert_to_png

logger = logging.getLogger(__name__)

# Generous: these are dense figures and the model spends a reasoning budget
# before emitting text - too low a ceiling yields an empty (length-capped) reply.
DEFAULT_MAX_TOKENS = 12000

# Formats the vision model can read. Vector (emf/wmf) and exotic raster formats
# are left as the placeholder rather than sent and failed.
DESCRIBABLE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
}


class ImageClientProtocol(Protocol):
    """The one capability the describer needs from an injected client."""

    def describe_image(
        self, image_bytes: bytes, *, prompt: str, mime_type: str, max_tokens: int
    ) -> str:
        ...


def describe_images(
    blocks: list[ContentBlock],
    file_path: str,
    config: DocumentTypeConfig,
    llm_client: ImageClientProtocol,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[ContentBlock]:
    """Replace each image block's placeholder with a textual description.

    Mutates and returns the same `blocks` list. Only acts on `.docx` sources
    (the only format that emits image blocks today) and only when `config`
    carries an `image_lens`.
    """
    if not config.image_lens:
        return blocks
    if Path(file_path).suffix.lower() != ".docx":
        return blocks

    image_blocks = [b for b in blocks if b.block_type == "image"]
    if not image_blocks:
        return blocks

    related = _load_related_parts(file_path)
    if related is None:
        return blocks

    for block in image_blocks:
        rel_id = block.structural_meta.get("image_rel_id")
        part = related.get(rel_id) if rel_id else None
        if part is None:
            continue
        content_type = (getattr(part, "content_type", "") or "").lower()
        try:
            blob = part.blob
        except Exception as exc:  # noqa: BLE001 - a bad part shouldn't fail the run
            logger.warning("Could not read image bytes for %s: %s", block.id, exc)
            continue

        mime = content_type
        if content_type not in DESCRIBABLE_TYPES:
            # Vector formats (EMF/WMF) can't be read directly; rasterize to PNG
            # first (LibreOffice, where available). Falls back to an honest
            # placeholder if that's not possible - the figure's caption, legend,
            # and surrounding prose are still captured as their own blocks.
            png = convert_to_png(blob, content_type)
            if png is None:
                block.content = f"[image: {content_type or 'unknown format'}, not described]"
                continue
            blob, mime = png, "image/png"

        prompt = _build_prompt(config, block)
        try:
            description = llm_client.describe_image(
                blob, prompt=prompt, mime_type=mime, max_tokens=max_tokens
            )
        except Exception as exc:  # noqa: BLE001 - vision failure is non-fatal
            logger.warning("Image description failed for %s: %s", block.id, exc)
            continue

        description = (description or "").strip()
        if description:
            block.content = description
        # else: leave the parser's placeholder in place

    return blocks


def _load_related_parts(file_path: str):
    try:
        from docx import Document

        return Document(file_path).part.related_parts
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not reopen %s for image bytes: %s", file_path, exc)
        return None


def _build_prompt(config: DocumentTypeConfig, block: ContentBlock) -> str:
    section_path = " > ".join(block.heading_stack) if block.heading_stack else "(top level)"
    context = (
        f"This figure appears in a {config.intervention_class} "
        f"{config.source_type} document, under section: {section_path}."
    )
    instruction = (
        "Produce ONE self-contained textual description that fully encodes the "
        "figure. The image itself is NOT available downstream - only your text "
        "stands in for it. Transcribe every label, axis, date, milestone, phase, "
        "and quantity you can read; describe the structure and the relationships "
        "between elements (e.g. sequence, dependencies, groupings). Be exhaustive "
        "and specific, but do not infer beyond what is shown. Return prose only - "
        "no preamble, no markdown headers."
    )
    return f"{config.image_lens.strip()}\n\n{context}\n\n{instruction}"
