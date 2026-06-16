"""Reviewer route - grade a document against its rubric, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.reviewer import find_config, run_pipeline

from api.deps import get_openai_client
from api.schemas import ReviewerRunResponse, ReviewResultOut
from api.streaming import run_with_progress

router = APIRouter()


DEFAULT_MAX_TOKENS = 32000


@router.post("/run")
async def run_reviewer(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    config = find_config(org, source_type, intervention_class)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reviewer config for ({org}, {source_type}, {intervention_class}).",
        )

    suffix = Path(file.filename or "upload").suffix or ".docx"
    contents = await file.read()
    doc_id = Path(file.filename or "doc").stem

    def work(progress):
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(contents)
                temp_path = temp_file.name

            llm_client = get_openai_client()
            result = run_pipeline(
                temp_path,
                config=config,
                llm_client=llm_client,
                indication=indication,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
                doc_id=doc_id,
            )

            return ReviewerRunResponse(
                review=ReviewResultOut(**asdict(result)),
            ).model_dump()
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
