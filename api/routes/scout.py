"""Scout route - uploaded docs + 4 primitives -> Matches, streaming progress."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.scout import (
    Attribute,
    EvidenceEntity,
    Insight,
    QuantitativeTarget,
    assessments_to_dicts,
    blocks_to_dicts,
    conformity_to_dicts,
    development_programs_to_dicts,
    find_config,
    matches_to_dicts,
    precedents_to_dicts,
    recalculate_conformity,
    safety_signals_to_dicts,
    run_pipeline,
)
from services.chunker import ContentBlock, ImageAsset
from services.searcher import (
    DevelopmentRecord,
    Finding,
    RetrievalPath,
    SafetyRecord,
    SourceAttribution,
)

from api.deps import get_openai_client, get_search_runtime
from api.schemas import (
    ConformityOut,
    ContentBlockOut,
    DevelopmentProgramOut,
    DocumentContextValidationOut,
    EvidenceAssessmentOut,
    EvidenceEntityOut,
    FindingOut,
    FunnelStatsOut,
    InsightOut,
    MatchOut,
    QuantitativeTargetOut,
    ScoutRunResponse,
    ScoutRecalibrationRequest,
    ScoutRecalibrationResponse,
    SafetySignalOut,
    SearchTraceOut,
    PrecedentOut,
    VariableOut,
)
from api.streaming import run_with_progress

router = APIRouter()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _finding_from_wire(finding: FindingOut) -> Finding:
    """Rehydrate the current wire contract without inferring absent provenance."""
    retrieved_at = _parse_datetime(finding.retrieved_at)
    if retrieved_at is None:
        raise ValueError(f"finding {finding.url!r} has no retrieval timestamp")
    return Finding(
        url=finding.url,
        title=finding.title,
        query=finding.query,
        retrieved_at=retrieved_at,
        excerpt=finding.excerpt,
        published_at=_parse_datetime(finding.published_at),
        source=finding.source,
        evidence_role=finding.evidence_role,
        development_records=[
            DevelopmentRecord(**record.model_dump())
            for record in finding.development_records
        ],
        safety_records=[
            SafetyRecord(**record.model_dump()) for record in finding.safety_records
        ],
        queries=finding.queries,
        source_lanes=finding.source_lanes,
        source_labels=finding.source_labels,
        source_attributions={
            key: SourceAttribution(**attribution.model_dump())
            for key, attribution in finding.source_attributions.items()
        },
        retrieval_paths=[
            RetrievalPath(**path.model_dump()) for path in finding.retrieval_paths
        ],
        title_source_lane=finding.title_source_lane,
        excerpt_source_lane=finding.excerpt_source_lane,
        published_source_lane=finding.published_source_lane,
    )


def _recalibration_inputs(
    result: ScoutRunResponse,
) -> tuple[list[Attribute], list[ContentBlock], list[Insight]]:
    attributes = [
        Attribute(
            name=variable.name,
            description=variable.description,
            block_ids=variable.block_ids,
            document_target=variable.document_target,
            definition_mode=variable.definition_mode,
            target_resolved=variable.target_resolved,
            evidence_domain=variable.evidence_domain,
            entities=[
                EvidenceEntity(**entity.model_dump()) for entity in variable.entities
            ],
            quantitative_target_status=variable.quantitative_target_status,
            quantitative_target_status_reason=variable.quantitative_target_status_reason,
            quantitative_targets=[
                QuantitativeTarget(**target.model_dump())
                for target in variable.quantitative_targets
            ],
        )
        for variable in result.variables
    ]
    blocks = [
        ContentBlock(
            id=block.id,
            doc_id=block.doc_id,
            ordinal=block.ordinal,
            block_type=block.block_type,
            content=block.content,
            heading_stack=block.heading_stack,
            structural_meta=block.structural_meta,
            style_hint=block.style_hint,
            section_label=block.section_label,
            image=ImageAsset(**block.image.model_dump()) if block.image else None,
            org=result.org,
            source_type=result.source_type,
            intervention_class=result.intervention_class,
            indication=result.indication,
        )
        for block in result.blocks
    ]
    insights: list[Insight] = []
    seen_insights: set[str] = set()
    for match in result.matches:
        item = match.insight
        identity = item.id or "\n".join((item.attribute_ref or "", item.statement))
        if identity in seen_insights:
            continue
        seen_insights.add(identity)
        insights.append(
            Insight(
                id=item.id,
                statement=item.statement,
                query=item.query,
                query_tracks=item.query_tracks,
                retrieval_target_ids=item.retrieval_target_ids,
                supporting_findings=[
                    _finding_from_wire(finding)
                    for finding in item.supporting_findings
                ],
                org=item.org,
                source_type=item.source_type,
                intervention_class=item.intervention_class,
                indication=item.indication,
                attribute_ref=item.attribute_ref,
            )
        )
    return attributes, blocks, insights


@router.post("/recalibrate")
async def recalibrate_scout(payload: ScoutRecalibrationRequest) -> StreamingResponse:
    """Rebuild quantitative ledgers from saved blocks and cited evidence only."""
    result = payload.result
    try:
        find_config(result.org, result.source_type, result.intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not result.blocks:
        raise HTTPException(
            status_code=422,
            detail="This result has no portable source blocks; rerun Scout to recalibrate it.",
        )
    attributes, blocks, insights = _recalibration_inputs(result)

    def work(progress):
        scores = recalculate_conformity(
            attributes,
            blocks,
            insights,
            openai_client=get_openai_client(),
            indication=result.indication,
            intervention_class=result.intervention_class,
            progress_callback=progress,
        )
        return ScoutRecalibrationResponse(
            conformity=[ConformityOut(**score) for score in conformity_to_dicts(scores)]
        ).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")


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
            development_program_dicts = development_programs_to_dicts(
                result.development_landscape
            )
            safety_signal_dicts = safety_signals_to_dicts(result.safety_signals)
            # Units actually investigated (vocabulary for TPP, extracted for IPDP) -
            # read from the result, not re-derived from the shared vocabulary.
            variables = result.variables
            return ScoutRunResponse(
                org=org,
                source_type=source_type,
                intervention_class=intervention_class,
                indication=indication,
                context_validation=DocumentContextValidationOut(
                    status=result.context_validation.status,
                    configured_indication=result.context_validation.configured_indication,
                    document_indication=result.context_validation.document_indication,
                    reason=result.context_validation.reason,
                    doc_block_ids=result.context_validation.doc_block_ids,
                ),
                variables=[
                    VariableOut(
                        name=variable.name,
                        description=variable.description,
                        block_ids=variable.block_ids,
                        document_target=variable.document_target,
                        definition_mode=variable.definition_mode,
                        target_resolved=variable.target_resolved,
                        evidence_domain=variable.evidence_domain,
                        quantitative_target_status=variable.quantitative_target_status,
                        quantitative_target_status_reason=variable.quantitative_target_status_reason,
                        entities=[
                            EvidenceEntityOut(
                                name=entity.name,
                                entity_type=entity.entity_type,
                                identifier=entity.identifier,
                            )
                            for entity in variable.entities
                        ],
                        quantitative_targets=[
                            QuantitativeTargetOut.model_validate(asdict(target))
                            for target in variable.quantitative_targets
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
                        target_ids=trace.target_ids,
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
                            retrieval_target_ids=md["insight"].get(
                                "retrieval_target_ids", []
                            ),
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
                conformity=[ConformityOut(**score) for score in conformity_dicts],
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
                development_landscape=[
                    DevelopmentProgramOut(**program)
                    for program in development_program_dicts
                ],
                safety_signals=[
                    SafetySignalOut(**signal) for signal in safety_signal_dicts
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
