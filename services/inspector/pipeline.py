from __future__ import annotations

from pathlib import Path

from shared.batching import map_ordered

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from .stages.grader import check_cross_section, grade_sections
from .contract import validate_result_contract
from .models import (
    ABSENT_CONTENT_STATUS,
    BatchInspectionResult,
    DIMENSIONS,
    DimensionGrade,
    GRADE_TO_SCORE,
    Grade,
    InspectionConfig,
    InspectionResult,
    LLMClientProtocol,
    SectionGrade,
    TopIssue,
    VariableSpec,
    score_to_grade,
)

DEFAULT_MAX_OUTPUT_TOKENS = 32000

SEVERITY_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4, "N/A": 5}
MISSING_SECTION_SEVERITY = -2
MISSING_VARIABLE_SEVERITY = -1
TOP_ISSUE_LIMIT = 5


def run_pipeline(
    file_path: str,
    *,
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
    doc_id: str | None = None,
) -> InspectionResult:
    """End-to-end document inspection: parse → label → grade → report.

    `doc_id` is stamped on every block. Pass the original filename stem
    when `file_path` points to a temp file (e.g., from an HTTP upload),
    so block ids don't end up prefixed with the temp filename.
    """
    source_path = Path(file_path)
    resolved_doc_id = doc_id or source_path.stem
    chunker_config = find_chunker_config(
        config.org, config.source_type, config.intervention_class
    )
    # Delegate parse + label to chunker via its public surface
    labeled_blocks = chunker_run_pipeline(
        str(source_path),
        doc_id=resolved_doc_id,
        config=chunker_config,
        llm_client=llm_client,
        max_tokens=max_tokens,
        indication=indication,
        progress_callback=progress_callback,
    )
    return inspect_blocks(
        labeled_blocks,
        config=config,
        llm_client=llm_client,
        indication=indication,
        max_tokens=max_tokens,
        progress_callback=progress_callback,
    )


def inspect_blocks(
    blocks: list[ContentBlock],
    *,
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
) -> InspectionResult:
    """Grade + report a document whose blocks have already been parsed and labeled.
    """
    if progress_callback:
        progress_callback("grade")
    section_grades = grade_sections(
        blocks,
        config,
        llm_client,
        max_tokens=max_tokens,
        progress=progress_callback,
    )
    result = build_report_card(blocks, section_grades, config)

    # Whole-document consistency pass - the one place that sees all sections at
    # once. Its explicit status distinguishes failure from a clean result.
    if progress_callback:
        progress_callback("consistency")
    result.cross_section_findings, result.consistency_status = check_cross_section(
        blocks, config, llm_client, max_tokens=max_tokens
    )

    result.org = config.org
    result.source_type = config.source_type
    result.intervention_class = config.intervention_class
    result.indication = indication
    result.blocks = blocks
    return validate_result_contract(result, config)


def run_pipeline_batch(
    jobs: list[tuple[str, str]],
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchInspectionResult]:
    """Run `run_pipeline` (parse → label → grade) over many documents in parallel."""
    return map_ordered(
        jobs,
        lambda job: _run_pipeline_one_batch(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    indication=indication,
                    max_tokens=max_tokens,
                ),
        workers=max_workers,
    )


def _run_pipeline_one_batch(
    file_path: str,
    doc_key: str,
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None,
    max_tokens: int,
) -> BatchInspectionResult:
    try:
        llm_client = llm_client_factory()
        inspection = run_pipeline(
            file_path,
            config=config,
            llm_client=llm_client,
            indication=indication,
            max_tokens=max_tokens,
        )
        inspection.doc_id = doc_key
        return BatchInspectionResult(doc_key=doc_key, inspection=inspection)
    except Exception as exc:
        return BatchInspectionResult(doc_key=doc_key, error=str(exc))


def inspect_blocks_batch(
    jobs: list[tuple[str, list[ContentBlock]]],
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchInspectionResult]:
    """Run `inspect_blocks` over many already-parsed documents in parallel.

    Args:
        jobs: list of (doc_key, blocks) pairs.
        llm_client_factory: zero-arg callable returning a fresh OpenAIClient per worker.

    Returns:
        list[BatchInspectionResult] in the same order as `jobs`.
    """
    return map_ordered(
        jobs,
        lambda job: _inspect_one_batch(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    indication=indication,
                    max_tokens=max_tokens,
                ),
        workers=max_workers,
    )


def _inspect_one_batch(
    doc_key: str,
    blocks: list[ContentBlock],
    *,
    config: InspectionConfig,
    llm_client_factory,
    indication: str | None,
    max_tokens: int,
) -> BatchInspectionResult:
    try:
        llm_client = llm_client_factory()
        inspection = inspect_blocks(
            blocks,
            config=config,
            llm_client=llm_client,
            indication=indication,
            max_tokens=max_tokens,
        )
        return BatchInspectionResult(doc_key=doc_key, inspection=inspection)
    except Exception as exc:
        return BatchInspectionResult(doc_key=doc_key, error=str(exc))




def build_report_card(
    labeled_blocks: list[ContentBlock],
    section_grades: list[SectionGrade],
    config: InspectionConfig,
) -> InspectionResult:
    """Roll section grades up into a full report card across three dimensions."""
    doc_id = labeled_blocks[0].doc_id if labeled_blocks else ""
    return InspectionResult(
        doc_id=doc_id,
        dimensions=_document_dimensions(section_grades, config),
        top_issues=_top_issues(section_grades, config),
        section_grades=section_grades,
        grading_status="complete",
    )


def _document_dimensions(
    section_grades: list[SectionGrade],
    config: InspectionConfig,
) -> dict[str, DimensionGrade]:
    """Weighted roll-up of section dimension grades into document-level dimensions.

    Weighted by authored section weight, unlike the unweighted variable-to-section
    roll-up in the grader. Both read one scale from `models`.
    """
    weights_by_section = {s.name: s.weight for s in config.sections}
    out: dict[str, DimensionGrade] = {}
    for name in DIMENSIONS:
        weighted_score = 0.0
        applied_weight = 0.0
        issues: list[str] = []
        recs: list[str] = []
        for sg in section_grades:
            dg = sg.dimensions.get(name)
            if dg is None:
                continue
            issues.extend(dg.issues)
            if dg.recommendation:
                recs.append(dg.recommendation)
            if dg.grade == "N/A" or dg.grade not in GRADE_TO_SCORE:
                continue
            weight = weights_by_section.get(sg.section_name, 0.0)
            weighted_score += GRADE_TO_SCORE[dg.grade] * weight
            applied_weight += weight
        grade: Grade = score_to_grade(
            weighted_score / applied_weight if applied_weight > 0 else None
        )
        out[name] = DimensionGrade(
            grade=grade,
            issues=issues,
            recommendation="; ".join(dict.fromkeys(recs)),
        )
    return out


def _top_issues(
    section_grades: list[SectionGrade],
    config: InspectionConfig,
    limit: int = TOP_ISSUE_LIMIT,
) -> list[TopIssue]:
    """Rank the most severe issues across sections, variables, and dimensions.

    Severity comes from the dimension grade; an absent section or variable ranks
    above any letter grade. Each result keeps its parts - section, variable,
    dimension, grade, presence, recommendation, lineage - so a consumer can link,
    filter, or re-sort without parsing a sentence back apart.
    """
    candidates: list[tuple[int, TopIssue]] = []
    for section in section_grades:
        if not section.is_present:
            candidates.append((
                MISSING_SECTION_SEVERITY,
                TopIssue(
                    section_name=section.section_name,
                    issue="Required section is not present.",
                    grade="F",
                    recommendation="; ".join(
                        grade.recommendation
                        for grade in section.dimensions.values()
                        if grade.recommendation
                    ),
                ),
            ))
            continue

        absent = set(section.missing_variables)
        for variable_name in section.missing_variables:
            candidates.append((
                MISSING_VARIABLE_SEVERITY,
                TopIssue(
                    section_name=section.section_name,
                    variable_name=variable_name,
                    issue="Required variable is not present.",
                    dimension="completeness",
                    grade="F",
                    content_status=ABSENT_CONTENT_STATUS,
                    recommendation=_missing_variable_recommendation(
                        variable_name, section.section_name, config
                    ),
                ),
            ))

        if section.variable_grades:
            for variable in section.variable_grades:
                if variable.variable_name in absent:
                    continue
                for dimension in DIMENSIONS:
                    grade = variable.dimensions.get(dimension)
                    if grade is None:
                        continue
                    for issue in grade.issues:
                        candidates.append((
                            SEVERITY_ORDER.get(grade.grade, 5),
                            TopIssue(
                                section_name=section.section_name,
                                variable_name=variable.variable_name,
                                issue=issue,
                                dimension=dimension,
                                grade=grade.grade,
                                content_status=variable.content_status,
                                recommendation=grade.recommendation,
                                cited_block_ids=list(grade.cited_block_ids),
                            ),
                        ))
        else:
            for dimension in DIMENSIONS:
                grade = section.dimensions.get(dimension)
                if grade is None:
                    continue
                for issue in grade.issues:
                    candidates.append((
                        SEVERITY_ORDER.get(grade.grade, 5),
                        TopIssue(
                            section_name=section.section_name,
                            issue=issue,
                            dimension=dimension,
                            grade=grade.grade,
                            recommendation=grade.recommendation,
                            cited_block_ids=list(grade.cited_block_ids),
                        ),
                    ))

    seen: set[tuple[str, str | None, str | None, str]] = set()
    ranked: list[TopIssue] = []
    for _, issue in sorted(candidates, key=lambda item: item[0]):
        identity = (
            issue.section_name,
            issue.variable_name,
            issue.dimension,
            issue.issue,
        )
        if not issue.issue or identity in seen:
            continue
        seen.add(identity)
        ranked.append(issue)
        if len(ranked) >= limit:
            break
    return ranked


def _missing_variable_recommendation(
    variable_name: str,
    section_name: str,
    config: InspectionConfig,
) -> str:
    variable_spec = _find_variable_spec(variable_name, section_name, config)
    if variable_spec is not None:
        return f"Add this required variable: {variable_spec.description}"
    return "Add the required variable with minimum, optimistic, and annotation details."


def _find_variable_spec(
    variable_name: str,
    section_name: str,
    config: InspectionConfig,
) -> VariableSpec | None:
    for section_spec in config.sections:
        if section_spec.name != section_name:
            continue
        for variable_spec in section_spec.variables:
            if variable_spec.name == variable_name:
                return variable_spec
    return None
