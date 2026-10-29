"""The response every tool's export returns: the tool's report, written as Word or Excel.

The tool decides what its report says (`export_report`); the format only decides how it is
written, so a workbook and a Word file of one result always say the same thing.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import HTTPException
from fastapi.responses import Response

from shared.report_export import ExportReport
from shared.word_export import word_document
from shared.xlsx_export import xlsx_workbook

ExportFormat = Literal["docx", "xlsx"]

_WRITERS: dict[str, tuple[Callable[[ExportReport], bytes], str]] = {
    "docx": (word_document, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": (xlsx_workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


def export_response(
    tool: str,
    build: Callable[[dict[str, Any]], ExportReport],
    result: dict[str, Any],
    file_format: ExportFormat,
) -> Response:
    """Build a final result's file, refusing one its service will not export."""
    try:
        report = build(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write, media_type = _WRITERS[file_format]
    return Response(
        content=write(report),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="pdis-{tool}.{file_format}"'},
    )
