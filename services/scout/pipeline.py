"""Stateless scout pipeline.

Orchestrates: chunker (parse only) -> canonical target binding -> per-unit query
generation (LLM) -> lane-native retrieval routing -> searcher -> per-unit insight
extraction (LLM) -> four independent reasoning layers. Reuses chunker and
searcher through their public contracts only.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Callable, TypeVar

from services.chunker import ContentBlock, run_pipeline as chunker_run
from services.searcher import (
    Finding,
    SearchRequest,
    SearchRuntime,
    merge_findings,
    plan_requests,
    run_requests,
)

from .context import (
    document_block_ids,
    render_canonical_binding,
    render_document_context,
    select_binding_context,
    select_resolution_context,
)
from .contract import validate_result_contract
from .models import (
    Attribute,
    ConformityScore,
    DocumentContextValidation,
    EvidenceAssessment,
    FunnelStats,
    Insight,
    LLMClientProtocol,
    Match,
    ScoutResult,
    ScoutTypeConfig,
    PrecedentSignal,
    QueryIntent,
    SearchTrace,
    load_attributes,
)
from .projections import build_development_landscape, build_safety_signals
from .stages.conformity import (
    empty_conformity_scores,
    extract_quantitative_target_set,
    resolve_quantitative_target_ownership,
    score_conformity,
)
from .stages.context_validator import mismatch_message, validate_document_context
from .stages.drift_classifier import INSIGHTS_BATCH_SIZE, classify_drift
from .stages.evidence_assessor import assess_evidence
from .stages.insight_extractor import extract_insights, merge_duplicate_insights
from .stages.precedent_classifier import classify_precedent
from .stages.query_extractor import extract_queries_for_variable
from .stages.intent_builder import build_retrieval_intents
from .stages.target_resolver import resolve_document_target
from .stages.unit_extractor import extract_units

FINDINGS_BATCH_SIZE = 40
FINDINGS_BATCH_CHARS = 240_000
TARGET_CONTEXT_CHARS = 40_000
SEARCH_MAX_TOKENS = 8000
SEARCH_MAX_USES = 10

# Parallelism for Scout's LLM reasoning fan-outs. Retrieval concurrency belongs
# to each Searcher source adapter and is not duplicated here.
MAX_WORKERS = 32


def run_pipeline(
    file_paths: list[str],
    *,
    doc_ids: list[str] | None = None,
    config: ScoutTypeConfig,
    openai_client: LLMClientProtocol,
    retrieval_runtime: SearchRuntime,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
    progress_callback=None,
) -> ScoutResult:
    """Run scout over every shared attribute variable for the intervention."""
    if progress_callback:
        progress_callback("parse")
    blocks = _parse_all_docs(
        file_paths,
        doc_ids=doc_ids,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
    )
    # Preserve block IDs through every doc-aware stage. The model may cite only
    # these markers; each stage validates returned IDs against its input context.
    doc_text = render_document_context(blocks)

    if progress_callback:
        progress_callback("context")
    context_validation = validate_document_context(
        doc_text,
        openai_client,
        indication=indication,
        images=[
            {"block_id": block.id, "data_url": block.image.data_url()}
            for block in blocks
            if block.image
        ]
        or None,
    )
    if context_validation.status == "mismatch":
        raise ValueError(mismatch_message(context_validation))

    attributes = _resolve_units(
        config, doc_text, blocks, openai_client, indication=indication
    )
    if not attributes:
        return validate_result_contract(ScoutResult(
            matches=[],
            assessments=[],
            stats=FunnelStats(
                queries=0,
                findings=0,
                unique_findings=0,
                insights=0,
                matches=0,
                assessments=0,
            ),
            context_validation=context_validation,
            blocks=blocks,
        ))

    # Provider-specific work ends here. Fixed definitions are bound to their
    # document target; dynamically extracted units arrive already bound. Every
    # later stage receives the same resolved Attribute contract.
    seed_contexts = {
        attribute.name: select_resolution_context(
            blocks,
            attribute,
            max_chars=TARGET_CONTEXT_CHARS,
        )
        for attribute in attributes
    }
    attributes = _resolve_targets_all(
        attributes,
        seed_contexts,
        blocks,
        openai_client,
        progress=progress_callback,
    )
    attributes = _extract_quantitative_targets_all(
        attributes,
        {
            attribute.name: select_binding_context(blocks, attribute)
            for attribute in attributes
        },
        blocks,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.conformity_framing,
        progress=progress_callback,
    )
    attributes = resolve_quantitative_target_ownership(attributes, openai_client)
    attribute_descriptions = {
        attribute.name: attribute.description for attribute in attributes
    }
    # The relevance-selected resolution view has completed its one job. Every
    # later reasoning stage receives the canonical target with its exact block
    # markers, not the rest of a potentially multi-topic table row.
    attribute_contexts = {
        attribute.name: render_canonical_binding(attribute)
        for attribute in attributes
    }
    attribute_images = _images_for_contexts(attribute_contexts, blocks)

    if progress_callback:
        progress_callback("queries")
    attribute_queries = _extract_queries_all_variables(
        attributes,
        config,
        openai_client,
        query_contexts=attribute_contexts,
        indication=indication,
        progress=progress_callback,
    )
    flat: list[tuple[str, QueryIntent]] = [
        (attribute_ref, query)
        for attribute_ref, queries in attribute_queries.items()
        for query in queries
    ]
    if not flat:
        return _empty_result(
            blocks=blocks,
            variables=attributes,
            context_validation=context_validation,
        )

    if progress_callback:
        progress_callback("search")
    retrieval_intents = build_retrieval_intents(
        attribute_queries,
        attributes,
        indication=indication,
        intervention_class=intervention_class,
    )
    search_tasks = plan_requests(retrieval_intents, sources=config.sources)
    findings_by_attribute, total_findings, search_plan = _search_all(
        search_tasks,
        retrieval_runtime,
        progress=progress_callback,
    )
    if not findings_by_attribute:
        return _empty_result(
            queries=len(flat),
            blocks=blocks,
            variables=attributes,
            search_plan=search_plan,
            context_validation=context_validation,
        )

    # Adapters own source-specific parsing. These views consume only normalized
    # records and therefore add no new model judgment or provider branch here.
    development_landscape = build_development_landscape(findings_by_attribute)
    safety_signals = build_safety_signals(findings_by_attribute)

    query_tracks_by_attribute: dict[str, dict[str, list[str]]] = {}
    query_targets_by_attribute: dict[str, dict[str, list[str]]] = {}
    for task in search_tasks:
        if task.tracks:
            track_map = query_tracks_by_attribute.setdefault(task.scope_ref, {})
            track_map[task.query] = list(
                dict.fromkeys([*track_map.get(task.query, []), *task.tracks])
            )
        if task.target_refs:
            target_map = query_targets_by_attribute.setdefault(task.scope_ref, {})
            target_map[task.query] = list(
                dict.fromkeys(
                    [*target_map.get(task.query, []), *task.target_refs]
                )
            )

    if progress_callback:
        progress_callback("insights")
    insights = _extract_insights_all_variables(
        findings_by_attribute,
        attribute_descriptions,
        query_tracks_by_attribute,
        query_targets_by_attribute,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )

    _stamp(
        insights,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
    )

    if progress_callback:
        progress_callback("classify")
    matches = _classify_drift_all(
        attribute_contexts,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.drift_framing,
        attribute_images=attribute_images,
        progress=progress_callback,
    )

    if progress_callback:
        progress_callback("evidence")
    assessments = _assess_evidence_all_variables(
        attributes,
        attribute_contexts,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.evidence_framing,
        attribute_images=attribute_images,
        progress=progress_callback,
    )

    if progress_callback:
        progress_callback("conformity")
    conformity = _score_conformity_all_variables(
        attributes,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )

    if progress_callback:
        progress_callback("precedent")
    precedents = _classify_precedent_all_variables(
        attributes,
        attribute_contexts,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.precedent_framing,
        attribute_images=attribute_images,
        progress=progress_callback,
    )

    stats = FunnelStats(
        queries=len(flat),
        findings=total_findings,
        unique_findings=len({
            finding.url
            for findings in findings_by_attribute.values()
            for finding in findings
        }),
        insights=len(insights),
        matches=len(matches),
        assessments=len(assessments),
    )
    return validate_result_contract(ScoutResult(
        matches=matches,
        assessments=assessments,
        stats=stats,
        conformity=conformity,
        precedents=precedents,
        search_plan=search_plan,
        development_landscape=development_landscape,
        safety_signals=safety_signals,
        context_validation=context_validation,
        variables=attributes,
        blocks=blocks,
    ))


def _resolve_units(
    config: ScoutTypeConfig,
    doc_text: str,
    blocks: list[ContentBlock],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
) -> list[Attribute]:
    """Get definitions from the configured provider.

    ``vocabulary`` reads fixed definitions; ``extract`` returns dynamically
    defined units already bound to their document targets. The next stage binds
    fixed definitions so provider-specific semantics end before retrieval.
    """
    if config.unit_provider == "extract":
        return extract_units(
            doc_text,
            intervention_class=config.intervention_class,
            source_type=config.source_type,
            indication=indication,
            llm_client=openai_client,
            images_by_block_id={
                block.id: block.image.data_url()
                for block in blocks
                if block.image
            },
        )
    return load_attributes(config.intervention_class)


def _parse_all_docs(
    file_paths: list[str],
    *,
    doc_ids: list[str] | None = None,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> list[ContentBlock]:
    """Parse each doc via chunker without section-label mapping."""
    if doc_ids is not None and len(doc_ids) != len(file_paths):
        raise ValueError("doc_ids must have the same length as file_paths")
    blocks: list[ContentBlock] = []
    for index, file_path in enumerate(file_paths):
        doc_id = doc_ids[index] if doc_ids is not None else Path(file_path).stem
        doc_blocks = chunker_run(
            file_path,
            doc_id,
            org=org,
            source_type=source_type,
            intervention_class=intervention_class,
            indication=indication,
        )
        blocks.extend(doc_blocks)
    return blocks


_T = TypeVar("_T")
_R = TypeVar("_R")

# A progress reporter: progress(stage, completed=int, total=int). Optional - when
# None, stages run with no per-item reporting. Threaded explicitly (never a
# global) so concurrent requests can't cross-report.
ProgressFn = Callable[..., None]


def _parallel_map(
    items: list[_T],
    fn: Callable[[_T], _R],
    *,
    workers: int,
    stage: str,
    progress: ProgressFn | None,
) -> list[_R]:
    """Run `fn` over `items` concurrently, preserving input order, emitting
    `progress(stage, completed, total)` as each task FINISHES.

    The completion counter is lock-guarded because tasks finish on worker
    threads; the streaming queue the callback writes to is itself thread-safe.
    """
    total = len(items)
    if total == 0:
        return []
    workers = max(1, min(workers, total))
    if progress:
        progress(stage, completed=0, total=total)

    lock = threading.Lock()
    state = {"done": 0}
    results: list[_R] = [None] * total  # type: ignore[list-item]

    def run_one(indexed: tuple[int, _T]) -> tuple[int, _R]:
        idx, item = indexed
        result = fn(item)
        if progress:
            with lock:
                state["done"] += 1
                progress(stage, completed=state["done"], total=total)
        return idx, result

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for idx, result in executor.map(run_one, enumerate(items)):
            results[idx] = result
    return results


def _extract_queries_all_variables(
    attributes: list[Attribute],
    config: ScoutTypeConfig,
    openai_client: LLMClientProtocol,
    *,
    query_contexts: dict[str, str],
    indication: str,
    progress: ProgressFn | None = None,
) -> dict[str, list[QueryIntent]]:
    """Run query extraction across attribute variables with bounded concurrency."""
    if not attributes:
        return {}

    def one(attribute: Attribute) -> tuple[str, list[QueryIntent]]:
        return attribute.name, extract_queries_for_variable(
            attribute,
            config,
            openai_client,
            indication=indication,
            queries_per_variable=config.queries_per_variable,
            document_context=query_contexts.get(attribute.name, ""),
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="queries", progress=progress
    )
    return {name: queries for name, queries in results if queries}


def _resolve_targets_all(
    attributes: list[Attribute],
    contexts: dict[str, str],
    blocks: list[ContentBlock],
    openai_client: LLMClientProtocol,
    *,
    progress: ProgressFn | None = None,
) -> list[Attribute]:
    """Resolve fixed and dynamic definitions to one document-bound shape."""
    images_by_attribute = _images_for_contexts(contexts, blocks)

    def one(attribute: Attribute) -> Attribute:
        return resolve_document_target(
            attribute,
            contexts.get(attribute.name, ""),
            openai_client,
            images=images_by_attribute.get(attribute.name) or None,
        )

    return _parallel_map(
        attributes,
        one,
        workers=MAX_WORKERS,
        stage="targets",
        progress=progress,
    )


def _extract_quantitative_targets_all(
    attributes: list[Attribute],
    contexts: dict[str, str],
    blocks: list[ContentBlock],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str,
    progress: ProgressFn | None = None,
) -> list[Attribute]:
    """Bind each verified numeric claim once, before retrieval planning."""
    images_by_attribute = _images_for_contexts(contexts, blocks)

    def one(attribute: Attribute) -> Attribute:
        if not attribute.document_target:
            return replace(
                attribute,
                quantitative_target_status="not_applicable",
                quantitative_target_status_reason=(
                    "The canonical field has no document-stated target to calibrate."
                ),
            )
        extraction = extract_quantitative_target_set(
            attribute,
            contexts.get(attribute.name, ""),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=images_by_attribute.get(attribute.name) or None,
        )
        return replace(
            attribute,
            quantitative_targets=extraction.targets,
            quantitative_target_status=extraction.status,
            quantitative_target_status_reason=extraction.reason,
        )

    return _parallel_map(
        attributes,
        one,
        workers=MAX_WORKERS,
        stage="quantitative_targets",
        progress=progress,
    )


def _images_for_contexts(
    contexts: dict[str, str],
    blocks: list[ContentBlock],
) -> dict[str, list[dict[str, str]]]:
    """Attach visuals by the exact block IDs present in each bounded context."""
    output: dict[str, list[dict[str, str]]] = {}
    for attribute_ref, context in contexts.items():
        context_ids = document_block_ids(context)
        output[attribute_ref] = [
            {
                "block_id": block.id,
                "data_url": block.image.data_url(),
            }
            for block in blocks
            if block.image and block.id in context_ids
        ]
    return output


def _extract_insights_all_variables(
    findings_by_attribute: dict[str, list[Finding]],
    attribute_descriptions: dict[str, str],
    query_tracks_by_attribute: dict[str, dict[str, list[str]]],
    query_targets_by_attribute: dict[str, dict[str, list[str]]],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[Insight]:
    """Run insight extraction concurrently across all (variable, finding-batch)
    units.

    Every finding is retained. Batches are bounded by both item count and rendered
    character size so one unusually large source cannot crowd the model context.
    Each task remains single-variable and results are deterministically merged,
    preventing duplicate insights created at batch boundaries."""
    items = list(findings_by_attribute.items())
    if not items:
        return []

    # Flatten to independent (attribute_ref, batch) units in document-variable order.
    batch_tasks: list[tuple[str, list[Finding]]] = [
        (attribute_ref, batch)
        for attribute_ref, findings in items
        for batch in _finding_batches(
            [finding for finding in findings if finding.evidence_role == "evidence"]
        )
    ]
    if not batch_tasks:
        return []

    def one(task: tuple[str, list[Finding]]) -> list[Insight]:
        attribute_ref, batch = task
        return extract_insights(
            batch,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            attribute_ref=attribute_ref,
            attribute_description=attribute_descriptions.get(attribute_ref, ""),
            query_tracks=query_tracks_by_attribute.get(attribute_ref, {}),
            query_targets=query_targets_by_attribute.get(attribute_ref, {}),
        )

    results = _parallel_map(
        batch_tasks, one, workers=MAX_WORKERS, stage="insights", progress=progress
    )

    insights: list[Insight] = []
    for batch_insights in results:
        insights.extend(batch_insights)
    return merge_duplicate_insights(insights)


def _finding_batches(findings: list[Finding]) -> list[list[Finding]]:
    """Partition findings without dropping any source or overfilling one prompt."""
    batches: list[list[Finding]] = []
    current: list[Finding] = []
    current_chars = 0
    for finding in findings:
        size = (
            len(finding.title or "")
            + len(finding.excerpt or "")
            + len(finding.url or "")
            + sum(len(query) for query in finding.queries)
        )
        if current and (
            len(current) >= FINDINGS_BATCH_SIZE
            or current_chars + size > FINDINGS_BATCH_CHARS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(finding)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def _search_all(
    tasks: list[SearchRequest],
    runtime: SearchRuntime,
    *,
    progress: ProgressFn | None = None,
) -> tuple[dict[str, list[Finding]], int, list[SearchTrace]]:
    """Run Searcher's controller and merge normalized findings per Scout unit."""
    if not tasks:
        return {}, 0, []
    outcomes = run_requests(
        tasks,
        runtime=runtime,
        max_tokens=SEARCH_MAX_TOKENS,
        max_uses=SEARCH_MAX_USES,
        progress=(
            lambda completed, total: progress(
                "search", completed=completed, total=total
            )
        )
        if progress
        else None,
    )

    findings_by_attribute: dict[str, list[Finding]] = {}
    by_attribute_url: dict[str, dict[str, Finding]] = {}
    total_findings = 0
    for outcome in outcomes:
        task = outcome.request
        findings = outcome.findings
        total_findings += len(findings)
        output = findings_by_attribute.setdefault(task.scope_ref, [])
        by_url = by_attribute_url.setdefault(task.scope_ref, {})
        for finding in findings:
            if finding.url in by_url:
                merge_findings(by_url[finding.url], finding)
                continue
            by_url[finding.url] = finding
            output.append(finding)

    def trace_for(outcome) -> SearchTrace:
        task = outcome.request
        return SearchTrace(
            attribute_ref=task.scope_ref,
            lane=task.source,
            query=task.query,
            connector=task.connector,
            operation=task.operation,
            request_options=dict(task.options),
            tracks=list(task.tracks),
            doc_block_ids=list(task.document_refs),
            target_ids=list(task.target_refs),
            intent_ids=list(task.intent_ids),
            input_queries=list(task.input_queries),
            applicability=task.applicability,
            applicability_reason=task.applicability_reason,
            status=outcome.status,
            error=outcome.error,
            finding_count=len(outcome.findings),
            source_urls=[finding.url for finding in outcome.findings],
        )

    search_plan = [trace_for(outcome) for outcome in outcomes]
    return (
        {attribute: findings for attribute, findings in findings_by_attribute.items() if findings},
        total_findings,
        search_plan,
    )


def _classify_drift_all(
    attribute_contexts: dict[str, str],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    attribute_images: dict[str, list[dict[str, str]]] | None = None,
    progress: ProgressFn | None = None,
) -> list[Match]:
    """Classify drift in single-variable batches against that variable's context."""
    if not insights:
        return []

    grouped = _group_insights_by_attribute(insights, set(attribute_contexts))
    tasks = [
        (attribute_ref, attribute_contexts.get(attribute_ref, ""), variable_insights[start : start + INSIGHTS_BATCH_SIZE])
        for attribute_ref, variable_insights in grouped.items()
        for start in range(0, len(variable_insights), INSIGHTS_BATCH_SIZE)
    ]

    def one(task: tuple[str, str, list[Insight]]) -> list[Match]:
        attribute_ref, context, batch = task
        return classify_drift(
            [context],
            batch,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute_ref) or None,
        )

    results = _parallel_map(
        tasks, one, workers=MAX_WORKERS, stage="classify", progress=progress
    )
    matches: list[Match] = []
    for batch_matches in results:
        matches.extend(batch_matches)
    return matches


def _assess_evidence_all_variables(
    attributes: list[Attribute],
    attribute_contexts: dict[str, str],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    attribute_images: dict[str, list[dict[str, str]]] | None = None,
    progress: ProgressFn | None = None,
) -> list[EvidenceAssessment]:
    """Assess evidence per attribute with bounded concurrency."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    def one(attribute: Attribute) -> EvidenceAssessment:
        return assess_evidence(
            attribute,
            attribute_contexts.get(attribute.name, ""),
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute.name) or None,
        )

    return _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="evidence", progress=progress
    )


def _score_conformity_all_variables(
    attributes: list[Attribute],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[ConformityScore]:
    """Score quantitative conformity per attribute with bounded concurrency.

    Self-gating: returns ledgers only for variables with an exact-quoted numeric
    target. A valid target with no admitted comparators remains an explicit
    insufficient cohort rather than disappearing."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    def one(attribute: Attribute) -> list[ConformityScore]:
        return score_conformity(
            attribute,
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="conformity", progress=progress
    )
    return [score for target_scores in results for score in target_scores]


def _classify_precedent_all_variables(
    attributes: list[Attribute],
    attribute_contexts: dict[str, str],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    attribute_images: dict[str, list[dict[str, str]]] | None = None,
    progress: ProgressFn | None = None,
) -> list[PrecedentSignal]:
    """Classify precedent per attribute with bounded concurrency.

    Self-gating: returns a signal only for variables with external evidence
    (classify_precedent returns None otherwise)."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    def one(attribute: Attribute) -> PrecedentSignal | None:
        return classify_precedent(
            attribute,
            attribute_contexts.get(attribute.name, ""),
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute.name) or None,
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="precedent", progress=progress
    )
    return [signal for signal in results if signal is not None]


def _group_insights_by_attribute(
    insights: list[Insight],
    known_attributes: set[str],
) -> dict[str, list[Insight]]:
    """Build the one field-isolation boundary shared by every reasoning axis."""
    grouped: dict[str, list[Insight]] = {}
    for insight in insights:
        attribute_ref = insight.attribute_ref
        if not attribute_ref or attribute_ref not in known_attributes:
            raise ValueError(
                f"insight {insight.id!r} references unknown field {attribute_ref!r}"
            )
        grouped.setdefault(attribute_ref, []).append(insight)
    return grouped


def _empty_result(
    *,
    context_validation: DocumentContextValidation,
    queries: int = 0,
    findings: int = 0,
    unique_findings: int = 0,
    insights: int = 0,
    blocks: list[ContentBlock] | None = None,
    variables: list[Attribute] | None = None,
    search_plan: list[SearchTrace] | None = None,
) -> ScoutResult:
    return validate_result_contract(ScoutResult(
        matches=[],
        assessments=[],
        stats=FunnelStats(
            queries=queries,
            findings=findings,
            unique_findings=unique_findings,
            insights=insights,
            matches=0,
            assessments=0,
        ),
        variables=variables or [],
        conformity=empty_conformity_scores(variables or []),
        search_plan=search_plan or [],
        context_validation=context_validation,
        blocks=blocks or [],
    ))


def _stamp(
    insights: list[Insight],
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> None:
    for insight in insights:
        insight.org = org
        insight.source_type = source_type
        insight.intervention_class = intervention_class
        insight.indication = indication
