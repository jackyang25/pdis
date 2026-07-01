"""EMF/WMF (Windows vector metafile) -> PNG, via headless LibreOffice.

Isolated and best-effort. The rest of the chunker deals only in image bytes;
this module is the one place that knows how a vector figure becomes a raster
the vision model can read. It has no dependency on ContentBlock, the pipeline,
or the describer - just `bytes -> bytes | None`.

Design:
- Spawned on demand (only when there's a vector image to convert), never a
  persistent process. Zero footprint when idle.
- Self-gating: if LibreOffice isn't installed, or the conversion fails/times
  out, returns None. The caller falls back to a placeholder; a run never breaks.
  So this is inert on a machine without LibreOffice and only does work where the
  binary is present (e.g. the Docker deploy).
- Garbage-safe: input, output, and LibreOffice's own user profile all live in a
  TemporaryDirectory that is removed on exit, even on exception. Each call gets
  its own temp dir + profile, so concurrent conversions don't collide.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

CONVERT_TIMEOUT_SECONDS = 60
VECTOR_CONTENT_TYPES = {"image/x-emf", "image/emf", "image/x-wmf", "image/wmf"}

_soffice_lookup: str | None | bool = False  # False = not yet looked up


def _soffice_path() -> str | None:
    """Cached path to the LibreOffice CLI, or None if it isn't installed."""
    global _soffice_lookup
    if _soffice_lookup is False:
        _soffice_lookup = shutil.which("soffice") or shutil.which("libreoffice") or None
    return _soffice_lookup  # type: ignore[return-value]


def is_available() -> bool:
    """True if LibreOffice is installed and conversion can be attempted."""
    return _soffice_path() is not None


def convert_to_png(data: bytes, content_type: str) -> bytes | None:
    """Rasterize one EMF/WMF blob to PNG bytes. Returns None on any problem
    (not a vector type, LibreOffice missing, timeout, empty/bad input) - never
    raises, so the caller can fall back cleanly.
    """
    if not data or content_type.lower() not in VECTOR_CONTENT_TYPES:
        return None
    soffice = _soffice_path()
    if not soffice:
        return None

    suffix = ".wmf" if "wmf" in content_type.lower() else ".emf"
    try:
        with tempfile.TemporaryDirectory(prefix="pdis-emf-") as tmp:
            src = os.path.join(tmp, f"image{suffix}")
            with open(src, "wb") as handle:
                handle.write(data)
            # Per-call user profile inside the temp dir: avoids the shared-profile
            # lock that breaks concurrent headless invocations, and is cleaned up
            # with the temp dir.
            profile = f"file://{os.path.join(tmp, 'profile')}"
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "png",
                    "--outdir",
                    tmp,
                    src,
                ],
                check=True,
                timeout=CONVERT_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            out = os.path.join(tmp, "image.png")
            if not os.path.exists(out):
                return None
            with open(out, "rb") as handle:
                return handle.read()
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("EMF/WMF -> PNG conversion failed: %s", exc)
        return None
