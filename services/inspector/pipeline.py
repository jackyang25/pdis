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
    GAP_VERDICTS,
    InspectionConfig,
    InspectionResult,
    LLMClientProtocol,
    SectionGrade,
    TopIssue,
    VariableSpec,
)

DEFAULT_MAX_OUTPUT_TOKENS = 32000

# Ranking is the verdict itself. It used to be a letter that this table then
# converted into an order, so what a reader saw ranked first was one lookup away
# from anything the model actually said.
SEVERITY_RANK = {"critical": 1, "for_consideration": 2}
UNRANKED_SEVERITY = 3
# An absence outranks any assessed gap: there is nothing to read at all.
MISSING_SECTION_RANK = -1
MISSING_VARIABLE_RANK = 0
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
    """Assemble the section assessments into one report.

    There is no document-level verdict to compute. The document publishes the
    gaps its sections found, counted by severity, so every number a reader sees
    can be traced to rows they can open.
    """
    doc_id = labeled_blocks[0].doc_id if labeled_blocks else ""
    return InspectionResult(
        doc_id=doc_id,
        top_issues=_top_issues(section_grades, config),
        section_grades=section_grades,
        grading_status="complete",
    )


def _top_issues(
    section_grades: list[SectionGrade],
    config: InspectionConfig,
    limit: int = TOP_ISSUE_LIMIT,
) -> list[TopIssue]:
    """Rank the most severe issues across sections, variables, and dimensions.

    Severity is the dimension's own verdict; an absent section or variable
    outranks any assessed gap because there is nothing to read at all. Ties break
    on the rubric's authored section weight, which is where the author's sense of
    what matters most now applies — it previously weighted an average of letters.

    Each result keeps its parts - section, variable, dimension, severity,
    presence, recommendation, lineage - so a consumer can link, filter, or
    re-sort without parsing a sentence back apart.
    """
    weights_by_section = {section.name: section.weight for section in config.sections}
    candidates: list[tuple[int, float, TopIssue]] = []
    for section in section_grades:
        if not section.is_present:
            candidates.append((
                MISSING_SECTION_RANK,
                -weights_by_section.get(section.section_name, 0.0),
                TopIssue(
                    section_name=section.section_name,
                    issue="Required section is not present.",
                    severity="critical",
                    recommendation="; ".join(
                        assessment.recommendation
                        for assessment in section.dimensions.values()
                        if assessment.recommendation
                    ),
                ),
            ))
            continue

        absent = set(section.missing_variables)
        for variable_name in section.missing_variables:
            candidates.append((
                MISSING_VARIABLE_RANK,
                -weights_by_section.get(section.section_name, 0.0),
                TopIssue(
                    section_name=section.section_name,
                    variable_name=variable_name,
                    issue="Required variable is not present.",
                    dimension="completeness",
                    severity="critical",
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
                    assessment = variable.dimensions.get(dimension)
                    if assessment is None or assessment.verdict not in GAP_VERDICTS:
                        continue
                    for issue in assessment.issues:
                        candidates.append((
                            SEVERITY_RANK.get(assessment.verdict, UNRANKED_SEVERITY),
                            -weights_by_section.get(section.section_name, 0.0),
                            TopIssue(
                                section_name=section.section_name,
                                variable_name=variable.variable_name,
                                issue=issue,
                                dimension=dimension,
                                severity=assessment.verdict,
                                content_status=variable.content_status,
                                recommendation=assessment.recommendation,
                                cited_block_ids=list(assessment.cited_block_ids),
                            ),
                        ))
        else:
            for dimension in DIMENSIONS:
                assessment = section.dimensions.get(dimension)
                if assessment is None or assessment.verdict not in GAP_VERDICTS:
                    continue
                for issue in assessment.issues:
                    candidates.append((
                        SEVERITY_RANK.get(assessment.verdict, UNRANKED_SEVERITY),
                        -weights_by_section.get(section.section_name, 0.0),
                        TopIssue(
                            section_name=section.section_name,
                            issue=issue,
                            dimension=dimension,
                            severity=assessment.verdict,
                            recommendation=assessment.recommendation,
                            cited_block_ids=list(assessment.cited_block_ids),
                        ),
                    ))

    seen: set[tuple[str, str | None, str | None, str]] = set()
    ranked: list[TopIssue] = []
    for *_, issue in sorted(candidates, key=lambda item: item[:2]):
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
