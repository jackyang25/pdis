from __future__ import annotations

import os
from typing import Any

import pdfplumber

from ..models import ContentBlock


# Heuristic: words within this y-pixel tolerance are treated as the same line.
_LINE_TOLERANCE = 3.0

# Heuristic: a vertical gap larger than this multiple of line height starts
# a new paragraph. Tuned for typical 11–12pt body text on letter/A4 layouts.
_PARAGRAPH_GAP_RATIO = 1.6


def parse_pdf(file_path: str, doc_id: str) -> list[ContentBlock]:
    """
    Parse a .pdf file into an ordered list of ContentBlocks.

    Uses pdfplumber for text + table extraction. Each page is processed
    sequentially: tables are detected first and their regions excluded
    from paragraph extraction so words inside tables do not get duplicated
    as paragraphs.

    Args:
        file_path: Path to the .pdf file
        doc_id: Identifier for this document (used in block IDs)

    Returns:
        List of ContentBlock objects in reading order across pages.

    Notes:
        heading_stack is left empty for PDFs at MVP. PDFs lack semantic
        heading tags; recovering a hierarchy requires font-size inference
        which is deferred until needed. Section labeling still works via
        the mapper, which reads block content against an injected
        DocumentTypeConfig.
    """
    _validate_file_path(file_path)

    blocks: list[ContentBlock] = []
    paragraph_index = 0
    table_index = 0

    with pdfplumber.open(file_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            table_objects = page.find_tables()
            table_bboxes = [tuple(table.bbox) for table in table_objects]

            # Pull every word with its bounding box for paragraph reconstruction.
            words = page.extract_words(
                use_text_flow=True,
                keep_blank_chars=False,
                extra_attrs=["fontname", "size"],
            ) or []

            # Exclude words that sit inside any detected table region.
            non_table_words = [
                word for word in words if not _word_in_any_bbox(word, table_bboxes)
            ]

            # Emit paragraph blocks from non-table text.
            for paragraph_text in _group_into_paragraphs(non_table_words):
                if not paragraph_text.strip():
                    continue
                blocks.append(
                    _make_block(
                        doc_id=doc_id,
                        block_type="paragraph",
                        content=paragraph_text,
                        structural_meta={
                            "paragraph_index": paragraph_index,
                            "page": page_number,
                        },
                        style_hint={"source": "pdf_paragraph"},
                    )
                )
                paragraph_index += 1

            # Emit table blocks. We extract via pdfplumber's table API for
            # accurate row/column reconstruction.
            for table_object in table_objects:
                rows = table_object.extract()
                if not rows:
                    table_index += 1
                    continue

                blocks.extend(
                    _build_table_blocks(
                        rows=rows,
                        doc_id=doc_id,
                        table_index=table_index,
                        page_number=page_number,
                    )
                )
                table_index += 1

    for ordinal, block in enumerate(blocks):
        block.ordinal = ordinal
        block.id = f"{doc_id}/b-{ordinal:04d}"

    return blocks


def _validate_file_path(file_path: str) -> None:
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("file_path must be a non-empty string")
    if not file_path.lower().endswith(".pdf"):
        raise ValueError("file_path must point to a .pdf file")
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)


def _word_in_any_bbox(word: dict, bboxes: list[tuple]) -> bool:
    if not bboxes:
        return False
    word_x0 = float(word.get("x0", 0))
    word_top = float(word.get("top", 0))
    for x0, top, x1, bottom in bboxes:
        if x0 <= word_x0 <= x1 and top <= word_top <= bottom:
            return True
    return False


def _group_into_paragraphs(words: list[dict]) -> list[str]:
    """
    Group words into paragraphs using line + gap heuristics.

    1. Sort words by (top, x0) so reading order is top-to-bottom, left-to-right.
    2. Cluster into lines: words on the same horizontal band (within tolerance).
    3. Cluster lines into paragraphs: a vertical gap larger than
       PARAGRAPH_GAP_RATIO * median_line_height starts a new paragraph.
    """
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: (round(float(w["top"]), 1), float(w["x0"])))

    # Group into lines.
    lines: list[list[dict]] = []
    current_line: list[dict] = []
    current_top: float | None = None
    for word in sorted_words:
        top = float(word["top"])
        if current_top is None or abs(top - current_top) <= _LINE_TOLERANCE:
            current_line.append(word)
            current_top = top if current_top is None else current_top
        else:
            lines.append(current_line)
            current_line = [word]
            current_top = top
    if current_line:
        lines.append(current_line)

    if not lines:
        return []

    # Reconstruct line text by x0-sorted concatenation.
    line_records = []
    for line_words in lines:
        line_words.sort(key=lambda w: float(w["x0"]))
        text = " ".join(word["text"] for word in line_words)
        top = float(line_words[0]["top"])
        bottom = float(line_words[0].get("bottom", line_words[0]["top"]))
        height = max(bottom - top, 1.0)
        line_records.append({"text": text, "top": top, "height": height})

    # Estimate typical line height for gap thresholding.
    heights = [r["height"] for r in line_records]
    heights.sort()
    median_height = heights[len(heights) // 2] if heights else 12.0
    gap_threshold = median_height * _PARAGRAPH_GAP_RATIO

    # Group lines into paragraphs by gap.
    paragraphs: list[str] = []
    current_paragraph: list[str] = []
    previous_bottom: float | None = None
    for record in line_records:
        if previous_bottom is not None and (record["top"] - previous_bottom) > gap_threshold:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
            current_paragraph = []
        current_paragraph.append(record["text"])
        previous_bottom = record["top"] + record["height"]

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))

    return paragraphs


def _build_table_blocks(
    *,
    rows: list[list[str | None]],
    doc_id: str,
    table_index: int,
    page_number: int,
) -> list[ContentBlock]:
    cleaned_rows: list[list[str]] = [
        [(cell or "").strip() for cell in row] for row in rows
    ]
    cleaned_rows = [row for row in cleaned_rows if any(cell for cell in row)]
    if not cleaned_rows:
        return []

    column_count = max(len(row) for row in cleaned_rows)

    # Single-cell table → one paragraph block.
    if len(cleaned_rows) == 1 and column_count == 1:
        text = cleaned_rows[0][0]
        if not text:
            return []
        return [
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=text,
                structural_meta={
                    "table_index": table_index,
                    "row_index": 0,
                    "page": page_number,
                },
                style_hint={"source": "single_cell_table"},
            )
        ]

    # Single-column table → one paragraph block per non-empty row.
    if column_count == 1:
        blocks: list[ContentBlock] = []
        for row_index, row in enumerate(cleaned_rows):
            text = row[0] if row else ""
            if not text:
                continue
            blocks.append(
                _make_block(
                    doc_id=doc_id,
                    block_type="paragraph",
                    content=text,
                    structural_meta={
                        "table_index": table_index,
                        "row_index": row_index,
                        "page": page_number,
                    },
                    style_hint={"source": "single_column_table"},
                )
            )
        return blocks

    # Multi-column table → first row as headers, rest as table_row blocks.
    headers = _normalize_row(cleaned_rows[0], column_count)
    data_rows = cleaned_rows[1:]

    if not data_rows:
        content = " | ".join(header for header in headers if header)
        if not content:
            return []
        return [
            _make_block(
                doc_id=doc_id,
                block_type="paragraph",
                content=content,
                structural_meta={
                    "table_index": table_index,
                    "row_index": 0,
                    "column_headers": headers,
                    "page": page_number,
                },
                style_hint={"source": "table_headers"},
            )
        ]

    blocks = []
    for row_index, row in enumerate(data_rows, start=1):
        values = _normalize_row(row, len(headers))
        if not any(value for value in values):
            continue
        content = _format_table_row(headers, values)
        if not content:
            continue
        blocks.append(
            _make_block(
                doc_id=doc_id,
                block_type="table_row",
                content=content,
                structural_meta={
                    "table_index": table_index,
                    "row_index": row_index,
                    "column_headers": headers,
                    "page": page_number,
                },
                style_hint={"source": "table_row"},
            )
        )
    return blocks


def _format_table_row(headers: list[str], values: list[str]) -> str:
    pairs = []
    for index, value in enumerate(values):
        if not value:
            continue
        header = headers[index] if index < len(headers) else ""
        pairs.append(f"{header}: {value}" if header else value)
    return ", ".join(pairs)


def _normalize_row(row: list[str], width: int) -> list[str]:
    normalized = row[:width]
    if len(normalized) < width:
        normalized.extend([""] * (width - len(normalized)))
    return normalized


def _make_block(
    *,
    doc_id: str,
    block_type: str,
    content: str,
    structural_meta: dict[str, Any],
    style_hint: dict[str, Any],
) -> ContentBlock:
    return ContentBlock(
        id="",
        doc_id=doc_id,
        ordinal=-1,
        block_type=block_type,
        content=content,
        heading_stack=[],  # PDFs: heading hierarchy not inferred at MVP
        structural_meta=structural_meta,
        style_hint=style_hint,
    )
