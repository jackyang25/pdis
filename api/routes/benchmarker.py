"""Benchmarker route — extract claims from a single document, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.benchmarker import (
    default_source_id_from_path,
    find_config,
    run_pipeline,
)

from api.deps import get_openai_client
from api.schemas import ClaimOut, BenchmarkerRunResponse
from api.streaming import run_with_progress

router = APIRouter()


DEFAULT_MAX_TOKENS = 16000
DEFAULT_SOURCE_KIND = "product_profile"


@router.post("/run")
async def run_benchmarker(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    try:
        config = find_config(intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    suffix = Path(file.filename or "upload").suffix or ".docx"
    contents = await file.read()
    doc_id = Path(file.filename or "doc").stem
    source_id = default_source_id_from_path(file.filename or doc_id)

    def work(progress):
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(contents)
                temp_path = temp_file.name

            llm_client = get_openai_client()
            _blocks, claims = run_pipeline(
                file_path=temp_path,
                doc_id=doc_id,
                source_id=source_id,
                config=config,
                llm_client=llm_client,
                org=org,
                source_type=source_type,
                indication=indication,
                source_kind=DEFAULT_SOURCE_KIND,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
            )
            return BenchmarkerRunResponse(
                doc_id=doc_id,
                source_id=source_id,
                claims=[ClaimOut(**asdict(c)) for c in claims],
            ).model_dump()
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
