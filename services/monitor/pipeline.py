"""Stateless monitor pipeline.

Orchestrates: chunker (parse + section label) -> per-section query_extractor
(LLM) -> searcher (web) -> per-section insight_extractor (LLM) ->
drift_classifier (LLM). Reuses chunker and searcher via their public
contracts only.

v0 does NOT use benchmarker; claim-level comparison is deferred to v1.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.chunker import (
    ContentBlock,
    find_config as chunker_find_config,
    run_pipeline as chunker_run,
)
from services.searcher import Finding, run_pipeline as searcher_run

from .models import (
    Insight,
    Match,
    MonitorTypeConfig,
    OpenAIClientProtocol,
    SearchClientProtocol,
)
from .stages.drift_classifier import classify_drift
from .stages.insight_extractor import extract_insights
from .stages.query_extractor import extract_queries_for_section

MAX_FINDINGS_FOR_EXTRACTION_PER_SECTION = 20
SECTIONS_TO_SKIP = {"Document Metadata", "Other", None, ""}


def run_pipeline(
    file_paths: list[str],
    *,
    config: MonitorTypeConfig,
    openai_client: OpenAIClientProtocol,
    search_client: SearchClientProtocol,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
    progress_callback=None,
) -> list[Match]:
    """Per-section monitor pipeline.

    Section-labels each uploaded doc, generates queries per section,
    searches the web in parallel, extracts Insights per section (tagged
    with section_label), and classifies drift against the doc.
    """
    if progress_callback:
        progress_callback("parse")
    blocks = _parse_all_docs(
        file_paths,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
        openai_client=openai_client,
    )

    sections = _group_by_section(blocks)
    if not sections:
        return []

    if progress_callback:
        progress_callback("queries")
    section_queries = _extract_queries_all_sections(
        sections, config, openai_client, indication=indication
    )
    flat: list[tuple[str, str]] = [
        (label, query) for label, queries in section_queries.items() for query in queries
    ]
    if not flat:
        return []

    if progress_callback:
        progress_callback("search")
    findings_by_query = _search_all(flat, search_client)
    if not findings_by_query:
        return []

    findings_by_section: dict[str, list[Finding]] = {}
    for (label, _query), findings in findings_by_query.items():
        findings_by_section.setdefault(label, [])
        for finding in findings:
            if not any(existing.url == finding.url for existing in findings_by_section[label]):
                findings_by_section[label].append(finding)

    if progress_callback:
        progress_callback("insights")
    insights: list[Insight] = []
    for label, section_findings in findings_by_section.items():
        capped = section_findings[:MAX_FINDINGS_FOR_EXTRACTION_PER_SECTION]
        section_insights = extract_insights(
            capped,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            section_label=label,
        )
        insights.extend(section_insights)

    _stamp(
        insights,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
    )

    if progress_callback:
        progress_callback("classify")
    doc_excerpts = _doc_excerpts_for_classifier(sections)
    matches = classify_drift(
        doc_excerpts,
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
    openai_client: OpenAIClientProtocol,
) -> list[ContentBlock]:
    """Parse + label each doc via chunker (with config to enable the mapper)."""
    try:
        chunker_config = chunker_find_config(org, source_type, intervention_class)
    except LookupError as exc:
        raise LookupError(
            f"Chunker config missing for ({org}, {source_type}, {intervention_class}). "
            f"Monitor needs section labeling to scope queries per variable. "
            f"Original error: {exc}"
        )

    blocks: list[ContentBlock] = []
    for file_path in file_paths:
        doc_id = Path(file_path).stem
        doc_blocks = chunker_run(
            file_path,
            doc_id,
            config=chunker_config,
            llm_client=openai_client,
            org=org,
            source_type=source_type,
            intervention_class=intervention_class,
            indication=indication,
        )
        blocks.extend(doc_blocks)
    return blocks


def _group_by_section(blocks: list[ContentBlock]) -> dict[str, list[ContentBlock]]:
    """Group blocks by section_label; drop metadata/other/empty labels."""
    grouped: dict[str, list[ContentBlock]] = {}
    for block in blocks:
        label = block.section_label
        if label in SECTIONS_TO_SKIP:
            continue
        grouped.setdefault(label, []).append(block)
    return grouped


def _extract_queries_all_sections(
    sections: dict[str, list[ContentBlock]],
    config: MonitorTypeConfig,
    openai_client: OpenAIClientProtocol,
    *,
    indication: str,
) -> dict[str, list[str]]:
    """One query-extractor call per section, sequential (fast LLM calls)."""
    out: dict[str, list[str]] = {}
    for label, section_blocks in sections.items():
        section_text = "\n".join(block.content for block in section_blocks if block.content)
        queries = extract_queries_for_section(
            label,
            section_text,
            config,
            openai_client,
            indication=indication,
            queries_per_section=config.queries_per_section,
        )
        if queries:
            out[label] = queries
    return out


def _search_all(
    section_queries: list[tuple[str, str]],
    search_client: SearchClientProtocol,
) -> dict[tuple[str, str], list[Finding]]:
    """Run all queries in parallel. Returns mapping from (section, query) to findings."""
    if not section_queries:
        return {}
    workers = max(1, len(section_queries))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(
            executor.map(
                lambda section_query: searcher_run(
                    section_query[1], llm_client=search_client
                ),
                section_queries,
            )
        )
    return {
        section_query: findings
        for section_query, findings in zip(section_queries, results)
    }


def _doc_excerpts_for_classifier(
    sections: dict[str, list[ContentBlock]],
) -> list[str]:
    """Build per-section excerpts for the drift_classifier prompt."""
    out: list[str] = []
    for label, blocks in sections.items():
        text = "\n".join(block.content for block in blocks if block.content)
        out.append(f"### {label}\n{text}")
    return out


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
