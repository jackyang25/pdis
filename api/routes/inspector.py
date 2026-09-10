"""Inspector route - inspect a document against its rubric, streaming progress."""

from __future__ import annotations

import os
import tempfile
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api.operations.inspector import execute_inspection, prepare_inspection

from api.deps import MissingCredentialError, get_openai_client
from api.streaming import run_with_progress
from api.uploads import document_upload_parts

router = APIRouter()


DEFAULT_MAX_TOKENS = 32000


@router.post("/run")
async def run_inspector(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
    applicability_facts: str = Form("{}"),
) -> StreamingResponse:
    try:
        parsed_facts = json.loads(applicability_facts)
        if not isinstance(parsed_facts, dict):
            raise ValueError("applicability_facts must be a JSON object")
        prepared = prepare_inspection(
            org=org, source_type=source_type,
            intervention_class=intervention_class,
            applicability_facts=parsed_facts,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    doc_id, suffix = document_upload_parts(file.filename, tool="Inspector")
    contents = await file.read()

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

            return execute_inspection(
                temp_path,
                prepared=prepared,
                llm_client=llm_client,
                indication=indication,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
                doc_id=doc_id,
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
