"""Searcher routes - discover adapters and run a query across selected sources."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse

from services.searcher import (
    findings_to_dicts,
    run_pipeline,
    source_specs,
    validate_source_keys,
)

from api.deps import get_search_runtime
from api.schemas import FindingOut, SearcherRunResponse, SearchSourceOut
from api.streaming import run_with_progress

router = APIRouter()

@router.get("/sources", response_model=list[SearchSourceOut])
def list_sources() -> list[SearchSourceOut]:
    """Expose registered source metadata so clients do not mirror an allowlist."""
    return [
        SearchSourceOut(
            key=source.key,
            label=source.label,
            default_enabled=source.default_enabled,
        )
        for source in source_specs()
    ]


@router.post("/run")
async def run_searcher(
    query: str = Form(...),
    sources: str = Form(""),
) -> StreamingResponse:
    requested = tuple(source.strip() for source in sources.split(",") if source.strip())
    try:
        selected = validate_source_keys(requested) if requested else tuple(
            source.key for source in source_specs() if source.default_enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    def work(progress):
        findings = run_pipeline(
            query,
            runtime=get_search_runtime(),
            sources=selected,
            progress_callback=progress,
        )
        return SearcherRunResponse(
            query=query,
            findings=[FindingOut(**d) for d in findings_to_dicts(findings)],
        ).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
