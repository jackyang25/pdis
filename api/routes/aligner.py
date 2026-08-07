"""Aligner route — parse a set of product-development documents together.

Takes documents as parallel lists rather than named reference/comparison fields,
because how many there are and which pairs compare is Aligner's configuration to
decide, not this route's. Adding a document type reaches neither this file nor
its schema.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.aligner import (
    DocumentInput,
    load_config,
    resolve_edges,
    run_pipeline,
)
from services.aligner.models import AlignmentDocument
from services.chunker import DOCUMENT_SUFFIXES, find_config as find_chunker_config

from api.deps import MissingCredentialError, get_openai_client
from api.schemas import (
    AlignerEdgesResponse,
    AlignerRunResponse,
    AlignmentEdgeSpecOut,
    AlignmentResultOut,
)
from api.streaming import run_with_progress

router = APIRouter()

DEFAULT_MAX_TOKENS = 16000


@router.get("/edges", response_model=AlignerEdgesResponse)
def list_edges() -> AlignerEdgesResponse:
    """The comparisons Aligner declares, so the picker can preview them.

    Published rather than mirrored in the web app: the config is the one place
    that decides what compares to what, and a copy in TypeScript would be a
    second answer that could disagree with it.
    """
    return AlignerEdgesResponse(
        edges=[
            AlignmentEdgeSpecOut(
                reference=spec.reference,
                comparison=spec.comparison,
                question=spec.question,
            )
            for spec in load_config().edges
        ]
    )


@router.post("/run")
async def run_aligner(
    files: list[UploadFile] = File(...),
    source_types: list[str] = Form(...),
    org: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    if len(files) != len(source_types):
        raise HTTPException(
            status_code=400, detail="Each document must be given a document type."
        )
    if len(files) < 2:
        raise HTTPException(
            status_code=400, detail="Aligner needs at least two documents to compare."
        )

    uploads: list[tuple[UploadFile, str, str, str]] = []
    for upload, source_type in zip(files, source_types):
        name = upload.filename or f"{source_type}.docx"
        suffix = Path(name).suffix.lower()
        if suffix not in DOCUMENT_SUFFIXES:
            raise HTTPException(
                status_code=400, detail="Aligner supports DOCX and PPTX files."
            )
        uploads.append((upload, source_type, Path(name).stem, suffix))

    doc_ids = [doc_id for _, _, doc_id, _ in uploads]
    if len(set(doc_ids)) != len(doc_ids):
        raise HTTPException(
            status_code=400, detail="Each document must have a distinct filename."
        )
    try:
        for _, source_type, _, _ in uploads:
            find_chunker_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    config = load_config()
    # Resolve before reading a single byte: a set of documents that forms no
    # comparison is a 400, not a run that streams and then fails.
    try:
        resolve_edges(
            config,
            [
                AlignmentDocument(doc_id=doc_id, source_type=source_type, display_name="")
                for _, source_type, doc_id, _ in uploads
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    contents = [(await upload.read(), source_type, doc_id, suffix)
                for upload, source_type, doc_id, suffix in uploads]

    # Construct provider clients before the stream opens: a missing credential
    # must fail the request, not arrive as an event on a 200 response.
    try:
        llm_client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def work(progress):
        temp_paths: list[str] = []
        try:
            documents: list[DocumentInput] = []
            for payload, source_type, doc_id, suffix in contents:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                    temp_file.write(payload)
                    temp_paths.append(temp_file.name)
                documents.append(
                    DocumentInput(
                        file_path=temp_file.name,
                        source_type=source_type,
                        doc_id=doc_id,
                    )
                )
            result = run_pipeline(
                documents,
                org=org,
                intervention_class=intervention_class,
                indication=indication,
                config=config,
                llm_client=llm_client,
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
