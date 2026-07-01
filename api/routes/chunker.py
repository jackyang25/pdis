"""Chunker route — parse + optionally label a document, streaming progress."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.chunker import find_config, run_pipeline

from api.deps import get_openai_client
from api.schemas import ChunkerRunResponse, ContentBlockOut
from api.streaming import run_with_progress

router = APIRouter()


DEFAULT_MAX_TOKENS = 16000


@router.post("/run")
async def run_chunker(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    try:
        config = find_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
            blocks = run_pipeline(
                temp_path,
                doc_id,
                config=config,
                llm_client=llm_client,
                max_tokens=DEFAULT_MAX_TOKENS,
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                progress_callback=progress,
            )
            return ChunkerRunResponse(
                doc_id=doc_id,
                blocks=[
                    ContentBlockOut(
                        id=b.id,
                        doc_id=b.doc_id,
                        ordinal=b.ordinal,
                        block_type=b.block_type,
                        content=b.content,
                        heading_stack=b.heading_stack,
                        section_label=b.section_label,
                        structural_meta=b.structural_meta,
                        style_hint=b.style_hint,
                    )
                    for b in blocks
                ],
            ).model_dump()
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
