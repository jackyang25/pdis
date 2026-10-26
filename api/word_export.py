"""The response every tool's Word export returns: one media type, one filename shape."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import Response

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def word_export(tool: str, build: Callable[[dict[str, Any]], bytes], result: dict[str, Any]) -> Response:
    """Build a final result's Word file, refusing one its service will not export."""
    try:
        data = build(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="pdis-{tool}.docx"'},
    )
