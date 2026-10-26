"""Drafter: a run that suggests iTPP targets, and the Word export of a draft."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import Response, StreamingResponse

from services.drafter import export_docx, find_config, run_pipeline
from shared.vocabulary import indications_for

from api.deps import MissingCredentialError, get_openai_client, get_search_runtime
from api.schemas import DrafterExportRequest, DrafterRunResponse, DraftResultOut
from api.streaming import run_with_progress
from api.word_export import word_export

router = APIRouter()

SOURCE_TYPE = "itpp"


@router.post("/run")
async def run_drafter(
    org: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    try:
        find_config(org, SOURCE_TYPE, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if indication not in indications_for(intervention_class):
        raise HTTPException(status_code=400, detail=f"Unknown disease / condition {indication!r} for {intervention_class}.")

    # Construct provider clients before the stream opens: a missing credential must
    # fail the request, not arrive as an event on a 200 response.
    try:
        llm_client = get_openai_client()
        runtime = get_search_runtime(llm_client)
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def work(progress):
        result = run_pipeline(
            org=org, intervention_class=intervention_class, indication=indication,
            llm_client=llm_client, runtime=runtime, progress_callback=progress,
        )
        return DrafterRunResponse(result=DraftResultOut(**result.to_dict())).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")


@router.post("/export")
def export_drafter(request: DrafterExportRequest) -> Response:
    """A draft as a Word table, each target marked as a suggestion with its sources."""
    return word_export("drafter", export_docx, request.result.model_dump())
