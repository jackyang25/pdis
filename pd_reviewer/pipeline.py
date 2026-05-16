from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from chunker.stages.mapper import label_blocks
from chunker.models import ContentBlock, load_config as load_chunker_config
from chunker.stages.parser import parse_document

from .stages.grader import grade_sections
from .models import (
    BatchReviewResult,
    Grade,
    LLMClientProtocol,
    ReviewConfig,
    ReviewResult,
    SectionGrade,
    VariableSpec,
)

DEFAULT_MAX_OUTPUT_TOKENS = 32000

GRADE_TO_SCORE = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
SEVERITY_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4, "N/A": 5}
MISSING_SECTION_SEVERITY = -2
MISSING_VARIABLE_SEVERITY = -1


def run_pipeline(
    file_path: str,
    *,
    config: ReviewConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> ReviewResult:
    """End-to-end PD document review: parse → label → grade → report."""
    source_path = Path(file_path)
    chunker_config = load_chunker_config(config.chunker_config_path)

    blocks = parse_document(str(source_path), doc_id=source_path.stem)
    labeled_blocks = label_blocks_via_client(
        blocks, chunker_config, llm_client, max_tokens=max_tokens
    )
    return review_blocks(
        labeled_blocks, config=config, llm_client=llm_client, max_tokens=max_tokens
    )


def review_blocks(
    blocks: list[ContentBlock],
    *,
    config: ReviewConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> ReviewResult:
    """Grade + report a document whose blocks have already been parsed and labeled."""
    section_grades = grade_sections(blocks, config, llm_client, max_tokens=max_tokens)
    return build_report_card(blocks, section_grades, config)


def run_pipeline_batch(
    jobs: list[tuple[str, str]],
    *,
    config: ReviewConfig,
    llm_client_factory,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchReviewResult]:
    """Run `run_pipeline` (parse → label → grade) over many documents in parallel.

    Args:
        jobs: list of (file_path, doc_key) pairs.
        llm_client_factory: zero-arg callable returning a fresh LLMClient per worker.

    Returns:
        list[BatchReviewResult] in the same order as `jobs`.
    """
    if not jobs:
        return []
    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda job: _run_pipeline_one_batch(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    max_tokens=max_tokens,
                ),
                jobs,
            )
        )


def _run_pipeline_one_batch(
    file_path: str,
    doc_key: str,
    *,
    config: ReviewConfig,
    llm_client_factory,
    max_tokens: int,
) -> BatchReviewResult:
    try:
        llm_client = llm_client_factory()
        review = run_pipeline(
            file_path, config=config, llm_client=llm_client, max_tokens=max_tokens
        )
        review.doc_id = doc_key
        return BatchReviewResult(doc_key=doc_key, review=review)
    except Exception as exc:
        return BatchReviewResult(doc_key=doc_key, error=str(exc))


def review_blocks_batch(
    jobs: list[tuple[str, list[ContentBlock]]],
    *,
    config: ReviewConfig,
    llm_client_factory,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchReviewResult]:
    """Run `review_blocks` over many already-parsed documents in parallel.

    Args:
        jobs: list of (doc_key, blocks) pairs.
        llm_client_factory: zero-arg callable returning a fresh LLMClient per worker.

    Returns:
        list[BatchReviewResult] in the same order as `jobs`.
    """
    if not jobs:
        return []
    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda job: _review_one_batch(
                    job[0],
                    job[1],
                    config=config,
                    llm_client_factory=llm_client_factory,
                    max_tokens=max_tokens,
                ),
                jobs,
            )
        )


def _review_one_batch(
    doc_key: str,
    blocks: list[ContentBlock],
    *,
    config: ReviewConfig,
    llm_client_factory,
    max_tokens: int,
) -> BatchReviewResult:
    try:
        llm_client = llm_client_factory()
        review = review_blocks(
            blocks, config=config, llm_client=llm_client, max_tokens=max_tokens
        )
        return BatchReviewResult(doc_key=doc_key, review=review)
    except Exception as exc:
        return BatchReviewResult(doc_key=doc_key, error=str(exc))


def label_blocks_via_client(
    blocks: list[ContentBlock],
    chunker_config,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> list[ContentBlock]:
    """Label blocks through the chunker's provider-neutral mapper path."""
    return label_blocks(blocks, chunker_config, llm_client, max_tokens=max_tokens)


def build_report_card(
    labeled_blocks: list[ContentBlock],
    section_grades: list[SectionGrade],
    config: ReviewConfig,
) -> ReviewResult:
    """Roll section grades up into a full report card."""
    doc_id = labeled_blocks[0].doc_id if labeled_blocks else ""
    return ReviewResult(
        doc_id=doc_id,
        overall_grade=_overall_grade(section_grades, config),
        top_issues=_top_issues(section_grades, config),
        section_grades=section_grades,
    )


def _overall_grade(
    section_grades: list[SectionGrade],
    config: ReviewConfig,
) -> Grade:
    weighted_score = 0.0
    applied_weight = 0.0
    grades_by_section = {grade.section_name: grade.grade for grade in section_grades}

    for section_spec in config.sections:
        grade = grades_by_section.get(section_spec.name)
        if grade == "N/A" or grade not in GRADE_TO_SCORE:
            continue
        weighted_score += GRADE_TO_SCORE[grade] * section_spec.weight
        applied_weight += section_spec.weight

    if applied_weight == 0:
        return "N/A"
    return _score_to_grade(weighted_score / applied_weight)


def _score_to_grade(score: float) -> Grade:
    if score >= 3.5:
        return "A"
    if score >= 2.5:
        return "B"
    if score >= 1.5:
        return "C"
    if score >= 0.5:
        return "D"
    return "F"


def _top_issues(
    section_grades: list[SectionGrade],
    config: ReviewConfig,
    limit: int = 5,
) -> list[str]:
    issue_candidates: list[tuple[int, str]] = []
    for section_grade in section_grades:
        if not section_grade.is_present:
            issue_candidates.append(
                (
                    MISSING_SECTION_SEVERITY,
                    (
                        f"{section_grade.section_name} missing - "
                        f"{section_grade.recommendation}"
                    ),
                )
            )
            continue

        for variable_name in section_grade.missing_variables:
            issue_candidates.append(
                (
                    MISSING_VARIABLE_SEVERITY,
                    _format_missing_variable_issue(
                        variable_name,
                        section_grade.section_name,
                        config,
                    ),
                )
            )

        issue_candidates.append(
            (
                SEVERITY_ORDER.get(section_grade.grade, 5),
                _format_issue(
                    section_grade.section_name,
                    section_grade.grade,
                    section_grade.issues,
                    section_grade.recommendation,
                ),
            )
        )
        for variable_grade in section_grade.variable_grades:
            issue_candidates.append(
                (
                    SEVERITY_ORDER.get(variable_grade.grade, 5),
                    _format_issue(
                        variable_grade.variable_name,
                        variable_grade.grade,
                        variable_grade.issues,
                        variable_grade.recommendation,
                    ),
                )
            )

    ranked_issues = [
        issue
        for _, issue in sorted(issue_candidates, key=lambda item: item[0])
        if issue
    ]
    return ranked_issues[:limit]


def _format_missing_variable_issue(
    variable_name: str,
    section_name: str,
    config: ReviewConfig,
) -> str:
    recommendation = _missing_variable_recommendation(variable_name, section_name, config)
    return f"{variable_name} missing - {recommendation}"


def _missing_variable_recommendation(
    variable_name: str,
    section_name: str,
    config: ReviewConfig,
) -> str:
    variable_spec = _find_variable_spec(variable_name, section_name, config)
    if variable_spec is not None:
        return f"Add this required variable: {variable_spec.description}"
    return "Add the required variable with minimum, optimistic, and annotation details."


def _find_variable_spec(
    variable_name: str,
    section_name: str,
    config: ReviewConfig,
) -> VariableSpec | None:
    for section_spec in config.sections:
        if section_spec.name != section_name:
            continue
        for variable_spec in section_spec.variables:
            if variable_spec.name == variable_name:
                return variable_spec
    return None


def _format_issue(
    name: str,
    grade: Grade,
    issues: list[str],
    recommendation: str,
) -> str:
    if grade in {"A", "B", "N/A"} and not issues:
        return ""
    first_issue = issues[0] if issues else "No specific issue provided."
    return f"{name} ({grade}) - {first_issue} {recommendation}".strip()
