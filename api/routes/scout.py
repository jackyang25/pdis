"""Scout route - uploaded docs + 4 primitives -> Matches, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.scout import (
    Attribute,
    DocumentContextValidation,
    DocumentSpan,
    EvidenceEntity,
    FunnelStats,
    NumericExpression,
    QuantitativeLedger,
    QuantitativeLedgerReview,
    QuantitativeFieldLink,
    QuantitativeStatementDisposition,
    QuantitativeTarget,
    ScoutResult,
    SemanticSlot,
    assessments_to_dicts,
    blocks_to_dicts,
    conformity_to_dicts,
    development_programs_to_dicts,
    find_config,
    matches_to_dicts,
    precedents_to_dicts,
    safety_signals_to_dicts,
    continue_pipeline,
    run_pipeline,
)
from services.chunker import ContentBlock, ImageAsset

from api.deps import (
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
    FindingOut,
    FunnelStatsOut,
    InsightOut,
    MatchOut,
    QuantitativeLedgerOut,
    ScoutContinueRequest,
    ScoutRunResponse,
    SafetySignalOut,
    SearchTraceOut,
    PrecedentOut,
    VariableOut,
)
from api.streaming import run_with_progress

router = APIRouter()


def _response_from_result(
    result: ScoutResult,
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> ScoutRunResponse:
    match_dicts = matches_to_dicts(result.matches)
    assessment_dicts = assessments_to_dicts(result.assessments)
    precedent_dicts = precedents_to_dicts(result.precedents)
    return ScoutRunResponse(
        phase=result.phase,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
        context_validation=DocumentContextValidationOut.model_validate(
            asdict(result.context_validation)
        ),
        quantitative_ledger=QuantitativeLedgerOut.model_validate(
            asdict(result.quantitative_ledger)
        ),
        variables=[VariableOut.model_validate(asdict(item)) for item in result.variables],
        search_plan=[SearchTraceOut.model_validate(asdict(item)) for item in result.search_plan],
        matches=[
            MatchOut(
                insight=InsightOut(
                    id=item["insight"].get("id", ""),
                    statement=item["insight"]["statement"],
                    query=item["insight"]["query"],
                    query_tracks=item["insight"].get("query_tracks", []),
                    retrieval_target_ids=item["insight"].get("retrieval_target_ids", []),
                    supporting_findings=[
                        FindingOut(**finding)
                        for finding in item["insight"]["supporting_findings"]
                    ],
                    org=item["insight"].get("org"),
                    source_type=item["insight"].get("source_type"),
                    intervention_class=item["insight"].get("intervention_class"),
                    indication=item["insight"].get("indication"),
                    attribute_ref=item["insight"].get("attribute_ref"),
                ),
                relation=item["relation"],
                reason=item["reason"],
                doc_block_ids=item.get("doc_block_ids", []),
            )
            for item in match_dicts
        ],
        assessments=[
            EvidenceAssessmentOut(
                attribute_ref=item["attribute_ref"],
                strength=item["strength"],
                reason=item["reason"],
                doc_target=item.get("doc_target", ""),
                doc_block_ids=item.get("doc_block_ids", []),
                supporting_insight_ids=item.get("supporting_insight_ids", []),
                supporting_findings=[
                    FindingOut(**finding) for finding in item["supporting_findings"]
                ],
            )
            for item in assessment_dicts
        ],
        conformity=[ConformityOut(**item) for item in conformity_to_dicts(result.conformity)],
        precedents=[
            PrecedentOut(
                attribute_ref=item["attribute_ref"],
                precedent=item["precedent"],
                outcome=item.get("outcome", "unknown"),
                reason=item["reason"],
                doc_block_ids=item.get("doc_block_ids", []),
                coverage_insight_ids=item.get("coverage_insight_ids", []),
                outcome_insight_ids=item.get("outcome_insight_ids", []),
                supporting_insight_ids=item.get("supporting_insight_ids", []),
                supporting_findings=[
                    FindingOut(**finding) for finding in item["supporting_findings"]
                ],
            )
            for item in precedent_dicts
        ],
        development_landscape=[
            DevelopmentProgramOut(**item)
            for item in development_programs_to_dicts(result.development_landscape)
        ],
        safety_signals=[
            SafetySignalOut(**item) for item in safety_signals_to_dicts(result.safety_signals)
        ],
        stats=FunnelStatsOut.model_validate(asdict(result.stats)),
        blocks=[ContentBlockOut(**item) for item in blocks_to_dicts(result.blocks)],
    )


def _target_from_payload(payload) -> QuantitativeTarget:
    raw = payload.model_dump()
    raw["expression"] = NumericExpression(**raw["expression"])
    raw["semantic_profile"] = {
        name: SemanticSlot(**slot)
        for name, slot in raw["semantic_profile"].items()
    }
    raw["semantic_provenance"] = {
        name: [DocumentSpan(**span) for span in spans]
        for name, spans in raw["semantic_provenance"].items()
    }
    raw["provenance_spans"] = [
        DocumentSpan(**span) for span in raw["provenance_spans"]
    ]
    raw["field_links"] = [
        QuantitativeFieldLink(**link) for link in raw["field_links"]
    ]
    return QuantitativeTarget(**raw)


def _result_from_target_review(draft: ScoutRunResponse) -> ScoutResult:
    """Rehydrate only the portable, pre-retrieval Scout contract.

    This deliberately does not deserialize downstream judgments. A continuation
    request can contain only the target-review draft produced by ``/run``.
    """
    if draft.phase != "target_review":
        raise ValueError("Scout continuation requires a target-review draft")
    if any((draft.search_plan, draft.matches, draft.assessments, draft.conformity,
            draft.precedents, draft.development_landscape, draft.safety_signals)):
        raise ValueError("target-review draft cannot contain downstream results")

    targets = [_target_from_payload(item) for item in draft.quantitative_ledger.targets]
    targets_by_id = {item.id: item for item in targets}
    variables: list[Attribute] = []
    for item in draft.variables:
        raw = item.model_dump()
        variables.append(Attribute(
            name=raw["name"],
            description=raw["description"],
            block_ids=raw["block_ids"],
            document_target=raw["document_target"],
            document_spans=[DocumentSpan(**span) for span in raw["document_spans"]],
            definition_mode=raw["definition_mode"],
            target_resolved=raw["target_resolved"],
            target_resolution_reason=raw["target_resolution_reason"],
            evidence_domain=raw["evidence_domain"],
            entities=[EvidenceEntity(**entity) for entity in raw["entities"]],
            quantitative_target_ids=[
                target_id
                for target_id in raw["quantitative_target_ids"]
                if target_id in targets_by_id
            ],
            quantitative_statement_dispositions=[
                QuantitativeStatementDisposition(**disposition)
                for disposition in raw["quantitative_statement_dispositions"]
            ],
            quantitative_target_status=raw["quantitative_target_status"],
            quantitative_target_status_reason=raw["quantitative_target_status_reason"],
        ))

    blocks: list[ContentBlock] = []
    for item in draft.blocks:
        raw = item.model_dump()
        image = raw.pop("image", None)
        blocks.append(ContentBlock(
            **raw,
            image=ImageAsset(**image) if image else None,
        ))

    return ScoutResult(
        matches=[],
        assessments=[],
        stats=FunnelStats(**draft.stats.model_dump()),
        context_validation=DocumentContextValidation(
            **draft.context_validation.model_dump()
        ),
        quantitative_ledger=QuantitativeLedger(
            status=draft.quantitative_ledger.status,
            reason=draft.quantitative_ledger.reason,
            block_ids=list(draft.quantitative_ledger.block_ids),
            reviews=[
                QuantitativeLedgerReview(**review.model_dump())
                for review in draft.quantitative_ledger.reviews
            ],
            targets=targets,
        ),
        variables=variables,
        blocks=blocks,
        phase="target_review",
    )


@router.post("/run")
async def run_scout(
    files: list[UploadFile] = File(...),
    org: str = Form(...),
    source_type: str = Form(...),
    intervention_class: str = Form(...),
    indication: str = Form(...),
) -> StreamingResponse:
    try:
        config = find_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    temp_paths: list[str] = []
    doc_ids: list[str] = []
    used_doc_ids: set[str] = set()
    for upload in files:
        suffix = Path(upload.filename or "upload").suffix or ".docx"
        contents = await upload.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_paths.append(temp_file.name)
        base_doc_id = Path(upload.filename or "document").stem or "document"
        doc_id = base_doc_id
        suffix_number = 2
        while doc_id in used_doc_ids:
            doc_id = f"{base_doc_id}-{suffix_number}"
            suffix_number += 1
        used_doc_ids.add(doc_id)
        doc_ids.append(doc_id)

    def work(progress):
        try:
            openai_client = get_openai_client()
            result = run_pipeline(
                temp_paths,
                doc_ids=doc_ids,
                config=config,
                openai_client=openai_client,
                retrieval_runtime=get_search_runtime(openai_client),
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                quantitative_mapping_client=get_quantitative_anthropic_client(),
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
        prepared = _result_from_target_review(draft)
    except (LookupError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def work(progress):
        openai_client = get_openai_client()
        result = continue_pipeline(
            prepared,
            config=config,
            openai_client=openai_client,
            quantitative_mapping_client=get_quantitative_anthropic_client(),
            retrieval_runtime=get_search_runtime(openai_client),
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
