"""Excel's layout for an exported result: a summary sheet, then one sheet per table.

The rows are the tool's (`shared.report_export`); this decides only how a workbook shows
them. A workbook is read by sorting and filtering, so each table is a sheet of its own with
a bold header row that stays in view and filters, and every cell holds the same words the
Word file prints - a value is never split, reworded or turned into a number here.
"""

from __future__ import annotations

import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from shared.report_export import CAVEAT, NONE, ExportReport, Table

#: Excel refuses a sheet name over 31 characters or holding any of these.
MAX_SHEET_NAME = 31
_SHEET_NAME_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")
#: The characters a table's columns share between them, as Word shares a page's width.
TABLE_WIDTH = 180
MIN_COLUMN_WIDTH = 10
SUMMARY_WIDTH = 120
_HEADER_FILL = PatternFill("solid", fgColor="E8EAED")
_WRAP = Alignment(wrap_text=True, vertical="top")


def xlsx_workbook(report: ExportReport) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    _summary(summary, report)
    names = {summary.title.casefold()}
    for index, table in enumerate(report.tables, start=1):
        # A report's only table is what the report is, so it takes the report's title.
        heading = table.heading or (report.title if len(report.tables) == 1 else f"Table {index}")
        _table(workbook.create_sheet(_sheet_name(heading, names)), table, heading)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _summary(sheet: Worksheet, report: ExportReport) -> None:
    sheet.column_dimensions["A"].width = SUMMARY_WIDTH
    sheet.append([report.title])
    sheet["A1"].font = Font(bold=True, size=14)
    for line in (report.context, report.about, CAVEAT, report.summary, *report.notes):
        if line:
            sheet.append([line])
    for row in sheet.iter_rows(min_row=2):
        row[0].alignment = _WRAP


def _table(sheet: Worksheet, table: Table, heading: str) -> None:
    # The full heading heads the sheet: a tab name is cut to Excel's 31 characters.
    sheet.append([heading])
    sheet.cell(row=1, column=1).font = Font(bold=True, size=12)
    if table.note:
        sheet.append([table.note])
        sheet.cell(row=sheet.max_row, column=1).font = Font(italic=True)
    # A table with no rows is its heading and note alone, as in Word: a header over nothing reads as lost rows.
    if not table.rows:
        return
    shares = table.widths or (1.0,) * len(table.columns)
    if len(shares) != len(table.columns):
        raise ValueError("a table gives one width per column")
    sheet.append(list(table.columns))
    header = sheet.max_row
    for cell in sheet[header]:
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
        cell.alignment = _WRAP
    for row in table.rows:
        if len(row) != len(table.columns):
            raise ValueError("a row gives one cell per column")
        sheet.append([text or NONE for text in row])
    for row in sheet.iter_rows(min_row=header + 1):
        for cell in row:
            cell.alignment = _WRAP
    for index, share in enumerate(shares, start=1):
        width = max(MIN_COLUMN_WIDTH, round(TABLE_WIDTH * share / sum(shares)))
        sheet.column_dimensions[get_column_letter(index)].width = width
    last = get_column_letter(len(table.columns))
    sheet.freeze_panes = f"A{header + 1}"
    sheet.auto_filter.ref = f"A{header}:{last}{sheet.max_row}"
    # Printed as the Word file is: landscape, every column on the page, the header on each page.
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = f"{header}:{header}"


def _sheet_name(heading: str, taken: set[str]) -> str:
    """The table's heading as a legal, unique tab name: Excel's limits, nothing else changed.

    A heading past the limit is cut at a word and marked with an ellipsis, so a tab never ends
    mid-word; the sheet's first row carries it whole.
    """
    base = " ".join(_SHEET_NAME_FORBIDDEN.sub(" ", heading).split()).strip("'") or "Table"
    name, suffix = _shortened(base, MAX_SHEET_NAME), 2
    while name.casefold() in taken:
        tail = f" ({suffix})"
        name, suffix = _shortened(base, MAX_SHEET_NAME - len(tail)) + tail, suffix + 1
    taken.add(name.casefold())
    return name


def _shortened(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    # Back to the last whole word, unless that would leave less than half the room used.
    if " " in cut and cut.rindex(" ") >= limit // 2:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" -→·:,") + "…"
