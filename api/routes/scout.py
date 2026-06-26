"""Scout route - uploaded docs + 4 primitives -> Matches, streaming progress."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.scout import (
    assessments_to_dicts,
    conformity_to_dicts,
    find_config,
    load_attributes,
    matches_to_dicts,
    precedents_to_dicts,
    run_pipeline,
)

from api.deps import get_openai_client
from api.schemas import (
    ConformityOut,
    EvidenceAssessmentOut,
    FindingOut,
    FunnelStatsOut,
    InsightOut,
    MatchOut,
    MeasurementOut,
    ScoutRunResponse,
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
    for upload in files:
        suffix = Path(upload.filename or "upload").suffix or ".docx"
        contents = await upload.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_paths.append(temp_file.name)

    def work(progress):
        try:
            openai_client = get_openai_client()
            result = run_pipeline(
                temp_paths,
                config=config,
                openai_client=openai_client,
                search_client=openai_client,
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
            variables = load_attributes(intervention_class)
            return ScoutRunResponse(
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                variables=[
                    VariableOut(name=variable.name, description=variable.description)
                    for variable in variables
                ],
                matches=[
                    MatchOut(
                        insight=InsightOut(
                            statement=md["insight"]["statement"],
                            query=md["insight"]["query"],
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
                    )
                    for md in match_dicts
                ],
                assessments=[
                    EvidenceAssessmentOut(
                        attribute_ref=assessment["attribute_ref"],
                        strength=assessment["strength"],
                        basis=assessment["basis"],
                        reason=assessment["reason"],
                        doc_target=assessment.get("doc_target", ""),
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
                        reason=signal["reason"],
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
            ).model_dump()
        finally:
            for path in temp_paths:
                if os.path.exists(path):
                    os.unlink(path)

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
