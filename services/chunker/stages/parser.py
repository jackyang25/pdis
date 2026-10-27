from __future__ import annotations

import tempfile
from pathlib import Path

from ..formats import DOCUMENT_SUFFIXES, SOURCE_FORMAT_BY_SUFFIX
from ..models import ContentBlock
from .parser_docx import parse_docx
from .parser_pdf import parse_pdf
from .parser_pptx import parse_pptx
from .parser_xlsx import WorkbookInputError, parse_xlsx
from .rasterizer import RenderError, convert_workbook_to_xlsx

_PARSERS = {".docx": parse_docx, ".pptx": parse_pptx, ".xlsx": parse_xlsx, ".pdf": parse_pdf}


def parse_document(file_path: str, doc_id: str) -> list[ContentBlock]:
    """Parse a document into an ordered list of ContentBlocks.

    Dispatches by file extension to the one reader for that format; every tool reads
    files through here, so a passage has one shape wherever it is read.

        .docx  -> parser_docx.parse_docx (semantic-tag-driven)
        .pptx  -> parser_pptx.parse_pptx (slide text, tables, and visuals)
        .xlsx  -> parser_xlsx.parse_xlsx (sheet regions, rows with their headers)
        .xls   -> converted to XLSX by LibreOffice, then parser_xlsx
        .pdf   -> parser_pdf.parse_pdf (page text and page renders, marked as such)

    Raises ValueError if the format is not supported or the file is unreadable.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in DOCUMENT_SUFFIXES:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported: {', '.join(sorted(DOCUMENT_SUFFIXES))}"
        )
    if suffix == ".xls":
        blocks = _parse_legacy_workbook(file_path, doc_id)
    else:
        blocks = _PARSERS[suffix](file_path, doc_id)
    # Stamped here, once, from the extension the dispatch chose by, so no parser can
    # forget it and no reader has to infer it from a page or slide field.
    source_format = SOURCE_FORMAT_BY_SUFFIX[suffix]
    for block in blocks:
        block.source_format = source_format
    return blocks


def _parse_legacy_workbook(file_path: str, doc_id: str) -> list[ContentBlock]:
    with tempfile.TemporaryDirectory(prefix="pdis-xls-") as directory:
        try:
            converted = convert_workbook_to_xlsx(file_path, directory)
        except RenderError as exc:
            raise WorkbookInputError(
                f"{doc_id}: the .xls workbook could not be converted. Save it as .xlsx and upload again."
            ) from exc
        return parse_xlsx(converted, doc_id)
