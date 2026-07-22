"""Aligner route — build a streamed traceability comparison across two documents."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.aligner import load_config, run_pipeline
from services.chunker import find_config as find_chunker_config

from api.deps import get_openai_client
from api.schemas import AlignerRunResponse, AlignmentResultOut
from api.streaming import run_with_progress

router = APIRouter()

DEFAULT_MAX_TOKENS = 16000
SUPPORTED_SUFFIXES = {".docx", ".pdf", ".pptx"}


@router.post("/run")
async def run_aligner(
    reference_file: UploadFile = File(...),
    comparison_file: UploadFile = File(...),
    org: str = Form(...),
    reference_source_type: str = Form(...),
    comparison_source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    reference_name = reference_file.filename or "reference.docx"
    comparison_name = comparison_file.filename or "comparison.docx"
    reference_suffix = Path(reference_name).suffix.lower()
    comparison_suffix = Path(comparison_name).suffix.lower()
    if reference_suffix not in SUPPORTED_SUFFIXES or comparison_suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Aligner supports DOCX, PDF, and PPTX files.")
    reference_doc_id = Path(reference_name).stem
    comparison_doc_id = Path(comparison_name).stem
    if reference_doc_id == comparison_doc_id:
        raise HTTPException(
            status_code=400,
            detail="Reference and comparison documents must have distinct filenames.",
        )
    try:
        find_chunker_config(org, reference_source_type, intervention_class)
        find_chunker_config(org, comparison_source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    reference_contents = await reference_file.read()
    comparison_contents = await comparison_file.read()
    config = load_config()

    def work(progress):
        temp_paths: list[str] = []
        try:
            for contents, suffix in (
                (reference_contents, reference_suffix),
                (comparison_contents, comparison_suffix),
            ):
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                    temp_file.write(contents)
                    temp_paths.append(temp_file.name)
            result = run_pipeline(
                temp_paths[0],
                temp_paths[1],
                reference_source_type=reference_source_type,
                comparison_source_type=comparison_source_type,
                org=org,
                intervention_class=intervention_class,
                indication=indication,
                config=config,
                llm_client=get_openai_client(),
                reference_doc_id=reference_doc_id,
                comparison_doc_id=comparison_doc_id,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
            )
            return AlignerRunResponse(
                alignment=AlignmentResultOut(**asdict(result))
            ).model_dump()
        finally:
            for temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
