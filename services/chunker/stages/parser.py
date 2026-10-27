from __future__ import annotations

import tempfile
from pathlib import Path

from ..formats import DOCUMENT_SUFFIXES, LEGACY_SUFFIXES, SOURCE_FORMAT_BY_SUFFIX
from ..models import ContentBlock
from .image_assets import attach_image_assets
from .parser_docx import parse_docx
from .parser_pdf import parse_pdf
from .parser_pptx import parse_pptx
from .parser_xlsx import parse_xlsx
from .rasterizer import RenderError, convert_legacy_document

_PARSERS = {".docx": parse_docx, ".pptx": parse_pptx, ".xlsx": parse_xlsx, ".pdf": parse_pdf}


def parse_document(file_path: str, doc_id: str) -> list[ContentBlock]:
    """Parse a document into an ordered list of ContentBlocks, its images attached.

    Dispatches by file extension to the one reader for that format; every tool reads
    files through here, so a passage has one shape wherever it is read.

        .docx  -> parser_docx.parse_docx (semantic-tag-driven)
        .pptx  -> parser_pptx.parse_pptx (slide text, tables, and visuals)
        .xlsx  -> parser_xlsx.parse_xlsx (sheet regions, rows with their headers)
        .pdf   -> parser_pdf.parse_pdf (page text and page renders, marked as such)
        .doc / .ppt / .xls -> converted by LibreOffice to their modern format, then read
                  by that format's reader

    Raises ValueError if the format is not supported or the file is unreadable.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in DOCUMENT_SUFFIXES:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported: {', '.join(sorted(DOCUMENT_SUFFIXES))}"
        )
    if suffix in LEGACY_SUFFIXES:
        blocks = _read_legacy(file_path, doc_id, LEGACY_SUFFIXES[suffix])
    else:
        blocks = _read(file_path, doc_id)
    # Stamped here, once, from the extension of the file that was uploaded, so no parser
    # can forget it and a converted file still names the format it arrived in.
    source_format = SOURCE_FORMAT_BY_SUFFIX[suffix]
    for block in blocks:
        block.source_format = source_format
    return blocks


def _read(file_path: str, doc_id: str) -> list[ContentBlock]:
    """One modern-format file through its reader, images resolved from that same file."""
    reader = _PARSERS[Path(file_path).suffix.lower()]
    return attach_image_assets(reader(file_path, doc_id), file_path)


def _read_legacy(file_path: str, doc_id: str, target: str) -> list[ContentBlock]:
    with tempfile.TemporaryDirectory(prefix="pdis-legacy-") as directory:
        try:
            converted = convert_legacy_document(file_path, directory, target)
        except RenderError as exc:
            suffix = Path(file_path).suffix.lower()
            raise ValueError(
                f"{doc_id}: the {suffix} file could not be converted. "
                f"Save it as {target} and upload again."
            ) from exc
        # Read inside the directory: a deck's slides render from the converted file.
        return _read(converted, doc_id)
