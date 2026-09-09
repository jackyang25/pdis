from __future__ import annotations

from pathlib import Path
from collections.abc import Set

from ..formats import DOCUMENT_SUFFIXES
from ..models import ContentBlock
from .parser_docx import parse_docx
from .parser_pptx import parse_pptx
from .parser_pdf import parse_pdf


def parse_document(
    file_path: str, doc_id: str, *, accepted_suffixes: Set[str] = DOCUMENT_SUFFIXES,
) -> list[ContentBlock]:
    """
    Parse a document into an ordered list of ContentBlocks.

    Dispatches by file extension to a format-specific parser. The output
    shape is uniform across formats; downstream consumers (mapper,
    evidence, Inspector) read ContentBlocks without caring about source
    format.

    Defaults require declared structure. Callers may explicitly opt into PDF
    text extraction, which produces page-level passages with limitations in
    metadata, never inferred table cells or headings.

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
    if suffix not in accepted_suffixes:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported: {', '.join(sorted(accepted_suffixes))}"
        )
    if suffix == ".docx":
        return parse_docx(file_path, doc_id)
    if suffix == ".pptx":
        return parse_pptx(file_path, doc_id)
    if suffix == ".pdf":
        return parse_pdf(file_path, doc_id)
    raise ValueError(
        f"Unsupported file format '{suffix}': no parser is registered."
    )
