"""Stateless monitor pipeline.

Orchestrates: chunker (parse only) -> per-attribute query_extractor
(LLM) -> searcher (web) -> per-attribute insight_extractor (LLM) ->
drift_classifier + evidence_assessor (LLM). Reuses chunker and searcher
via their public contracts only.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.chunker import ContentBlock, run_pipeline as chunker_run
from services.searcher import Finding, run_pipeline as searcher_run

from .models import (
    Attribute,
    EvidenceAssessment,
    FunnelStats,
    Insight,
    LLMClientProtocol,
    Match,
    MonitorResult,
    MonitorTypeConfig,
    SearchClientProtocol,
    load_attributes,
)
from .stages.drift_classifier import classify_drift
from .stages.evidence_assessor import assess_evidence
from .stages.insight_extractor import extract_insights
from .stages.query_extractor import extract_queries_for_variable

FINDINGS_BATCH_SIZE = 40
SEARCH_MAX_TOKENS = 8000
SEARCH_MAX_USES = 10

# Parallelism. LLM/web stages are I/O-bound on OpenAI (enterprise rate limits
# allow generous concurrency). PubMed runs on its own pass; NCBI is globally
# rate-throttled inside the searcher regardless, so its worker count is modest.
MAX_WORKERS = 16
PUBMED_WORKERS = 8


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
    findings_by_query = _search_all(flat, search_client)
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
    )

    stats = FunnelStats(
        queries=len(flat),
        findings=total_findings,
        unique_findings=sum(len(findings) for findings in findings_by_attribute.values()),
        insights=len(insights),
        matches=len(matches),
        assessments=len(assessments),
    )
    return MonitorResult(matches=matches, assessments=assessments, stats=stats)


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


def _extract_queries_all_variables(
    attributes: list[Attribute],
    config: MonitorTypeConfig,
    openai_client: LLMClientProtocol,
    *,
    indication: str,
) -> dict[str, list[str]]:
    """Run query extraction across attribute variables with bounded concurrency."""
    if not attributes:
        return {}
    workers = max(1, min(MAX_WORKERS, len(attributes)))

    def one(attribute: Attribute) -> tuple[str, list[str]]:
        return attribute.name, extract_queries_for_variable(
            attribute,
            config,
            openai_client,
            indication=indication,
            queries_per_variable=config.queries_per_variable,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(one, attributes))
    return {name: queries for name, queries in results if queries}


def _extract_insights_all_variables(
    findings_by_attribute: dict[str, list[Finding]],
    attribute_descriptions: dict[str, str],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
) -> list[Insight]:
    """Run insight extraction per attribute with bounded concurrency."""
    items = list(findings_by_attribute.items())
    if not items:
        return []
    workers = max(1, min(MAX_WORKERS, len(items)))

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

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(one, items))

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
) -> dict[tuple[str, str], list[Finding]]:
    """Search all queries and return a mapping from (attribute, query) to findings.

    Web and PubMed run as TWO concurrent passes so the fast web modality is not
    blocked by PubMed's global NCBI rate throttle. Per query, the two backends'
    findings are unioned (dedup by URL).
    """
    if not attribute_queries:
        return {}

    with ThreadPoolExecutor(max_workers=2) as outer:
        web_future = outer.submit(
            _search_backend, attribute_queries, search_client, ("web",), MAX_WORKERS
        )
        pubmed_future = outer.submit(
            _search_backend, attribute_queries, search_client, ("pubmed",), PUBMED_WORKERS
        )
        web = web_future.result()
        pubmed = pubmed_future.result()

    merged: dict[tuple[str, str], list[Finding]] = {}
    for attribute_query in attribute_queries:
        seen: set[str] = set()
        out: list[Finding] = []
        for finding in web.get(attribute_query, []) + pubmed.get(attribute_query, []):
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
) -> dict[tuple[str, str], list[Finding]]:
    """Run one retrieval backend across all queries with bounded concurrency."""
    workers = max(1, min(max_workers, len(attribute_queries)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(
            executor.map(
                lambda attribute_query: searcher_run(
                    attribute_query[1],
                    llm_client=search_client,
                    max_tokens=SEARCH_MAX_TOKENS,
                    max_uses=SEARCH_MAX_USES,
                    backends=backends,
                    ncbi_api_key=os.getenv("NCBI_API_KEY"),
                ),
                attribute_queries,
            )
        )
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
) -> list[EvidenceAssessment]:
    """Assess evidence per attribute with bounded concurrency."""
    insights_by_attribute: dict[str, list[Insight]] = {}
    for insight in insights:
        if not insight.attribute_ref:
            continue
        insights_by_attribute.setdefault(insight.attribute_ref, []).append(insight)

    if not attributes:
        return []
    workers = max(1, min(MAX_WORKERS, len(attributes)))

    def one(attribute: Attribute) -> EvidenceAssessment:
        return assess_evidence(
            attribute,
            doc_text,
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(one, attributes))


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
