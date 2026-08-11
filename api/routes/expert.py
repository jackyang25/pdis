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
    ContextReadError,
    DocumentInput,
    MAX_TOTAL_CONTEXT_CHARACTERS,
    available_gates,
    find_config,
    read_context_text,
    resolve_questions,
    run_pipeline,
    total_context_length,
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
def list_gates(org: str = "bmgf", intervention: str | None = None) -> ExpertGatesResponse:
    """The gates Expert declares for this org and intervention, in development order.

    Published rather than mirrored in the web app: the banks are the one place that
    decides which gates exist, and a copy in TypeScript would be a second answer
    that could disagree with them.

    Filtered by intervention when one is given, so a modality no bank covers offers no
    gate rather than offering one that would ask it about synthetic routes.
    """
    return ExpertGatesResponse(
        gates=[
            GateSpecOut(id=gate.id, label=gate.label, ordinal=gate.ordinal)
            for gate in available_gates(org, intervention)
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
    context_files: list[UploadFile] = File(default_factory=list),
    context_labels: list[str] = Form(default_factory=list),
) -> StreamingResponse:
    if len(files) != len(source_types):
        raise HTTPException(
            status_code=400, detail="Each document must be given a document type."
        )
    if len(context_labels) != len(context_files):
        raise HTTPException(
            status_code=400, detail="Each context attachment must have a label."
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

    # Read here rather than in the pipeline: a file that cannot be read is a 400 the
    # user can fix, and finding that out after the stream opens would report it as a
    # failed review instead. The label is the reader's, never the filename — it is what
    # an answer is attributed to, and `AIV_CMC_final_v3` is not an attribution.
    context_items: list[ContextItem] = []
    for upload, label in zip(context_files, context_labels):
        name = Path(upload.filename or "attachment").name
        if not label.strip():
            raise HTTPException(
                status_code=400,
                detail=f"{name}: name this context so an answer can be attributed to it.",
            )
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"{name}: the file is empty.")
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(name).suffix.lower()
        ) as temp_file:
            temp_file.write(payload)
            context_path = temp_file.name
        try:
            text = read_context_text(context_path, filename=name)
        except ContextReadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if os.path.exists(context_path):
                os.unlink(context_path)
        context_items.append(ContextItem(label=label.strip(), text=text))

    total = total_context_length([item.text for item in context_items])
    if total > MAX_TOTAL_CONTEXT_CHARACTERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{total:,} characters of context in total, over the "
                f"{MAX_TOTAL_CONTEXT_CHARACTERS:,} limit. Every question in the gate is "
                "read against all of it, so attach the parts that bear on this review."
            ),
        )

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
