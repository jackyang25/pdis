"""Inspector orchestration: parse once, assess every included rubric, check consistency."""

from __future__ import annotations

from pathlib import Path

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from .assembly import assess_sections, rank_assessments, rank_document_findings
from .contract import validate_aggregate_result_contract
from .configuration import (
    InspectionProfile,
    RubricResolution,
    profile_document_config,
    resolve_profile,
    validate_product_facts,
)
from .models import (
    AggregateInspectionResult,
    InspectionConfig,
    InspectionReview,
    RequirementSnapshot,
    RubricSnapshot,
    RubricSourceSnapshot,
    LLMClientProtocol,
)
from .stages.assessor import assess_rubrics, check_cross_section


def run_profile_pipeline(
    file_path: str,
    *,
    profile: InspectionProfile,
    applicability_facts: dict[str, str],
    llm_client: LLMClientProtocol,
    indication: str | None = None,
    progress_callback=None,
    doc_id: str | None = None,
) -> AggregateInspectionResult:
    """Parse once, then assess every rubric included by the profile.

    `doc_id` is stamped on every block. Pass the original filename stem when
    `file_path` points to a temp file (e.g., from an HTTP upload), so block ids
    don't end up prefixed with the temp filename. The profile is resolved before
    parsing, so a run with no included rubric is refused without spending a parse.
    """
    source_path = Path(file_path)
    facts = validate_product_facts(applicability_facts)
    resolutions = _included_resolutions(profile, facts)
    chunker_config = find_chunker_config(profile.org, profile.source_type, profile.intervention_class)
    blocks = chunker_run_pipeline(
        str(source_path), doc_id=doc_id or source_path.stem, config=chunker_config,
        llm_client=llm_client, indication=indication,
        progress_callback=progress_callback,
    )
    return _inspect(
        blocks, profile=profile, facts=facts, resolutions=resolutions,
        llm_client=llm_client, indication=indication,
        progress_callback=progress_callback,
    )


def inspect_blocks_with_profile(
    blocks: list[ContentBlock], *, profile: InspectionProfile,
    applicability_facts: dict[str, str], llm_client: LLMClientProtocol,
    indication: str | None = None, progress_callback=None,
) -> AggregateInspectionResult:
    """Assess already-parsed blocks against every rubric the profile includes."""
    facts = validate_product_facts(applicability_facts)
    return _inspect(
        blocks, profile=profile, facts=facts,
        resolutions=_included_resolutions(profile, facts),
        llm_client=llm_client, indication=indication,
        progress_callback=progress_callback,
    )


def _included_resolutions(profile: InspectionProfile, facts) -> list[RubricResolution]:
    resolutions = resolve_profile(profile, facts)
    if not any(item.status == "included" and item.rubric for item in resolutions):
        raise ValueError("Inspector profile resolved no included rubrics")
    return resolutions


def _inspect(
    blocks: list[ContentBlock], *, profile: InspectionProfile, facts,
    resolutions: list[RubricResolution], llm_client: LLMClientProtocol,
    indication: str | None, progress_callback,
) -> AggregateInspectionResult:
    included = [item for item in resolutions if item.status == "included" and item.rubric]
    reviews: list[InspectionReview] = []
    configs: dict[str, InspectionConfig] = {}
    assessed = assess_rubrics(
        blocks, [item.rubric.config for item in included], llm_client,
        indication=indication, progress=progress_callback,
    )
    worklist_lengths: list[int] = []
    for resolution, (findings, mapped) in zip(included, assessed):
        rubric = resolution.rubric
        assert rubric is not None
        prefix = rubric.id + "::"
        for item in findings:
            item.id = prefix + item.id
        sections = assess_sections(rubric.config, findings, mapped_blocks=mapped)
        worklist_lengths.append(len(rank_assessments(rubric.config, sections)))
        snapshot = _rubric_snapshot(rubric, sections)
        reviews.append(InspectionReview(rubric=snapshot, sections=sections))
        configs[rubric.id] = rubric.config
    if progress_callback:
        progress_callback("consistency")
    # Consistency is a property of the document, so it reads the document's own
    # template sections, whichever rubrics this profile happens to include.
    consistency = check_cross_section(blocks, profile_document_config(profile), llm_client)
    rank_document_findings(consistency.findings, after=max(worklist_lengths, default=0))
    result = AggregateInspectionResult(
        doc_id=blocks[0].doc_id if blocks else "", reviews=reviews,
        rubric_resolutions=[{
            "rubric_id": item.rubric_id, "display_name": item.display_name,
            "status": item.status, "reason_code": item.reason_code, "reason": item.reason,
        } for item in resolutions],
        applicability_facts=facts, document_findings=consistency.findings,
        consistency_status=consistency.status,
        consistency_failure_code=consistency.failure_code, org=profile.org,
        source_type=profile.source_type, intervention_class=profile.intervention_class,
        indication=indication, blocks=blocks,
    )
    return validate_aggregate_result_contract(result, configs)


def _rubric_snapshot(rubric, sections) -> RubricSnapshot:
    spec_by_key = {}
    for section in rubric.config.sections:
        if section.variables:
            for variable in section.variables:
                spec_by_key[(section.name, variable.name)] = variable
        else:
            spec_by_key[(section.name, None)] = section
    requirements = []
    for section in sections:
        for unit in section.units:
            spec = spec_by_key[(section.section_name, unit.variable_name)]
            requirements.append(RequirementSnapshot(
                id=unit.id, section_name=section.section_name,
                variable_name=unit.variable_name, description=spec.description,
                expectations=spec.expectations, source_refs=list(spec.source_refs),
            ))
    return RubricSnapshot(
        id=rubric.id, revision=rubric.revision, display_name=rubric.display_name,
        updated_on=rubric.updated_on,
        authority=rubric.authority, scope=rubric.scope,
        stage_guidance=rubric.config.stage_guidance,
        mirrors=rubric.config.mirrors or None,
        reference_url=rubric.reference_url,
        evidence_scope=rubric.evidence_scope,
        sources=[RubricSourceSnapshot(**source.__dict__) for source in rubric.sources],
        requirements=requirements,
    )
