"""Inspector route - inspect a document against its rubric, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.inspector import find_config, run_pipeline

from api.deps import MissingCredentialError, get_openai_client
from api.schemas import InspectionResultOut, InspectorRunResponse
from api.streaming import run_with_progress

router = APIRouter()


DEFAULT_MAX_TOKENS = 32000


@router.post("/run")
async def run_inspector(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    try:
        config = find_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    suffix = Path(file.filename or "upload").suffix or ".docx"
    contents = await file.read()
    doc_id = Path(file.filename or "doc").stem

    # Construct provider clients before the stream opens: a missing credential
    # must fail the request, not arrive as an event on a 200 response.
    try:
        llm_client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def work(progress):
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(contents)
                temp_path = temp_file.name

            result = run_pipeline(
                temp_path,
                config=config,
                llm_client=llm_client,
                indication=indication,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
                doc_id=doc_id,
            )

            return InspectorRunResponse(
                inspection=InspectionResultOut(**asdict(result)),
            ).model_dump()
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
