"""Evidence route — extract claims from a single document."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.evidence import (
    default_source_id_from_path,
    find_config,
    run_pipeline,
)

from api.deps import get_llm_client
from api.schemas import ClaimOut, EvidenceRunResponse

router = APIRouter()


@router.post("/run", response_model=EvidenceRunResponse)
async def run_evidence(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    therapeutic_area: str | None = Form(None),
    source_kind: str = Form("product_profile"),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    max_tokens: int = Form(16000),
) -> EvidenceRunResponse:
    try:
        config = find_config(intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    suffix = Path(file.filename or "upload").suffix or ".docx"
    temp_path = ""
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        doc_id = Path(file.filename or "doc").stem
        source_id = default_source_id_from_path(file.filename or doc_id)
        llm_client = get_llm_client(provider, model)
        _blocks, claims = run_pipeline(
            file_path=temp_path,
            doc_id=doc_id,
            source_id=source_id,
            config=config,
            llm_client=llm_client,
            org=org,
            source_type=source_type,
            therapeutic_area=therapeutic_area,
            source_kind=source_kind,
            max_tokens=max_tokens,
        )
        return EvidenceRunResponse(
            doc_id=doc_id,
            source_id=source_id,
            claims=[
                ClaimOut(
                    id=c.id,
                    ordinal=c.ordinal,
                    statement=c.statement,
                    claim_type=c.claim_type,
                    polarity=c.polarity,
                    source_id=c.source_id,
                    source_kind=c.source_kind,
                    source_locator=c.source_locator,
                    attribute_ref=c.attribute_ref,
                    binding_confidence=c.binding_confidence,
                    evidence_strength=c.evidence_strength,
                    recency_tier=c.recency_tier,
                    org=c.org,
                    source_type=c.source_type,
                    intervention_class=c.intervention_class,
                    therapeutic_area=c.therapeutic_area,
                )
                for c in claims
            ],
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
