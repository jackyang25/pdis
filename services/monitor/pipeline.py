"""Stateless monitor pipeline.

Orchestrates: chunker (parse only) -> per-attribute query_extractor
(LLM) -> searcher (web) -> per-attribute insight_extractor (LLM) ->
drift_classifier (LLM). Reuses chunker and searcher via their public
contracts only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.chunker import ContentBlock, run_pipeline as chunker_run
from services.searcher import Finding, run_pipeline as searcher_run

from .models import (
    Attribute,
    Insight,
    LLMClientProtocol,
    Match,
    MonitorTypeConfig,
    SearchClientProtocol,
    load_attributes,
)
from .stages.drift_classifier import classify_drift
from .stages.insight_extractor import extract_insights
from .stages.query_extractor import extract_queries_for_variable

MAX_FINDINGS_FOR_EXTRACTION_PER_VARIABLE = 20


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
) -> list[Match]:
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
        return []
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
        return []

    if progress_callback:
        progress_callback("search")
    findings_by_query = _search_all(flat, search_client)
    if not findings_by_query:
        return []

    findings_by_attribute: dict[str, list[Finding]] = {}
    for (attribute_ref, _query), findings in findings_by_query.items():
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
    return matches


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
    workers = max(1, min(8, len(attributes)))

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
    workers = max(1, min(8, len(items)))

    def one(item: tuple[str, list[Finding]]) -> list[Insight]:
        attribute_ref, findings = item
        capped = findings[:MAX_FINDINGS_FOR_EXTRACTION_PER_VARIABLE]
        return extract_insights(
            capped,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            attribute_ref=attribute_ref,
            attribute_description=attribute_descriptions.get(attribute_ref, ""),
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(one, items))

    insights: list[Insight] = []
    for variable_insights in results:
        insights.extend(variable_insights)
    return insights


def _search_all(
    attribute_queries: list[tuple[str, str]],
    search_client: SearchClientProtocol,
) -> dict[tuple[str, str], list[Finding]]:
    """Run all queries in parallel. Returns mapping from (attribute, query) to findings."""
    if not attribute_queries:
        return {}
    workers = max(1, min(8, len(attribute_queries)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(
            executor.map(
                lambda attribute_query: searcher_run(
                    attribute_query[1], llm_client=search_client
                ),
                attribute_queries,
            )
        )
    return {
        attribute_query: findings
        for attribute_query, findings in zip(attribute_queries, results)
    }


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
