"""Rasterize document visuals, and convert legacy Office files, through the office boundary.

This is the only optional system-binary boundary in Chunker. It is invoked only for
formats that cannot be carried directly as a browser/model image, and for `.doc`, `.ppt`
and `.xls` files, which are converted to their modern format before reading.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

# One LibreOffice start converts every vector image of a document, so the bound is
# per batch rather than per image.
CONVERT_TIMEOUT_SECONDS = 120
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

# LibreOffice's PDF export omits hidden slides unless told otherwise (JSON filter
# options, LibreOffice 7.4+).
PRESENTATION_PDF_TARGET = (
    'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
)

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


def _run_office(arguments: list[str], *, timeout: int) -> None:
    """Run LibreOffice in its own process group and kill the whole group on timeout.

    `soffice` is a launcher that starts `soffice.bin`; killing only the launcher, as
    `subprocess.run(timeout=...)` does, leaves the converter running with its profile
    and temporary directory in use.
    """
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, arguments)


def rasterize_many_to_png(items: list[tuple[bytes, str]]) -> list[bytes | None]:
    """Convert vector images to PNG with one LibreOffice start, in input order.

    Each result is ``None`` when its format is unsupported or its conversion
    produced nothing; a failed or timed-out batch returns ``None`` for every item.
    Callers deduplicate identical bytes before calling, so a repeated logo is
    converted once.
    """
    results: list[bytes | None] = [None] * len(items)
    soffice = _soffice_path()
    pending = [
        (index, data, SUFFIX_BY_MEDIA_TYPE.get((media_type or "").lower()))
        for index, (data, media_type) in enumerate(items)
    ]
    pending = [(index, data, suffix) for index, data, suffix in pending if data and suffix]
    if not pending or not soffice:
        return results
    try:
        with tempfile.TemporaryDirectory(prefix="pdis-image-") as directory:
            sources = []
            for index, data, suffix in pending:
                source = os.path.join(directory, f"image-{index}{suffix}")
                with open(source, "wb") as handle:
                    handle.write(data)
                sources.append(source)
            profile = f"file://{os.path.join(directory, 'profile')}"
            _run_office(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "png",
                    "--outdir",
                    directory,
                    *sources,
                ],
                timeout=CONVERT_TIMEOUT_SECONDS,
            )
            for index, _, _ in pending:
                output = os.path.join(directory, f"image-{index}.png")
                if os.path.exists(output):
                    with open(output, "rb") as handle:
                        results[index] = handle.read() or None
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("Image rasterization failed: %s", exc)
        return [None] * len(items)
    return results


def render_pdf_pages(
    file_path: str, *, expected_pages: int | None = None
) -> dict[int, bytes]:
    """Render every PDF page to PNG under fixed page, pixel, and output bounds.

    PDFium calls are globally serialized. Its public Python bindings do not promise
    that independent documents may be rendered concurrently, while Chunker fans out
    document parsing across threads. Only PDFium work holds the lock: each page is
    copied out of its bitmap under it, and PNG encoding happens outside it, so one
    document's encoding does not stall another's rendering.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RendererUnavailableError("pypdfium2 is unavailable") from exc

    try:
        with _pdfium_lock:
            document = pdfium.PdfDocument(file_path)
            page_count = len(document)
        try:
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
                with _pdfium_lock:
                    image = _render_page_image(document, page_index)
                try:
                    output = BytesIO()
                    image.save(output, format="PNG")
                    payload = output.getvalue()
                finally:
                    image.close()

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
            with _pdfium_lock:
                document.close()
    except RenderError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize PDFium failures
        raise RenderFailedError(f"PDF rendering failed: {exc}") from exc


def _render_page_image(document, page_index: int):
    """Render one page to an independent PIL image; the caller holds the lock."""
    page = document[page_index]
    try:
        width = float(page.get_width())
        height = float(page.get_height())
        if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
            raise RenderFailedError(f"PDF page {page_index + 1} has invalid dimensions")
        pixel_width = math.ceil(width * PDF_RENDER_SCALE)
        pixel_height = math.ceil(height * PDF_RENDER_SCALE)
        if pixel_width * pixel_height > MAX_RENDER_PIXELS_PER_PAGE:
            raise RenderLimitError(
                f"PDF page {page_index + 1} exceeds the per-page pixel limit"
            )
        bitmap = page.render(scale=PDF_RENDER_SCALE)
        try:
            # `to_pil` shares the bitmap's buffer, so copy before the bitmap closes.
            shared = bitmap.to_pil()
            try:
                if shared.width <= 0 or shared.height <= 0:
                    raise RenderFailedError(
                        f"PDF page {page_index + 1} rendered with invalid dimensions"
                    )
                if shared.width * shared.height > MAX_RENDER_PIXELS_PER_PAGE:
                    raise RenderLimitError(
                        f"PDF page {page_index + 1} exceeds the per-page pixel limit"
                    )
                return shared.copy()
            finally:
                shared.close()
        finally:
            bitmap.close()
    finally:
        page.close()


def convert_legacy_document(file_path: str, directory: str, target: str) -> str:
    """Convert a legacy Office file (`.doc`, `.ppt`, `.xls`) to `target` in `directory`.

    Returns the converted file's path. The file is then read by the one reader for its
    modern format, so a legacy file yields the same passages a current one does. Typed
    failures, as for slide rendering.
    """
    soffice = _soffice_path()
    if not soffice:
        raise RendererUnavailableError("LibreOffice is unavailable")
    profile = f"file://{os.path.join(directory, 'profile')}"
    extension = target.removeprefix(".")
    try:
        _run_office(
            [soffice, f"-env:UserInstallation={profile}", "--headless",
             "--convert-to", extension, "--outdir", directory, file_path],
            timeout=CONVERT_TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RenderFailedError(f"Document conversion failed: {exc}") from exc
    converted = os.path.join(directory, f"{Path(file_path).stem}{target}")
    if not os.path.exists(converted):
        raise RenderFailedError(f"LibreOffice produced no {extension.upper()} output")
    return converted


def render_presentation_slides(
    file_path: str, *, expected_pages: int | None = None
) -> dict[int, bytes]:
    """Render a PPTX into one PNG per slide, keyed by one-based slide number.

    Hidden slides are rendered too: they are part of the document the parser reads,
    and LibreOffice's default export skips them, which would leave fewer pages than
    slides and lose every slide's render.

    Typed failures let callers distinguish missing runtime support from a failed
    or incomplete conversion and choose an explicit degraded fallback.
    """
    soffice = _soffice_path()
    if not soffice:
        raise RendererUnavailableError("LibreOffice is unavailable")

    try:
        with tempfile.TemporaryDirectory(prefix="pdis-pptx-") as directory:
            profile = f"file://{os.path.join(directory, 'profile')}"
            _run_office(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    PRESENTATION_PDF_TARGET,
                    "--outdir",
                    directory,
                    file_path,
                ],
                timeout=PRESENTATION_TIMEOUT_SECONDS,
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
