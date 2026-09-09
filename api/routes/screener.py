"""Screener receives one collection of traceable documents for one gate review."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from services.screener import (
    DocumentInput,
    SUPPORTED_DOCUMENT_SUFFIXES,
    available_gates,
    find_config,
    resolve_questions,
    run_pipeline,
)

from api.deps import MissingCredentialError, get_openai_client
from api.schemas import (
    ScreenerGatesResponse,
    ScreenerRunResponse,
    GateReviewOut,
    GateSpecOut,
)
from api.streaming import run_with_progress
from api.uploads import document_upload_parts

router = APIRouter()

DEFAULT_MAX_TOKENS = 16000


@router.get("/gates", response_model=ScreenerGatesResponse)
def list_gates(org: str = "bmgf", intervention: str | None = None) -> ScreenerGatesResponse:
    """The gates Screener declares for this org and intervention, in development order.

    Published rather than mirrored in the web app: the banks are the one place that
    decides which gates exist, and a copy in TypeScript would be a second answer
    that could disagree with them.

    Filtered by intervention when one is given, so a modality no bank covers offers no
    gate rather than offering one that would ask it about synthetic routes.
    """
    return ScreenerGatesResponse(
        gates=[
            GateSpecOut(id=gate.id, label=gate.label, ordinal=gate.ordinal)
            for gate in available_gates(org, intervention)
        ]
    )


@router.post("/run")
async def run_screener(
    request: Request,
    files: list[UploadFile] = File(...),
    gate: str = Form(...),
    org: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    form = await request.form()
    legacy_fields = {"source_types", "context_files", "context_labels"} & set(form)
    if legacy_fields:
        raise HTTPException(
            status_code=400,
            detail="Screener accepts one document collection. Remove obsolete fields: "
            + ", ".join(sorted(legacy_fields)),
        )

    uploads: list[tuple[UploadFile, str, str]] = []
    for upload in files:
        doc_id, suffix = document_upload_parts(
            upload.filename, tool="Screener", accepted_suffixes=SUPPORTED_DOCUMENT_SUFFIXES,
        )
        uploads.append((upload, doc_id, suffix))

    doc_ids = [doc_id for _, doc_id, _ in uploads]
    if len(set(doc_ids)) != len(doc_ids):
        raise HTTPException(
            status_code=400, detail="Each document must have a distinct filename."
        )

    try:
        config = find_config(org, gate)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Checked here as well as filtered from the picker: a stale page could still post a
    # gate whose bank has nothing to ask this modality, and a review of questions none of
    # which apply reads exactly like a review that found nothing.
    if not config.serves(intervention_class):
        raise HTTPException(
            status_code=400,
            detail=(
                f"The {config.gate_label} question bank is written for "
                f"{', '.join(sorted(config.intervention_classes))} programs, not for "
                f"{intervention_class}. Its questions ask about matters this modality "
                "does not have, so every one would report as unanswered."
            ),
        )

    # Resolve before reading a byte: a bank with nothing to say about this product
    # is a 400, not a run that streams and then fails.
    try:
        resolve_questions(config, intervention_class=intervention_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    contents = []
    for upload, doc_id, suffix in uploads:
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"{doc_id}: the file is empty.")
        contents.append((payload, doc_id, suffix))

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
            for payload, doc_id, suffix in contents:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                    temp.write(payload)
                    temp_paths.append(temp.name)
                documents.append(
                    DocumentInput(
                        file_path=temp.name, doc_id=doc_id
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
            return ScreenerRunResponse(review=GateReviewOut(**asdict(result))).model_dump()
        finally:
            for temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
