"""Monitor route - uploaded docs + 4 primitives -> Insights, streaming progress."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.monitor import find_config, insights_to_dicts, run_pipeline

from api.deps import get_openai_client
from api.schemas import FindingOut, InsightOut, MonitorRunResponse
from api.streaming import run_with_progress

router = APIRouter()


@router.post("/run")
async def run_monitor(
    files: list[UploadFile] = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    try:
        config = find_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    temp_paths: list[str] = []
    for upload in files:
        suffix = Path(upload.filename or "upload").suffix or ".docx"
        contents = await upload.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_paths.append(temp_file.name)

    def work(progress):
        try:
            openai_client = get_openai_client()
            insights = run_pipeline(
                temp_paths,
                config=config,
                openai_client=openai_client,
                search_client=openai_client,
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                progress_callback=progress,
            )
            insight_dicts = insights_to_dicts(insights)
            return MonitorRunResponse(
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                insights=[
                    InsightOut(
                        statement=d["statement"],
                        query=d["query"],
                        supporting_findings=[
                            FindingOut(**f) for f in d["supporting_findings"]
                        ],
                        org=d.get("org"),
                        source_type=d.get("source_type"),
                        intervention_class=d.get("intervention_class"),
                        indication=d.get("indication"),
                    )
                    for d in insight_dicts
                ],
            ).model_dump()
        finally:
            for path in temp_paths:
                if os.path.exists(path):
                    os.unlink(path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
