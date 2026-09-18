"""PDF page text and rendered page visuals → canonical blocks.

Page boundaries are declared by PDF; headings, tables and reading order are not.
Never turn layout guesses into structural metadata or exact-quote guarantees.
"""

from pathlib import Path
from contextlib import contextmanager
import logging
import threading

from pypdf import PdfReader

from ..models import ContentBlock
from . import rasterizer
from .image_assets import image_asset_byte_size, image_asset_from_bytes
from .rasterizer import RenderError, render_pdf_pages

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PAGE_STREAM_BYTES = 5 * 1024 * 1024


class PdfInputError(ValueError):
    """A document cannot be read under the text-extraction contract."""


class _PdfWarnings(logging.Handler):
    """pypdf can swallow malformed Form errors; observe only this parse's thread."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.thread_id = threading.get_ident()
        self.seen = False

    def emit(self, record):
        if record.thread == self.thread_id:
            self.seen = True


@contextmanager
def _reject_extraction_warnings(doc_id: str):
    logger = logging.getLogger("pypdf")
    warnings = _PdfWarnings()
    logger.addHandler(warnings)
    try:
        yield
        if warnings.seen:
            raise PdfInputError(
                f"{doc_id}: PDF produced extraction warnings and may be incomplete. "
                "Upload a fresh export."
            )
    finally:
        logger.removeHandler(warnings)
        warnings.close()


def parse_pdf(file_path: str, doc_id: str) -> list[ContentBlock]:
    path = Path(file_path)
    if path.stat().st_size > MAX_PDF_BYTES:
        raise PdfInputError(f"{doc_id}: PDF exceeds 20 MB. Split it into smaller documents.")
    try:
        # strict=True alone still permits logged-and-swallowed extraction failures.
        # Observe the library's warnings too, without changing global logger levels.
        with _reject_extraction_warnings(doc_id), path.open("rb") as source:
            reader = PdfReader(source, strict=True)
            if reader.is_encrypted:
                raise PdfInputError(f"{doc_id}: PDF is encrypted. Upload an unlocked copy.")
            count = len(reader.pages)
            if not count:
                raise PdfInputError(f"{doc_id}: PDF has no pages.")
            if count > MAX_PDF_PAGES:
                raise PdfInputError(f"{doc_id}: PDF exceeds 200 pages. Split it into smaller documents.")
            page_texts: list[str] = []
            for number, page in enumerate(reader.pages, 1):
                content = page.get_contents()
                if content is not None and len(content.get_data()) > MAX_PAGE_STREAM_BYTES:
                    raise PdfInputError(
                        f"{doc_id}: PDF page {number} is too complex to extract. Upload a simpler export."
                    )
                text = page.extract_text().strip()
                if not text:
                    # Includes blank pages: do not guess whether an empty extraction
                    # was intentional, a scan, or content the library failed to read.
                    raise PdfInputError(
                        f"{doc_id}: PDF page {number} has no extractable text. "
                        "Upload a text-based export or remove blank pages; scanned pages need OCR."
                    )
                # Page rendering replaces separate embedded-image blocks, but keep
                # the prior strict validation of directly displayed raster resources.
                # A corrupt resource must not disappear inside an otherwise successful
                # page render without refusing the document.
                images = page.images
                for key in images.keys():
                    if not isinstance(key, str):
                        continue
                    extracted = images[key]
                    if extracted.is_displayed and extracted.image is None:
                        raise PdfInputError(
                            f"{doc_id}: PDF page {number} has an unreadable image."
                        )
                page_texts.append(text)

        try:
            page_renders = render_pdf_pages(file_path, expected_pages=len(page_texts))
        except RenderError as exc:
            raise PdfInputError(
                f"{doc_id}: PDF page rendering failed and no complete visual parse can be returned."
            ) from exc

        blocks: list[ContentBlock] = []
        published_image_bytes = 0
        for number, text in enumerate(page_texts, 1):
            warnings = ["pdf_text_layout"]
            blocks.append(ContentBlock(
                id=f"{doc_id}/b-{number:04d}", doc_id=doc_id, ordinal=len(blocks) + 1,
                block_type="paragraph", content=text, heading_stack=[],
                structural_meta={"page": number, "extraction_warnings": warnings.copy()},
                style_hint={"parser": "pdf_text"},
            ))
            asset = image_asset_from_bytes(
                page_renders[number],
                "application/pdf",
                data_media_type="image/png",
            )
            if asset is None:
                raise PdfInputError(
                    f"{doc_id}: PDF page {number} produced an unreadable rendered image."
                )
            published_image_bytes += image_asset_byte_size(asset)
            if published_image_bytes > rasterizer.MAX_RENDERED_BYTES:
                raise PdfInputError(
                    f"{doc_id}: PDF rendering exceeds the aggregate encoded-image limit."
                )
            blocks.append(ContentBlock(
                id=f"{doc_id}/b-{number:04d}-image-0001",
                doc_id=doc_id, ordinal=len(blocks) + 1,
                block_type="image", content="[image]", heading_stack=[],
                structural_meta={
                    "page": number,
                    "visual_scope": "full_page",
                    "extraction_warnings": warnings.copy(),
                },
                style_hint={"parser": "pdf_page_render"}, image=asset,
            ))
        return blocks
    except PdfInputError:
        raise
    except Exception as exc:  # noqa: BLE001 - decoder failures reject the whole input
        raise PdfInputError(
            f"{doc_id}: not a readable PDF. Upload a fresh, unlocked export."
        ) from exc
