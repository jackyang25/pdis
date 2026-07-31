from __future__ import annotations

from pathlib import Path

from ..models import ContentBlock
from .parser_docx import parse_docx
from .parser_pptx import parse_pptx


def parse_document(file_path: str, doc_id: str) -> list[ContentBlock]:
    """
    Parse a document into an ordered list of ContentBlocks.

    Dispatches by file extension to a format-specific parser. The output
    shape is uniform across formats; downstream consumers (mapper,
    evidence, Inspector) read ContentBlocks without caring about source
    format.

    A supported format declares its own structure, so tables, rows, headings,
    and reading order are read from the file rather than inferred from where
    glyphs landed on a page. Rendering formats are refused here: reconstructing
    a table from geometry can merge unrelated columns into one block whose text
    still satisfies exact-quote validation, which is a provenance error no
    downstream check can detect.

    Supported formats:
        .docx  -> parser_docx.parse_docx (semantic-tag-driven)
        .pptx  -> parser_pptx.parse_pptx (slide text, tables, and visuals)

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
    if suffix == ".pptx":
        return parse_pptx(file_path, doc_id)
    raise ValueError(
        f"Unsupported file format '{suffix}'. Supported: .docx, .pptx"
    )
