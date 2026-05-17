from __future__ import annotations

from pathlib import Path

from ..models import ContentBlock
from .parser_docx import parse_docx
from .parser_pdf import parse_pdf


def parse_document(file_path: str, doc_id: str) -> list[ContentBlock]:
    """
    Parse a document into an ordered list of ContentBlocks.

    Dispatches by file extension to a format-specific parser. The output
    shape is uniform across formats; downstream consumers (mapper,
    evidence, pd_reviewer) read ContentBlocks without caring about source
    format.

    Supported formats:
        .docx  -> parser_docx.parse_docx (semantic-tag-driven)
        .pdf   -> parser_pdf.parse_pdf   (text + table extraction via pdfplumber)

    Args:
        file_path: Path to the source file.
        doc_id: Identifier for this document (used in block IDs).

    Returns:
        List of ContentBlock objects in document order.

    Raises:
        ValueError: if the file extension is not supported.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix == ".docx":
        return parse_docx(file_path, doc_id)
    if suffix == ".pdf":
        return parse_pdf(file_path, doc_id)
    raise ValueError(
        f"Unsupported file format '{suffix}'. Supported: .docx, .pdf"
    )
