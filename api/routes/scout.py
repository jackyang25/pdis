"""Scout route - uploaded docs + 4 primitives -> Matches, streaming progress."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.scout import (
    assessments_to_dicts,
    blocks_to_dicts,
    conformity_to_dicts,
    find_config,
    matches_to_dicts,
    precedents_to_dicts,
    run_pipeline,
)

from api.deps import get_openai_client, get_search_runtime
from api.schemas import (
    ConformityOut,
    ContentBlockOut,
    EvidenceAssessmentOut,
    EvidenceEntityOut,
    FindingOut,
    FunnelStatsOut,
    InsightOut,
    MatchOut,
    MeasurementOut,
    ScoutRunResponse,
    SearchTraceOut,
    PrecedentOut,
    VariableOut,
)
from api.streaming import run_with_progress

router = APIRouter()


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
                progress_callback=progress,
            )
            match_dicts = matches_to_dicts(result.matches)
            assessment_dicts = assessments_to_dicts(result.assessments)
            conformity_dicts = conformity_to_dicts(result.conformity)
            precedent_dicts = precedents_to_dicts(result.precedents)
            # Units actually investigated (vocabulary for TPP, extracted for IPDP) -
            # read from the result, not re-derived from the shared vocabulary.
            variables = result.variables
            return ScoutRunResponse(
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                variables=[
                    VariableOut(
                        name=variable.name,
                        description=variable.description,
                        block_ids=variable.block_ids,
                        document_target=variable.document_target,
                        definition_mode=variable.definition_mode,
                        target_resolved=variable.target_resolved,
                        evidence_domain=variable.evidence_domain,
                        entities=[
                            EvidenceEntityOut(
                                name=entity.name,
                                entity_type=entity.entity_type,
                                identifier=entity.identifier,
                            )
                            for entity in variable.entities
                        ],
                    )
                    for variable in variables
                ],
                search_plan=[
                    SearchTraceOut(
                        attribute_ref=trace.attribute_ref,
                        lane=trace.lane,
                        query=trace.query,
                        connector=trace.connector,
                        operation=trace.operation,
                        request_options=trace.request_options,
                        tracks=trace.tracks,
                        doc_block_ids=trace.doc_block_ids,
                        intent_ids=trace.intent_ids,
                        input_queries=trace.input_queries,
                        applicability=trace.applicability,
                        applicability_reason=trace.applicability_reason,
                        status=trace.status,
                        error=trace.error,
                        finding_count=trace.finding_count,
                        source_urls=trace.source_urls,
                    )
                    for trace in result.search_plan
                ],
                matches=[
                    MatchOut(
                        insight=InsightOut(
                            id=md["insight"].get("id", ""),
                            statement=md["insight"]["statement"],
                            query=md["insight"]["query"],
                            query_tracks=md["insight"].get("query_tracks", []),
                            supporting_findings=[
                                FindingOut(**f)
                                for f in md["insight"]["supporting_findings"]
                            ],
                            org=md["insight"].get("org"),
                            source_type=md["insight"].get("source_type"),
                            intervention_class=md["insight"].get(
                                "intervention_class"
                            ),
                            indication=md["insight"].get("indication"),
                            attribute_ref=md["insight"].get("attribute_ref"),
                        ),
                        relation=md["relation"],
                        reason=md["reason"],
                        doc_block_ids=md.get("doc_block_ids", []),
                    )
                    for md in match_dicts
                ],
                assessments=[
                    EvidenceAssessmentOut(
                        attribute_ref=assessment["attribute_ref"],
                        strength=assessment["strength"],
                        reason=assessment["reason"],
                        doc_target=assessment.get("doc_target", ""),
                        doc_block_ids=assessment.get("doc_block_ids", []),
                        supporting_insight_ids=assessment.get(
                            "supporting_insight_ids", []
                        ),
                        supporting_findings=[
                            FindingOut(**finding)
                            for finding in assessment["supporting_findings"]
                        ],
                    )
                    for assessment in assessment_dicts
                ],
                conformity=[
                    ConformityOut(
                        attribute_ref=score["attribute_ref"],
                        target_value=score["target_value"],
                        comparator=score["comparator"],
                        unit=score["unit"],
                        target_label=score["target_label"],
                        conformity=score["conformity"],
                        lower=score["lower"],
                        upper=score["upper"],
                        verdict=score["verdict"],
                        doc_block_ids=score.get("doc_block_ids", []),
                        measurements=[
                            MeasurementOut(**m) for m in score["measurements"]
                        ],
                    )
                    for score in conformity_dicts
                ],
                precedents=[
                    PrecedentOut(
                        attribute_ref=signal["attribute_ref"],
                        precedent=signal["precedent"],
                        outcome=signal.get("outcome", "unknown"),
                        reason=signal["reason"],
                        doc_block_ids=signal.get("doc_block_ids", []),
                        coverage_insight_ids=signal.get(
                            "coverage_insight_ids", []
                        ),
                        outcome_insight_ids=signal.get("outcome_insight_ids", []),
                        supporting_insight_ids=signal.get(
                            "supporting_insight_ids", []
                        ),
                        supporting_findings=[
                            FindingOut(**finding)
                            for finding in signal["supporting_findings"]
                        ],
                    )
                    for signal in precedent_dicts
                ],
                stats=FunnelStatsOut(
                    queries=result.stats.queries,
                    findings=result.stats.findings,
                    unique_findings=result.stats.unique_findings,
                    insights=result.stats.insights,
                    matches=result.stats.matches,
                    assessments=result.stats.assessments,
                ),
                blocks=[
                    ContentBlockOut(**block) for block in blocks_to_dicts(result.blocks)
                ],
            ).model_dump()
        finally:
            for path in temp_paths:
                if os.path.exists(path):
                    os.unlink(path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
