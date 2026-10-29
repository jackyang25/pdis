"""Scout route - uploaded docs + 4 primitives -> Matches, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from services.scout import (
    FieldSelectionError,
    export_report,
    result_from_target_review,
    ScoutResult,
    assessments_to_dicts,
    blocks_to_dicts,
    conformity_to_dicts,
    development_programs_to_dicts,
    find_config,
    matches_to_dicts,
    precedents_to_dicts,
    safety_observations_to_dicts,
    continue_pipeline,
    run_pipeline,
)

from api.deps import (
    MissingCredentialError,
    get_openai_client,
    get_quantitative_anthropic_client,
    get_search_runtime,
)
from api.schemas import (
    ConformityOut,
    ContentBlockOut,
    DevelopmentProgramOut,
    DocumentContextValidationOut,
    EvidenceAssessmentOut,
    FunnelStatsOut,
    IdentityReconciliationOut,
    MatchOut,
    QuantitativeLedgerOut,
    RetrievalScopeOut,
    ScoutContinueRequest,
    ScoutExportRequest,
    ScoutRunResponse,
    SafetyObservationOut,
    SearchTraceOut,
    PrecedentOut,
    VariableOut,
)
from api.streaming import run_with_progress
from api.uploads import document_upload_parts, read_uploads, require_distinct_doc_ids
from api.result_export import ExportFormat, export_response

router = APIRouter()


def _response_from_result(
    result: ScoutResult,
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> ScoutRunResponse:
    """Publish a result through the schema, field for field.

    Each record is validated from its serialised form rather than rebuilt by hand: a
    hand-built copy is where `failure_code` went missing from matches, assessments and
    precedents, so a failed stage published a value with nothing saying why.
    """
    return ScoutRunResponse(
        phase=result.phase,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
        published_since=result.published_since,
        context_validation=DocumentContextValidationOut.model_validate(
            asdict(result.context_validation)
        ),
        retrieval_scope=RetrievalScopeOut.model_validate(asdict(result.retrieval_scope)),
        reconciliations=[
            IdentityReconciliationOut.model_validate(asdict(record))
            for record in result.reconciliations
        ],
        not_searched_fields=list(result.not_searched_fields),
        quantitative_ledger=QuantitativeLedgerOut.model_validate(
            asdict(result.quantitative_ledger)
        ),
        variables=[VariableOut.model_validate(asdict(item)) for item in result.variables],
        search_plan=[SearchTraceOut.model_validate(asdict(item)) for item in result.search_plan],
        matches=[MatchOut.model_validate(item) for item in matches_to_dicts(result.matches)],
        assessments=[
            EvidenceAssessmentOut.model_validate(item)
            for item in assessments_to_dicts(result.assessments)
        ],
        conformity=[ConformityOut(**item) for item in conformity_to_dicts(result.conformity)],
        precedents=[
            PrecedentOut.model_validate(item) for item in precedents_to_dicts(result.precedents)
        ],
        development_landscape=[
            DevelopmentProgramOut(**item)
            for item in development_programs_to_dicts(result.development_landscape)
        ],
        safety_observations=[
            SafetyObservationOut(**item)
            for item in safety_observations_to_dicts(result.safety_observations)
        ],
        stats=FunnelStatsOut.model_validate(asdict(result.stats)),
        blocks=[ContentBlockOut(**item) for item in blocks_to_dicts(result.blocks)],
    )


@router.post("/run")
async def run_scout(
    files: list[UploadFile] = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
    published_since: str = Form(""),
) -> StreamingResponse:
    try:
        config = find_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    uploads = [
        (upload, *document_upload_parts(upload.filename, tool="Scout"))
        for upload in files
    ]
    doc_ids = [doc_id for _, doc_id, _ in uploads]
    require_distinct_doc_ids(doc_ids)
    payloads = await read_uploads([(upload, doc_id) for upload, doc_id, _ in uploads])

    # Construct provider clients before the stream opens: a missing credential
    # must fail the request, not arrive as an event on a 200 response.
    try:
        openai_client = get_openai_client()
        quantitative_client = get_quantitative_anthropic_client()
        retrieval_runtime = get_search_runtime(openai_client)
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def work(progress):
        temp_paths: list[str] = []
        try:
            for payload, (_, _, suffix) in zip(payloads, uploads):
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                    temp_file.write(payload)
                    temp_paths.append(temp_file.name)
            result = run_pipeline(
                temp_paths,
                doc_ids=doc_ids,
                config=config,
                openai_client=openai_client,
                retrieval_runtime=retrieval_runtime,
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                # Declared here and carried on the draft, so the continuation
                # cannot widen the cohort after targets were approved.
                published_since=published_since,
                quantitative_mapping_client=quantitative_client,
                progress_callback=progress,
            )
            return _response_from_result(
                result,
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
            ).model_dump()
        finally:
            for path in temp_paths:
                if os.path.exists(path):
                    os.unlink(path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")


@router.post("/continue")
async def continue_scout(payload: ScoutContinueRequest) -> StreamingResponse:
    draft = payload.draft
    try:
        config = find_config(draft.org, draft.source_type, draft.intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        prepared = result_from_target_review(draft.model_dump())
    except FieldSelectionError as exc:
        # The reviewer's own choice, correctable on the checkpoint, before any work starts.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Construct provider clients before the stream opens: a missing credential
    # must fail the request, not arrive as an event on a 200 response.
    try:
        openai_client = get_openai_client()
        quantitative_client = get_quantitative_anthropic_client()
        retrieval_runtime = get_search_runtime(openai_client)
    except MissingCredentialError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def work(progress):
        result = continue_pipeline(
            prepared,
            config=config,
            openai_client=openai_client,
            quantitative_mapping_client=quantitative_client,
            retrieval_runtime=retrieval_runtime,
            org=draft.org,
            source_type=draft.source_type,
            intervention_class=draft.intervention_class,
            indication=draft.indication,
            progress_callback=progress,
        )
        return _response_from_result(
            result,
            org=draft.org,
            source_type=draft.source_type,
            intervention_class=draft.intervention_class,
            indication=draft.indication,
        ).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")


@router.post("/export")
def export_scout(request: ScoutExportRequest, file_format: ExportFormat = Query("docx", alias="format")) -> Response:
    """A final evidence review as a Word or Excel file, from the result the browser holds."""
    return export_response("scout", export_report, request.result.model_dump(), file_format)
