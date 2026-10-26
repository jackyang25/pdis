"""One layout for every result exported to Word.

A reader who has opened one PDIS export can read the next: the same heading, a line naming
what the result is about, what the tool did, the caveat every AI reading carries, a summary
of the counts, then tables with a bold header row in small type on a landscape page, where
five columns of prose fit. What goes in the rows is each tool's, decided in its own
`export.py` in the order and words its page uses; how they look is decided here, once.

A Word file is the result flattened, so it keeps what survives flattening: the finding, its
status and where it was read from, named as a reader would find it in the source. Links
into the app's own views do not survive and are not imitated.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Pt

#: The caveat the app prints on every result, in the same words.
CAVEAT = (
    "AI-generated results may contain errors or unsupported claims. Verify findings against "
    "the cited sources and original documents before making decisions."
)
CELL_POINTS = 9
#: A cell with nothing to say, so an empty cell is never mistaken for a lost value.
NONE = "—"


@dataclass(frozen=True)
class Table:
    columns: tuple[str, ...]
    rows: Sequence[tuple[str, ...]]
    heading: str = ""
    #: One line under the heading: what the table holds, or its counts.
    note: str = ""
    #: Each column's share of the page width, so a status column does not take a prose
    #: column's room. Equal when not given.
    widths: tuple[float, ...] = ()


@dataclass(frozen=True)
class WordReport:
    title: str
    #: What the result is about: the disease, the product type, the documents.
    context: str
    #: What the tool did, in one or two sentences.
    about: str
    tables: Sequence[Table]
    summary: str = ""
    #: Facts beside the tables, such as a review that was not run, one line each.
    notes: Sequence[str] = field(default_factory=tuple)


def word_document(report: WordReport) -> bytes:
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    document.add_heading(report.title, level=1)
    for line in (report.context, report.about, CAVEAT, report.summary, *report.notes):
        if line:
            document.add_paragraph(line)
    for table in report.tables:
        if table.heading:
            document.add_heading(table.heading, level=2)
        if table.note:
            document.add_paragraph(table.note)
        # A table with no rows is its note alone: a header row over nothing reads as lost rows.
        if table.rows:
            _table(document, table, section.page_width - section.left_margin - section.right_margin)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _table(document: Any, table: Table, width: int) -> None:
    grid = document.add_table(rows=1, cols=len(table.columns))
    grid.style = "Table Grid"
    shares = table.widths or (1.0,) * len(table.columns)
    if len(shares) != len(table.columns):
        raise ValueError("a table gives one width per column")
    grid.autofit = False
    for cell, heading in zip(grid.rows[0].cells, table.columns, strict=True):
        cell.text = heading
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(CELL_POINTS)
    for row in table.rows:
        for cell, text in zip(grid.add_row().cells, row, strict=True):
            cell.text = text or NONE
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(CELL_POINTS)
    # Set on the table's column grid and on every cell of the column: Word reads the cells,
    # other readers the grid.
    for index, column in enumerate(grid.columns):
        column_width = int(width * shares[index] / sum(shares))
        column.width = column_width
        for cell in column.cells:
            cell.width = column_width


def count_summary(total: int, noun: tuple[str, str], parts: Iterable[tuple[int, str]]) -> str:
    """"49 questions: 27 answered, 14 partly answered, 8 not found." Zero parts stay: a zero a
    run produced says the check ran and found none."""
    # Lower case inside a sentence, except a label that is all capitals, such as "N/A".
    counted = ", ".join(f"{count} {label if label.isupper() else label.lower()}" for count, label in parts)
    return f"{total} {noun[0] if total == 1 else noun[1]}: {counted}."


def document_name(doc_id: str) -> str:
    """A document as the app names it: its file name with separators read as spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", doc_id)).strip() or "Source document"


_PARTS = {"header": "Header", "footer": "Footer", "footnote": "Footnote", "endnote": "Endnote", "textbox": "Text box"}


def passage_location(block: Mapping[str, Any]) -> str:
    """Where a passage sits, as the app's passage lists name it: "Page 4", "Slide 3", a
    footnote, or its section heading."""
    meta = block.get("structural_meta") or {}
    # The web's `documentBlockBoundary`: one positive whole page or slide, never both.
    page, slide = (value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
                   for value in (meta.get("page"), meta.get("slide")))
    if (page is None) != (slide is None):
        return f"Page {page}" if page is not None else f"Slide {slide}"
    part = _PARTS.get(str(meta.get("document_part_kind") or ""))
    if part:
        note = meta.get("note_id")
        return f"{part} {note}" if part in {"Footnote", "Endnote"} and note not in (None, "") else part
    headings = block.get("heading_stack") or []
    return str(block.get("section_label") or (headings[-1] if headings else ""))


def passage_sources(
    block_ids: Iterable[str],
    blocks_by_id: Mapping[str, Mapping[str, Any]],
    *,
    name_documents: bool,
) -> str:
    """Each cited passage on its own line, with its document when a result reads several.

    A passage the saved result no longer holds is named as unavailable rather than dropped:
    the citation was made, and the line says it cannot be followed.
    """
    lines: list[str] = []
    for block_id in block_ids:
        block = blocks_by_id.get(block_id)
        if block is None:
            lines.append("Passage not in the saved result")
            continue
        location = passage_location(block)
        name = document_name(str(block.get("doc_id") or "")) if name_documents else ""
        lines.append(" · ".join(part for part in (name, location) if part) or "Passage without a heading")
    return "\n".join(dict.fromkeys(lines))
