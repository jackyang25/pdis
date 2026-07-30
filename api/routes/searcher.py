"""Searcher routes - discover adapters and run a query across selected sources."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse

from services.searcher import (
    findings_to_dicts,
    run_pipeline,
    source_specs,
    unconfigured_source_keys,
    validate_source_keys,
)

from api.deps import (
    MissingCredentialError,
    get_search_integrations,
    get_search_runtime,
)
from api.schemas import (
    FindingOut,
    SearcherRunResponse,
    SearchSourceOut,
    SourceAttributionOut,
)
from api.streaming import run_with_progress

router = APIRouter()


@router.get("/sources", response_model=list[SearchSourceOut])
def list_sources() -> list[SearchSourceOut]:
    """Expose registered source metadata so clients do not mirror an allowlist."""
    integrations = get_search_integrations()
    return [
        SearchSourceOut(
            key=source.key,
            label=source.label,
            default_enabled=source.default_enabled,
            configured=(not source.integration_key or source.integration_key in integrations),
            evidence_domains=list(source.evidence_domains),
            required_entity_types=list(source.required_entity_types),
            attribution=(
                SourceAttributionOut(
                    label=source.attribution.label,
                    url=source.attribution.url,
                    prefix=source.attribution.prefix,
                )
                if source.attribution
                else None
            ),
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
    try:
        runtime = get_search_runtime()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    missing = unconfigured_source_keys(selected, runtime)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Unconfigured retrieval source(s): {', '.join(missing)}",
        )

    def work(progress):
        findings = run_pipeline(
            query,
            runtime=runtime,
            sources=selected,
            progress_callback=progress,
        )
        return SearcherRunResponse(
            query=query,
            findings=[FindingOut(**d) for d in findings_to_dicts(findings)],
        ).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
