"""Rasterize document visuals through the optional office boundary.

This is the only optional system-binary boundary in Chunker. It is invoked only
for formats that cannot be carried directly as a browser/model image.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERT_TIMEOUT_SECONDS = 60
PRESENTATION_TIMEOUT_SECONDS = 120
PDF_RENDER_SCALE = 1.5
MAX_RENDER_PAGES = 200
MAX_RENDER_PIXELS_PER_PAGE = 20_000_000
MAX_RENDERED_BYTES = 100 * 1024 * 1024
SUFFIX_BY_MEDIA_TYPE = {
    "image/x-emf": ".emf",
    "image/emf": ".emf",
    "image/x-wmf": ".wmf",
    "image/wmf": ".wmf",
    "image/svg+xml": ".svg",
}

_soffice_lookup: str | None | bool = False
_pdfium_lock = threading.Lock()


class RenderError(RuntimeError):
    """A visual source could not be rendered under the bounded contract."""


class RendererUnavailableError(RenderError):
    """A required local renderer is not installed."""


class RenderFailedError(RenderError):
    """An available renderer did not produce complete usable output."""


class RenderLimitError(RenderFailedError):
    """Rendering would exceed a declared resource bound."""


def _soffice_path() -> str | None:
    global _soffice_lookup
    if _soffice_lookup is False:
        _soffice_lookup = shutil.which("soffice") or shutil.which("libreoffice") or None
    return _soffice_lookup  # type: ignore[return-value]


def rasterize_to_png(data: bytes, media_type: str) -> bytes | None:
    """Return PNG bytes for a supported vector format, or ``None`` on failure."""
    suffix = SUFFIX_BY_MEDIA_TYPE.get(media_type.lower())
    soffice = _soffice_path()
    if not data or not suffix or not soffice:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="pdis-image-") as directory:
            source = os.path.join(directory, f"image{suffix}")
            with open(source, "wb") as handle:
                handle.write(data)
            profile = f"file://{os.path.join(directory, 'profile')}"
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "png",
                    "--outdir",
                    directory,
                    source,
                ],
                check=True,
                timeout=CONVERT_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            output = os.path.join(directory, "image.png")
            if not os.path.exists(output):
                return None
            with open(output, "rb") as handle:
                return handle.read()
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("Image rasterization failed: %s", exc)
        return None


def render_pdf_pages(
    file_path: str, *, expected_pages: int | None = None
) -> dict[int, bytes]:
    """Render every PDF page to PNG under fixed page, pixel, and output bounds.

    PDFium calls are globally serialized. Its public Python bindings do not promise
    that independent documents may be rendered concurrently, while Chunker fans out
    document parsing across threads.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RendererUnavailableError("pypdfium2 is unavailable") from exc

    try:
        with _pdfium_lock:
            document = pdfium.PdfDocument(file_path)
            try:
                page_count = len(document)
                if page_count <= 0:
                    raise RenderFailedError("PDF renderer found no pages")
                if page_count > MAX_RENDER_PAGES:
                    raise RenderLimitError(
                        f"PDF rendering exceeds the {MAX_RENDER_PAGES}-page limit"
                    )
                if expected_pages is not None and page_count != expected_pages:
                    raise RenderFailedError(
                        f"PDF renderer produced {page_count} pages; expected {expected_pages}"
                    )
                rendered: dict[int, bytes] = {}
                encoded_bytes = 0
                for page_index in range(page_count):
                    page = document[page_index]
                    try:
                        width = float(page.get_width())
                        height = float(page.get_height())
                        if (
                            not math.isfinite(width)
                            or not math.isfinite(height)
                            or width <= 0
                            or height <= 0
                        ):
                            raise RenderFailedError(
                                f"PDF page {page_index + 1} has invalid dimensions"
                            )
                        pixel_width = math.ceil(width * PDF_RENDER_SCALE)
                        pixel_height = math.ceil(height * PDF_RENDER_SCALE)
                        if pixel_width * pixel_height > MAX_RENDER_PIXELS_PER_PAGE:
                            raise RenderLimitError(
                                f"PDF page {page_index + 1} exceeds the per-page pixel limit"
                            )
                        bitmap = page.render(scale=PDF_RENDER_SCALE)
                        try:
                            image = bitmap.to_pil()
                            try:
                                if image.width <= 0 or image.height <= 0:
                                    raise RenderFailedError(
                                        f"PDF page {page_index + 1} rendered with invalid dimensions"
                                    )
                                if image.width * image.height > MAX_RENDER_PIXELS_PER_PAGE:
                                    raise RenderLimitError(
                                        f"PDF page {page_index + 1} exceeds the per-page pixel limit"
                                    )
                                output = BytesIO()
                                image.save(output, format="PNG", optimize=True)
                                payload = output.getvalue()
                            finally:
                                image.close()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()

                    if not payload:
                        raise RenderFailedError(
                            f"PDF page {page_index + 1} rendered no image bytes"
                        )
                    encoded_bytes += len(payload)
                    if encoded_bytes > MAX_RENDERED_BYTES:
                        raise RenderLimitError(
                            "PDF rendering exceeds the aggregate encoded-image limit"
                        )
                    rendered[page_index + 1] = payload
                return rendered
            finally:
                document.close()
    except RenderError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize PDFium failures
        raise RenderFailedError(f"PDF rendering failed: {exc}") from exc


def render_presentation_slides(
    file_path: str, *, expected_pages: int | None = None
) -> dict[int, bytes]:
    """Render a PPTX into one PNG per slide, keyed by one-based slide number.

    Typed failures let callers distinguish missing runtime support from a failed
    or incomplete conversion and choose an explicit degraded fallback.
    """
    soffice = _soffice_path()
    if not soffice:
        raise RendererUnavailableError("LibreOffice is unavailable")

    try:
        with tempfile.TemporaryDirectory(prefix="pdis-pptx-") as directory:
            profile = f"file://{os.path.join(directory, 'profile')}"
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    directory,
                    file_path,
                ],
                check=True,
                timeout=PRESENTATION_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            pdf_path = os.path.join(
                directory, f"{Path(file_path).stem}.pdf"
            )
            if not os.path.exists(pdf_path):
                raise RenderFailedError("LibreOffice produced no PDF output")
            return render_pdf_pages(pdf_path, expected_pages=expected_pages)
    except RenderError:
        raise
    except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
        raise RenderFailedError(f"Presentation rendering failed: {exc}") from exc
