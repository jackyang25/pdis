"""Expert route — triage one gate's question bank against a set of documents.

Documents arrive as parallel lists, as Aligner's do, because how many there are is
Expert's business rather than this route's. Context items arrive the same way and go
no further than the prompt: their text is never stored, so nothing here persists it
and no schema carries it.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.chunker import DOCUMENT_SUFFIXES, find_config as find_chunker_config
from services.expert import (
    ContextItem,
    DocumentInput,
    available_gates,
    find_config,
    resolve_questions,
    run_pipeline,
)

from api.deps import MissingCredentialError, get_openai_client
from api.schemas import (
    ExpertGatesResponse,
    ExpertRunResponse,
    GateReviewOut,
    GateSpecOut,
)
from api.streaming import run_with_progress

router = APIRouter()

DEFAULT_MAX_TOKENS = 16000


@router.get("/gates", response_model=ExpertGatesResponse)
def list_gates(org: str = "bmgf") -> ExpertGatesResponse:
    """The gates Expert declares, in development order.

    Published rather than mirrored in the web app: the banks are the one place that
    decides which gates exist, and a copy in TypeScript would be a second answer
    that could disagree with them.
    """
    return ExpertGatesResponse(
        gates=[
            GateSpecOut(id=gate.id, label=gate.label, ordinal=gate.ordinal)
            for gate in available_gates(org)
        ]
    )


@router.post("/run")
async def run_expert(
    files: list[UploadFile] = File(...),
    source_types: list[str] = Form(...),
    gate: str = Form(...),
    org: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
    context_labels: list[str] = Form(default_factory=list),
    context_texts: list[str] = Form(default_factory=list),
) -> StreamingResponse:
    if len(files) != len(source_types):
        raise HTTPException(
            status_code=400, detail="Each document must be given a document type."
        )
    if len(context_labels) != len(context_texts):
        raise HTTPException(
            status_code=400, detail="Each context item must have a label and text."
        )

    uploads: list[tuple[UploadFile, str, str, str]] = []
    for upload, source_type in zip(files, source_types):
        name = upload.filename or f"{source_type}.docx"
        suffix = Path(name).suffix.lower()
        if suffix not in DOCUMENT_SUFFIXES:
            raise HTTPException(
                status_code=400, detail="Expert supports DOCX and PPTX files."
            )
        uploads.append((upload, source_type, Path(name).stem, suffix))

    doc_ids = [doc_id for _, _, doc_id, _ in uploads]
    if len(set(doc_ids)) != len(doc_ids):
        raise HTTPException(
            status_code=400, detail="Each document must have a distinct filename."
        )
    if len(set(source_types)) != len(source_types):
        raise HTTPException(
            status_code=400,
            detail="Each document must be a different type. A review covers one "
            "investment's set, so two documents of one type would be two candidates "
            "or two versions, and a citation could not say which was read.",
        )

    try:
        config = find_config(org, gate)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        for _, source_type, _, _ in uploads:
            find_chunker_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Resolve before reading a byte: a bank with nothing to say about this product
    # is a 400, not a run that streams and then fails.
    try:
        resolve_questions(config, intervention_class=intervention_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context_items = [
        ContextItem(label=label.strip(), text=text)
        for label, text in zip(context_labels, context_texts)
        if label.strip() and text.strip()
    ]
    labels = [item.label for item in context_items]
    if len(set(labels)) != len(labels):
        raise HTTPException(
            status_code=400,
            detail="Two context items share a label. Labels are how an answer "
            "names its source, so they must be distinct.",
        )

    contents = [
        (await upload.read(), source_type, doc_id, suffix)
        for upload, source_type, doc_id, suffix in uploads
    ]

    # Construct provider clients before the stream opens: a missing credential must
    # fail the request, not arrive as an event on a 200 response.
    try:
        llm_client = get_openai_client()
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def work(progress):
        temp_paths: list[str] = []
        try:
            documents: list[DocumentInput] = []
            for payload, source_type, doc_id, suffix in contents:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                    temp.write(payload)
                    temp_paths.append(temp.name)
                documents.append(
                    DocumentInput(
                        file_path=temp.name, source_type=source_type, doc_id=doc_id
                    )
                )
            result = run_pipeline(
                documents,
                org=org,
                intervention_class=intervention_class,
                indication=indication,
                config=config,
                llm_client=llm_client,
                context_items=context_items,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
            )
            return ExpertRunResponse(review=GateReviewOut(**asdict(result))).model_dump()
        finally:
            for temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
