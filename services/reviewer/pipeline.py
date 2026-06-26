from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from .stages.grader import check_cross_section, grade_sections
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
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
    doc_id: str | None = None,
) -> ReviewResult:
    """End-to-end PD document review: parse → label → grade → report.

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
        progress_callback=progress_callback,
    )
    return review_blocks(
        labeled_blocks,
        config=config,
        llm_client=llm_client,
        indication=indication,
        max_tokens=max_tokens,
        progress_callback=progress_callback,
    )


def review_blocks(
    blocks: list[ContentBlock],
    *,
    config: ReviewConfig,
    llm_client: LLMClientProtocol,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
) -> ReviewResult:
    """Grade + report a document whose blocks have already been parsed and labeled.
    """
    if progress_callback:
        progress_callback("grade")
    section_grades = grade_sections(
        blocks,
        config,
        llm_client,
        max_tokens=max_tokens,
    )
    result = build_report_card(blocks, section_grades, config)

    # Whole-document consistency pass - the one place that sees all sections at
    # once. Additive: failures return [] and never block the report card.
    if progress_callback:
        progress_callback("consistency")
    result.cross_section_findings = check_cross_section(
        blocks, config, llm_client, max_tokens=max_tokens
    )

    result.org = config.org
    result.source_type = config.source_type
    result.intervention_class = config.intervention_class
    result.indication = indication
    return result


def run_pipeline_batch(
    jobs: list[tuple[str, str]],
    *,
    config: ReviewConfig,
    llm_client_factory,
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchReviewResult]:
    """Run `run_pipeline` (parse → label → grade) over many documents in parallel."""
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
                    indication=indication,
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
    indication: str | None,
    max_tokens: int,
) -> BatchReviewResult:
    try:
        llm_client = llm_client_factory()
        review = run_pipeline(
            file_path,
            config=config,
            llm_client=llm_client,
            indication=indication,
            max_tokens=max_tokens,
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
    indication: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[BatchReviewResult]:
    """Run `review_blocks` over many already-parsed documents in parallel.

    Args:
        jobs: list of (doc_key, blocks) pairs.
        llm_client_factory: zero-arg callable returning a fresh OpenAIClient per worker.

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
                    indication=indication,
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
    indication: str | None,
    max_tokens: int,
) -> BatchReviewResult:
    try:
        llm_client = llm_client_factory()
        review = review_blocks(
            blocks,
            config=config,
            llm_client=llm_client,
            indication=indication,
            max_tokens=max_tokens,
        )
        return BatchReviewResult(doc_key=doc_key, review=review)
    except Exception as exc:
        return BatchReviewResult(doc_key=doc_key, error=str(exc))




def build_report_card(
    labeled_blocks: list[ContentBlock],
    section_grades: list[SectionGrade],
    config: ReviewConfig,
) -> ReviewResult:
    """Roll section grades up into a full report card across two dimensions."""
    doc_id = labeled_blocks[0].doc_id if labeled_blocks else ""
    return ReviewResult(
        doc_id=doc_id,
        dimensions=_document_dimensions(section_grades, config),
        top_issues=_top_issues(section_grades, config),
        section_grades=section_grades,
    )


def _document_dimensions(
    section_grades: list[SectionGrade],
    config: ReviewConfig,
) -> dict[str, "DimensionGrade"]:
    """Weighted roll-up of section dimension grades into document-level dimensions."""
    from .models import DIMENSIONS, DimensionGrade

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
        grade: Grade = (
            _score_to_grade(weighted_score / applied_weight) if applied_weight > 0 else "N/A"
        )
        out[name] = DimensionGrade(
            grade=grade,
            issues=issues,
            recommendation="; ".join(dict.fromkeys(recs)),
        )
    return out


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
    """Pick the most severe issues across sections and variables, across all dimensions.

    Severity is derived from the dimension grade. Missing sections/variables
    rank above any letter grade.
    """
    issue_candidates: list[tuple[int, str]] = []
    for sg in section_grades:
        if not sg.is_present:
            recs = "; ".join(
                dg.recommendation for dg in sg.dimensions.values() if dg.recommendation
            )
            issue_candidates.append(
                (MISSING_SECTION_SEVERITY, f"{sg.section_name} missing - {recs}".strip(" -"))
            )
            continue

        for variable_name in sg.missing_variables:
            issue_candidates.append(
                (
                    MISSING_VARIABLE_SEVERITY,
                    _format_missing_variable_issue(variable_name, sg.section_name, config),
                )
            )

        for dim_name, dg in sg.dimensions.items():
            for issue in dg.issues:
                issue_candidates.append(
                    (
                        SEVERITY_ORDER.get(dg.grade, 5),
                        f"{sg.section_name} · {dim_name} ({dg.grade}) — {issue}",
                    )
                )
        for vg in sg.variable_grades:
            for dim_name, dg in vg.dimensions.items():
                for issue in dg.issues:
                    issue_candidates.append(
                        (
                            SEVERITY_ORDER.get(dg.grade, 5),
                            f"{vg.variable_name} · {dim_name} ({dg.grade}) — {issue}",
                        )
                    )

    seen: set[str] = set()
    ranked: list[str] = []
    for _, issue in sorted(issue_candidates, key=lambda item: item[0]):
        if not issue or issue in seen:
            continue
        seen.add(issue)
        ranked.append(issue)
        if len(ranked) >= limit:
            break
    return ranked


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
