"""Stateless monitor pipeline.

Orchestrates: chunker (parse only) -> per-attribute query_extractor
(LLM) -> searcher (web) -> per-attribute insight_extractor (LLM) ->
drift_classifier + evidence_assessor (LLM). Reuses chunker and searcher
via their public contracts only.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, TypeVar

from services.chunker import ContentBlock, run_pipeline as chunker_run
from services.searcher import Finding, run_pipeline as searcher_run

from .models import (
    Attribute,
    ConformityScore,
    EvidenceAssessment,
    FunnelStats,
    Insight,
    LLMClientProtocol,
    Match,
    MonitorResult,
    MonitorTypeConfig,
    PrecedentSignal,
    SearchClientProtocol,
    load_attributes,
)
from .stages.conformity import score_conformity
from .stages.drift_classifier import classify_drift
from .stages.evidence_assessor import assess_evidence
from .stages.insight_extractor import extract_insights
from .stages.precedent_classifier import classify_precedent
from .stages.query_extractor import extract_queries_for_variable

FINDINGS_BATCH_SIZE = 40
SEARCH_MAX_TOKENS = 8000
SEARCH_MAX_USES = 10

# Parallelism. MAX_WORKERS governs every OpenAI-bound fan-out (query/insight/
# evidence/conformity/precedent stages AND the web search lane) - they are all
# I/O-bound on OpenAI, whose enterprise rate limits allow generous concurrency.
# 32 roughly halves the wall-clock of the web lane (the long pole) versus 16
# while staying well under enterprise RPM/TPM; push higher only if no 429s
# appear. PubMed is globally rate-throttled to NCBI's ~9/s ceiling (more workers
# would just queue behind the throttle) and ClinicalTrials.gov is cached to one
# fetch per run, so those keep modest, independent worker counts.
MAX_WORKERS = 32
PUBMED_WORKERS = 8
CLINICALTRIALS_WORKERS = 8


def run_pipeline(
    file_paths: list[str],
    *,
    config: MonitorTypeConfig,
    openai_client: LLMClientProtocol,
    search_client: SearchClientProtocol,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
    progress_callback=None,
) -> MonitorResult:
    """Run monitor over every shared attribute variable for the intervention."""
    if progress_callback:
        progress_callback("parse")
    blocks = _parse_all_docs(
        file_paths,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
    )
    doc_text = "\n".join(
        block.content for block in blocks if getattr(block, "content", "")
    )

    attributes = load_attributes(intervention_class)
    if not attributes:
        return MonitorResult(
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
        )
    attribute_descriptions = {
        attribute.name: attribute.description for attribute in attributes
    }

    if progress_callback:
        progress_callback("queries")
    attribute_queries = _extract_queries_all_variables(
        attributes,
        config,
        openai_client,
        indication=indication,
        progress=progress_callback,
    )
    flat: list[tuple[str, str]] = [
        (attribute_ref, query)
        for attribute_ref, queries in attribute_queries.items()
        for query in queries
    ]
    if not flat:
        return _empty_result()

    if progress_callback:
        progress_callback("search")
    findings_by_query = _search_all(
        flat,
        search_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )
    if not findings_by_query:
        return _empty_result(queries=len(flat))

    findings_by_attribute: dict[str, list[Finding]] = {}
    total_findings = 0
    for (attribute_ref, _query), findings in findings_by_query.items():
        total_findings += len(findings)
        findings_by_attribute.setdefault(attribute_ref, [])
        for finding in findings:
            if not any(
                existing.url == finding.url
                for existing in findings_by_attribute[attribute_ref]
            ):
                findings_by_attribute[attribute_ref].append(finding)

    if progress_callback:
        progress_callback("insights")
    insights = _extract_insights_all_variables(
        findings_by_attribute,
        attribute_descriptions,
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
    matches = classify_drift(
        [doc_text],
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
    )

    if progress_callback:
        progress_callback("evidence")
    assessments = _assess_evidence_all_variables(
        attributes,
        doc_text,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )

    if progress_callback:
        progress_callback("conformity")
    conformity = _score_conformity_all_variables(
        attributes,
        doc_text,
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
        doc_text,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )

    stats = FunnelStats(
        queries=len(flat),
        findings=total_findings,
        unique_findings=sum(len(findings) for findings in findings_by_attribute.values()),
        insights=len(insights),
        matches=len(matches),
        assessments=len(assessments),
    )
    return MonitorResult(
        matches=matches,
        assessments=assessments,
        stats=stats,
        conformity=conformity,
        precedents=precedents,
    )


def _parse_all_docs(
    file_paths: list[str],
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> list[ContentBlock]:
    """Parse each doc via chunker without section-label mapping."""
    blocks: list[ContentBlock] = []
    for file_path in file_paths:
        doc_id = Path(file_path).stem
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
    config: MonitorTypeConfig,
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    progress: ProgressFn | None = None,
) -> dict[str, list[str]]:
    """Run query extraction across attribute variables with bounded concurrency."""
    if not attributes:
        return {}

    def one(attribute: Attribute) -> tuple[str, list[str]]:
        return attribute.name, extract_queries_for_variable(
            attribute,
            config,
            openai_client,
            indication=indication,
            queries_per_variable=config.queries_per_variable,
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="queries", progress=progress
    )
    return {name: queries for name, queries in results if queries}


def _extract_insights_all_variables(
    findings_by_attribute: dict[str, list[Finding]],
    attribute_descriptions: dict[str, str],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[Insight]:
    """Run insight extraction per attribute with bounded concurrency."""
    items = list(findings_by_attribute.items())
    if not items:
        return []

    def one(item: tuple[str, list[Finding]]) -> list[Insight]:
        attribute_ref, findings = item
        return _extract_insights_for_variable(
            attribute_ref,
            findings,
            attribute_descriptions,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
        )

    results = _parallel_map(
        items, one, workers=MAX_WORKERS, stage="insights", progress=progress
    )

    insights: list[Insight] = []
    for variable_insights in results:
        insights.extend(variable_insights)
    return insights


def _extract_insights_for_variable(
    attribute_ref: str,
    findings: list[Finding],
    attribute_descriptions: dict[str, str],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
) -> list[Insight]:
    """Extract insights from every finding for one variable, batching as needed."""
    insights: list[Insight] = []
    for start in range(0, len(findings), FINDINGS_BATCH_SIZE):
        batch = findings[start : start + FINDINGS_BATCH_SIZE]
        insights.extend(
            extract_insights(
                batch,
                openai_client,
                indication=indication,
                intervention_class=intervention_class,
                attribute_ref=attribute_ref,
                attribute_description=attribute_descriptions.get(attribute_ref, ""),
            )
        )
    return insights


def _search_all(
    attribute_queries: list[tuple[str, str]],
    search_client: SearchClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> dict[tuple[str, str], list[Finding]]:
    """Search all queries and return a mapping from (attribute, query) to findings.

    Web, PubMed, and ClinicalTrials.gov run as THREE concurrent passes so the
    fast web modality is not blocked by the literature/registry backends' global
    rate throttles. Per query, the three backends' findings are unioned (dedup by
    URL). Each backend swallows its own failures, so one lane going dark never
    drops the others.

    Progress is reported as backend-query tasks complete; each query is searched
    once per lane, so the total is queries x 3 lanes.
    """
    if not attribute_queries:
        return {}

    total = 3 * len(attribute_queries)
    lock = threading.Lock()
    state = {"done": 0}
    if progress:
        progress("search", completed=0, total=total)

    def report() -> None:
        if not progress:
            return
        with lock:
            state["done"] += 1
            progress("search", completed=state["done"], total=total)

    with ThreadPoolExecutor(max_workers=3) as outer:
        web_future = outer.submit(
            _search_backend, attribute_queries, search_client, ("web",), MAX_WORKERS, report
        )
        pubmed_future = outer.submit(
            _search_backend, attribute_queries, search_client, ("pubmed",), PUBMED_WORKERS, report
        )
        ctgov_future = outer.submit(
            _search_backend,
            attribute_queries,
            search_client,
            ("clinicaltrials",),
            CLINICALTRIALS_WORKERS,
            report,
            indication,
            intervention_class,
        )
        web = web_future.result()
        pubmed = pubmed_future.result()
        ctgov = ctgov_future.result()

    merged: dict[tuple[str, str], list[Finding]] = {}
    for attribute_query in attribute_queries:
        seen: set[str] = set()
        out: list[Finding] = []
        for finding in (
            web.get(attribute_query, [])
            + pubmed.get(attribute_query, [])
            + ctgov.get(attribute_query, [])
        ):
            if finding.url in seen:
                continue
            seen.add(finding.url)
            out.append(finding)
        merged[attribute_query] = out
    return merged


def _search_backend(
    attribute_queries: list[tuple[str, str]],
    search_client: SearchClientProtocol,
    backends: tuple[str, ...],
    max_workers: int,
    report: Callable[[], None] | None = None,
    condition: str | None = None,
    intervention: str | None = None,
) -> dict[tuple[str, str], list[Finding]]:
    """Run one retrieval backend across all queries with bounded concurrency.

    Calls `report()` once per query as it completes, so the shared search
    counter advances across all three lanes. `condition`/`intervention` are
    backend-specific hints for the structured ClinicalTrials.gov search; other
    backends ignore them."""
    workers = max(1, min(max_workers, len(attribute_queries)))

    def one(attribute_query: tuple[str, str]) -> list[Finding]:
        findings = searcher_run(
            attribute_query[1],
            llm_client=search_client,
            max_tokens=SEARCH_MAX_TOKENS,
            max_uses=SEARCH_MAX_USES,
            backends=backends,
            ncbi_api_key=os.getenv("NCBI_API_KEY"),
            condition=condition,
            intervention=intervention,
        )
        if report:
            report()
        return findings

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(one, attribute_queries))
    return {
        attribute_query: findings
        for attribute_query, findings in zip(attribute_queries, results)
    }


def _assess_evidence_all_variables(
    attributes: list[Attribute],
    doc_text: str,
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[EvidenceAssessment]:
    """Assess evidence per attribute with bounded concurrency."""
    insights_by_attribute: dict[str, list[Insight]] = {}
    for insight in insights:
        if not insight.attribute_ref:
            continue
        insights_by_attribute.setdefault(insight.attribute_ref, []).append(insight)

    if not attributes:
        return []

    def one(attribute: Attribute) -> EvidenceAssessment:
        return assess_evidence(
            attribute,
            doc_text,
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
        )

    return _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="evidence", progress=progress
    )


def _score_conformity_all_variables(
    attributes: list[Attribute],
    doc_text: str,
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[ConformityScore]:
    """Score quantitative conformity per attribute with bounded concurrency.

    Self-gating: returns scores only for variables that are numeric and have
    comparable evidence (score_conformity returns None otherwise)."""
    insights_by_attribute: dict[str, list[Insight]] = {}
    for insight in insights:
        if not insight.attribute_ref:
            continue
        insights_by_attribute.setdefault(insight.attribute_ref, []).append(insight)

    if not attributes:
        return []

    def one(attribute: Attribute) -> ConformityScore | None:
        return score_conformity(
            attribute,
            doc_text,
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="conformity", progress=progress
    )
    return [score for score in results if score is not None]


def _classify_precedent_all_variables(
    attributes: list[Attribute],
    doc_text: str,
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[PrecedentSignal]:
    """Classify precedent per attribute with bounded concurrency.

    Self-gating: returns a signal only for variables with web evidence
    (classify_precedent returns None otherwise)."""
    insights_by_attribute: dict[str, list[Insight]] = {}
    for insight in insights:
        if not insight.attribute_ref:
            continue
        insights_by_attribute.setdefault(insight.attribute_ref, []).append(insight)

    if not attributes:
        return []

    def one(attribute: Attribute) -> PrecedentSignal | None:
        return classify_precedent(
            attribute,
            doc_text,
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="precedent", progress=progress
    )
    return [signal for signal in results if signal is not None]


def _empty_result(
    *,
    queries: int = 0,
    findings: int = 0,
    unique_findings: int = 0,
    insights: int = 0,
) -> MonitorResult:
    return MonitorResult(
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
    )


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
