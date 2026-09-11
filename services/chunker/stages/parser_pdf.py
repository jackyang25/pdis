"""PDF text and embedded rasters → canonical blocks, without inferred structure.

Page boundaries are declared by PDF; headings, tables and reading order are not.
Never turn layout guesses into structural metadata or exact-quote guarantees.
"""

from pathlib import Path
from contextlib import contextmanager
import logging
import threading
from PIL import Image

from pypdf import PdfReader

from ..models import ContentBlock
from .image_assets import image_asset_from_bytes

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
            blocks = []
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
                blocks.append(ContentBlock(
                    id=f"{doc_id}/b-{number:04d}", doc_id=doc_id, ordinal=len(blocks) + 1,
                    block_type="paragraph", content=text, heading_stack=[],
                    structural_meta={
                        "page": number,
                        "extraction_warnings": ["pdf_limited_structure"],
                    },
                    style_hint={"parser": "pdf_text"},
                ))
                # pypdf owns inline/XObject decoding and masks. Resource
                # order is not reading order: keep page text first, then its images.
                # No placement guesses, chart reconstruction, or page rendering.
                images = page.images
                for index, key in enumerate(images.keys(), 1):
                    # Nested Form placement is outside this narrow extraction
                    # contract. pypdf's display flag is page-local, not recursive.
                    if not isinstance(key, str):
                        continue
                    extracted = images[key]
                    if not extracted.is_displayed:
                        continue
                    if extracted.image is None:
                        raise PdfInputError(f"{doc_id}: PDF page {number} has an unreadable image.")
                    media_type = Image.MIME.get(extracted.image.format, "application/octet-stream")
                    asset = image_asset_from_bytes(extracted.data, media_type)
                    if asset is None:
                        raise PdfInputError(f"{doc_id}: PDF page {number} has an unreadable image.")
                    blocks.append(ContentBlock(
                        id=f"{doc_id}/b-{number:04d}-image-{index:04d}",
                        doc_id=doc_id, ordinal=len(blocks) + 1,
                        block_type="image", content="[image]", heading_stack=[],
                        structural_meta={
                            "page": number,
                            "extraction_warnings": ["pdf_limited_structure"],
                        },
                        style_hint={"parser": "pdf_image"}, image=asset,
                    ))
            return blocks
    except PdfInputError:
        raise
    except Exception as exc:  # noqa: BLE001 - decoder failures reject the whole input
        raise PdfInputError(
            f"{doc_id}: not a readable PDF. Upload a fresh, unlocked export."
        ) from exc
