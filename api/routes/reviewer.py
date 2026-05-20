"""Reviewer route — grade a document with peer-claim benchmark, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.benchmarker import FileClaimsStore
from services.reviewer import find_config, run_pipeline

from api.deps import get_llm_client
from api.schemas import ReviewerRunResponse, PeerClaimOut, ReviewResultOut
from api.streaming import run_with_progress

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CLAIMS_DIR = ROOT_DIR / "data" / "claims"


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

            claims_store = (
                FileClaimsStore(DEFAULT_CLAIMS_DIR) if DEFAULT_CLAIMS_DIR.exists() else None
            )

            llm_client = get_llm_client()
            result = run_pipeline(
                temp_path,
                config=config,
                llm_client=llm_client,
                indication=indication,
                claims_store=claims_store,
                max_tokens=DEFAULT_MAX_TOKENS,
                progress_callback=progress,
                doc_id=doc_id,
            )

            # Build the audit-overview list of peer claims that were actually
            # queryable for this rubric (attributes the rubric declares,
            # excluding self-references).
            peer_claims_out: list[PeerClaimOut] = []
            if claims_store is not None:
                seen: set[str] = set()
                attribute_refs = {
                    v.attribute_ref
                    for section in config.sections
                    for v in section.variables
                    if v.attribute_ref
                }
                for ref in sorted(attribute_refs):
                    for c in claims_store.get_by_attribute(
                        ref,
                        indication=indication,
                        exclude_source_id=doc_id,
                    ):
                        cid = c.id or f"{c.source_id}/{c.ordinal}"
                        if cid in seen:
                            continue
                        seen.add(cid)
                        peer_claims_out.append(
                            PeerClaimOut(
                                source_id=c.source_id,
                                statement=c.statement,
                                claim_type=c.claim_type,
                                attribute_ref=c.attribute_ref,
                                valid_as_of=c.valid_as_of,
                                extracted_at=c.extracted_at,
                                org=c.org,
                                source_type=c.source_type,
                                indication=c.indication,
                            )
                        )

            return ReviewerRunResponse(
                review=ReviewResultOut(**asdict(result)),
                peer_claims=peer_claims_out,
            ).model_dump()
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
