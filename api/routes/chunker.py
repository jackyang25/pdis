"""Chunker route — parse + optionally label a document."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.chunker import find_config, run_pipeline

from api.deps import get_llm_client
from api.schemas import ChunkerRunResponse, ContentBlockOut

router = APIRouter()


@router.post("/run", response_model=ChunkerRunResponse)
async def run_chunker(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    therapeutic_area: str | None = Form(None),
    label: bool = Form(True),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    max_tokens: int = Form(16000),
) -> ChunkerRunResponse:
    config = find_config(org, source_type, intervention_class)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"No chunker config for ({org}, {source_type}, {intervention_class}).",
        )

    suffix = Path(file.filename or "upload").suffix or ".docx"
    temp_path = ""
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        llm_client = get_llm_client(provider, model) if label else None
        doc_id = Path(file.filename or "doc").stem
        blocks = run_pipeline(
            temp_path,
            doc_id,
            config=config if label else None,
            llm_client=llm_client,
            max_tokens=max_tokens,
            org=org,
            source_type=source_type,
            intervention_class=intervention_class,
            therapeutic_area=therapeutic_area,
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
                    label_confidence=b.label_confidence,
                )
                for b in blocks
            ],
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
