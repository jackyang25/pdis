from __future__ import annotations

import os
import re
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..models import ContentBlock


def parse_docx(file_path: str, doc_id: str) -> list[ContentBlock]:
    """
    Parse a .docx file into an ordered list of ContentBlocks.

    Args:
        file_path: Path to the .docx file
        doc_id: Identifier for this document (used in block IDs)

    Returns:
        List of ContentBlock objects in document order
    """
    _validate_file_path(file_path)

    doc = Document(file_path)
    blocks: list[ContentBlock] = []
    heading_stack: list[tuple[int, str]] = []
    paragraph_index = 0
    table_index = 0

    for child in doc.element.body:
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, doc)
            paragraph_text = paragraph.text
            current_paragraph_index = paragraph_index
            paragraph_index += 1

            if not paragraph_text.strip():
                continue

            heading_level = _heading_level(paragraph)
            if heading_level is not None:
                heading_stack = [
                    (level, text)
                    for level, text in heading_stack
                    if level < heading_level
                ]
                heading_stack.append((heading_level, paragraph_text))
                blocks.append(
                    _make_block(
                        doc_id=doc_id,
                        block_type="heading",
                        content=paragraph_text,
                        heading_stack=_stack_text(heading_stack),
                        structural_meta={
                            "paragraph_index": current_paragraph_index,
                            "heading_level": heading_level,
                        },
                        style_hint=_paragraph_style_hint(paragraph),
                    )
                )
                continue

            blocks.append(
                _make_block(
                    doc_id=doc_id,
                    block_type="paragraph",
                    content=paragraph_text,
                    heading_stack=_stack_text(heading_stack),
                    structural_meta={"paragraph_index": current_paragraph_index},
                    style_hint=_paragraph_style_hint(paragraph),
                )
            )

        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            blocks.extend(_parse_table(table, doc_id, table_index, heading_stack))
            table_index += 1

    for ordinal, block in enumerate(blocks):
        block.ordinal = ordinal
        block.id = f"{doc_id}/b-{ordinal:04d}"

    return blocks


def _validate_file_path(file_path: str) -> None:
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("file_path must be a non-empty string")
    if not file_path.lower().endswith(".docx"):
        raise ValueError("file_path must point to a .docx file")
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = _style_name(paragraph)
    if not style_name.startswith("Heading"):
        return None

    match = re.search(r"(\d+)$", style_name)
    if not match:
        return 1
    return int(match.group(1))


def _parse_table(
    table: Table,
    doc_id: str,
    table_index: int,
    heading_stack: list[tuple[int, str]],
) -> list[ContentBlock]:
    rows = [[_cell_text(cell) for cell in row.cells] for row in table.rows]
    if not rows:
        return []

    column_count = max((len(row) for row in rows), default=0)
    if column_count == 0:
        return []

    if len(rows) == 1 and column_count == 1:
        text = rows[0][0]
        if not text.strip():
            return []
        return [
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=text,
                heading_stack=_stack_text(heading_stack),
                structural_meta={"table_index": table_index, "row_index": 0},
                style_hint={"source": "single_cell_table"},
            )
        ]

    if column_count == 1:
        blocks: list[ContentBlock] = []
        for row_index, row in enumerate(rows):
            text = row[0] if row else ""
            if not text.strip():
                continue
            blocks.append(
                _make_block(
                    doc_id=doc_id,
                    block_type="paragraph",
                    content=text,
                    heading_stack=_stack_text(heading_stack),
                    structural_meta={
                        "table_index": table_index,
                        "row_index": row_index,
                    },
                    style_hint={"source": "single_column_table"},
                )
            )
        return blocks

    return _parse_multi_column_table(
        rows,
        doc_id,
        table_index,
        heading_stack,
        column_count,
    )


def _parse_multi_column_table(
    rows: list[list[str]],
    doc_id: str,
    table_index: int,
    heading_stack: list[tuple[int, str]],
    column_count: int,
) -> list[ContentBlock]:
    headers = _normalize_row(rows[0], column_count)
    data_rows = rows[1:]

    if not data_rows:
        content = " | ".join(header for header in headers if header.strip())
        if not content.strip():
            return []
        return [
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=content,
                heading_stack=_stack_text(heading_stack),
                structural_meta={
                    "table_index": table_index,
                    "row_index": 0,
                    "column_headers": headers,
                },
                style_hint={"source": "table_headers"},
            )
        ]

    blocks: list[ContentBlock] = []
    for row_index, row in enumerate(data_rows, start=1):
        values = _normalize_row(row, len(headers))
        if not any(value.strip() for value in values):
            continue

        content = _format_table_row(headers, values)
        if not content.strip():
            continue

        blocks.append(
            _make_block(
                doc_id=doc_id,
                block_type="table_row",
                content=content,
                heading_stack=_stack_text(heading_stack),
                structural_meta={
                    "table_index": table_index,
                    "row_index": row_index,
                    "column_headers": headers,
                },
                style_hint={"source": "table_row"},
            )
        )
    return blocks


def _format_table_row(headers: list[str], values: list[str]) -> str:
    pairs = []
    for index, value in enumerate(values):
        if not value.strip():
            continue
        header = headers[index].strip() if index < len(headers) else ""
        pairs.append(f"{header}: {value}" if header else value)
    return ", ".join(pairs)


def _normalize_row(row: list[str], width: int) -> list[str]:
    normalized = row[:width]
    if len(normalized) < width:
        normalized.extend([""] * (width - len(normalized)))
    return normalized


def _cell_text(cell: Any) -> str:
    return cell.text


def _make_block(
    *,
    doc_id: str,
    block_type: str,
    content: str,
    heading_stack: list[str],
    structural_meta: dict,
    style_hint: dict,
) -> ContentBlock:
    return ContentBlock(
        id="",
        doc_id=doc_id,
        ordinal=-1,
        block_type=block_type,
        content=content,
        heading_stack=heading_stack.copy(),
        structural_meta=structural_meta,
        style_hint=style_hint,
    )


def _paragraph_style_hint(paragraph: Paragraph) -> dict[str, str | bool]:
    return {
        "style_name": _style_name(paragraph),
        "is_bold": any(run.bold is True for run in paragraph.runs),
    }


def _style_name(paragraph: Paragraph) -> str:
    return paragraph.style.name if paragraph.style is not None else ""


def _stack_text(heading_stack: list[tuple[int, str]]) -> list[str]:
    return [text for _, text in heading_stack]
