"""Rasterize document visuals through the optional office boundary.

This is the only optional system-binary boundary in Chunker. It is invoked only
for formats that cannot be carried directly as a browser/model image.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERT_TIMEOUT_SECONDS = 60
PRESENTATION_TIMEOUT_SECONDS = 120
SUFFIX_BY_MEDIA_TYPE = {
    "image/x-emf": ".emf",
    "image/emf": ".emf",
    "image/x-wmf": ".wmf",
    "image/wmf": ".wmf",
    "image/svg+xml": ".svg",
}

_soffice_lookup: str | None | bool = False


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


def render_presentation_slides(file_path: str) -> dict[int, bytes]:
    """Render a PPTX into one PNG per slide, keyed by one-based slide number.

    Rendering is best-effort. Text and table parsing remains available without
    LibreOffice or PDFium; callers can retain embedded pictures as a fallback.
    """
    soffice = _soffice_path()
    if not soffice:
        logger.info("Presentation rendering skipped: LibreOffice is unavailable")
        return {}
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("Presentation rendering skipped: pypdfium2 is unavailable")
        return {}

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
                return {}

            document = pdfium.PdfDocument(pdf_path)
            rendered: dict[int, bytes] = {}
            try:
                for page_index in range(len(document)):
                    page = document[page_index]
                    try:
                        bitmap = page.render(scale=1.5)
                        try:
                            image = bitmap.to_pil()
                            output = BytesIO()
                            image.save(output, format="PNG", optimize=True)
                            rendered[page_index + 1] = output.getvalue()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
            finally:
                document.close()
            return rendered
    except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
        logger.warning("Presentation rendering failed: %s", exc)
        return {}
