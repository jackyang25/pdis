"""Rasterize unsupported document image formats through headless LibreOffice.

This is the only optional system-binary boundary in Chunker. It is invoked only
for formats that cannot be carried directly as a browser/model image.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

CONVERT_TIMEOUT_SECONDS = 60
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
