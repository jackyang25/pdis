"""PD Reviewer route — grade a document, with optional peer-claim benchmark."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.evidence import FileClaimsStore
from services.pd_reviewer import find_config, run_pipeline

from api.deps import get_llm_client
from api.schemas import (
    PDReviewerRunResponse,
    PeerClaimOut,
    ReviewResultOut,
    SectionGradeOut,
    VariableGradeOut,
)

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CLAIMS_DIR = ROOT_DIR / "data" / "evidence_table"


@router.post("/run", response_model=PDReviewerRunResponse)
async def run_pd_reviewer(
    file: UploadFile = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    therapeutic_area: str | None = Form(None),
    use_peer_claims: bool = Form(True),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    max_tokens: int = Form(32000),
) -> PDReviewerRunResponse:
    config = find_config(org, source_type, intervention_class)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pd_reviewer config for ({org}, {source_type}, {intervention_class}).",
        )

    claims_store = None
    peer_claims_out: list[PeerClaimOut] = []
    if use_peer_claims and DEFAULT_CLAIMS_DIR.exists():
        claims_store = FileClaimsStore(DEFAULT_CLAIMS_DIR)

    suffix = Path(file.filename or "upload").suffix or ".docx"
    temp_path = ""
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        doc_id = Path(file.filename or "doc").stem
        llm_client = get_llm_client(provider, model)

        if claims_store is not None:
            peers = claims_store.get_by_header(
                intervention_class=intervention_class,
                therapeutic_area=therapeutic_area,
            )
            peers = [c for c in peers if c.source_id != doc_id]
            peer_claims_out = [
                PeerClaimOut(
                    source_id=c.source_id,
                    statement=c.statement,
                    attribute_ref=c.attribute_ref,
                    binding_confidence=c.binding_confidence,
                    evidence_strength=c.evidence_strength,
                )
                for c in peers
            ]

        result = run_pipeline(
            temp_path,
            config=config,
            llm_client=llm_client,
            therapeutic_area=therapeutic_area,
            claims_store=claims_store,
            max_tokens=max_tokens,
        )
        result.doc_id = doc_id

        return PDReviewerRunResponse(
            review=ReviewResultOut(
                doc_id=result.doc_id,
                overall_grade=result.overall_grade,
                top_issues=result.top_issues,
                section_grades=[
                    SectionGradeOut(
                        section_name=s.section_name,
                        grade=s.grade,
                        is_present=s.is_present,
                        missing_variables=s.missing_variables,
                        issues=s.issues,
                        recommendation=s.recommendation,
                        variable_grades=[
                            VariableGradeOut(
                                variable_name=v.variable_name,
                                grade=v.grade,
                                issues=v.issues,
                                recommendation=v.recommendation,
                                block_ids=v.block_ids,
                            )
                            for v in s.variable_grades
                        ],
                    )
                    for s in result.section_grades
                ],
                org=result.org,
                source_type=result.source_type,
                intervention_class=result.intervention_class,
                therapeutic_area=result.therapeutic_area,
            ),
            peer_claims=peer_claims_out,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
