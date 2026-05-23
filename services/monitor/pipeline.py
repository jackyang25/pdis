"""Stateless monitor pipeline.

Orchestrates: chunker (parse docs) -> query_extractor (LLM) -> searcher
(web) -> insight_extractor (LLM). Reuses chunker and searcher via their
public contracts only.

v0 does NOT use benchmarker; doc claims comparison is deferred to v1.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.chunker import run_pipeline as chunker_run
from services.searcher import Finding, run_pipeline as searcher_run

from .models import (
    Insight,
    MonitorTypeConfig,
    OpenAIClientProtocol,
    SearchClientProtocol,
)
from .stages.insight_extractor import extract_insights
from .stages.query_extractor import extract_queries

MAX_PER_DOC_CHARS = 4000


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
) -> list[Insight]:
    """Run the full monitor pipeline. Stateless.

    Args:
        file_paths: uploaded document paths.
        config: monitor's domain config (per 4-primitive triple).
        openai_client: used by query_extractor + insight_extractor.
        search_client: used by searcher.
        org/source_type/intervention_class/indication: stamped onto every Insight.

    Returns:
        list[Insight] - empty if no queries or no findings produced.
    """
    if progress_callback:
        progress_callback("parse")
    doc_excerpts = [_parse_doc_excerpt(p) for p in file_paths]

    if progress_callback:
        progress_callback("queries")
    queries = extract_queries(
        doc_excerpts, config, openai_client, indication=indication,
    )
    if not queries:
        return []

    if progress_callback:
        progress_callback("search")
    findings = _search_all(queries, search_client)
    if not findings:
        return []

    if progress_callback:
        progress_callback("insights")
    insights = extract_insights(
        findings,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
    )

    _stamp(insights, org=org, source_type=source_type,
           intervention_class=intervention_class, indication=indication)
    return insights


def _parse_doc_excerpt(file_path: str) -> str:
    """Parse a doc via chunker (no mapper) and return concatenated content."""
    doc_id = Path(file_path).stem
    blocks = chunker_run(file_path, doc_id)  # no config/llm_client -> skips mapper
    text = "\n".join(b.content for b in blocks if getattr(b, "content", ""))
    if len(text) > MAX_PER_DOC_CHARS:
        text = text[:MAX_PER_DOC_CHARS] + "\n...[truncated]"
    return f"FILE: {doc_id}\n{text}"


def _search_all(
    queries: list[str],
    search_client: SearchClientProtocol,
) -> list[Finding]:
    """Run searcher in parallel across queries. Concat and dedupe by URL.

    Worker count equals query count - `num_queries` is the natural bound
    (config-controlled, small). No separate cap.
    """
    if not queries:
        return []
    workers = max(1, len(queries))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        per_query = list(
            executor.map(lambda q: searcher_run(q, llm_client=search_client), queries)
        )
    seen: set[str] = set()
    out: list[Finding] = []
    for findings in per_query:
        for f in findings:
            if f.url in seen:
                continue
            seen.add(f.url)
            out.append(f)
    return out


def _stamp(
    insights: list[Insight],
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> None:
    for ins in insights:
        ins.org = org
        ins.source_type = source_type
        ins.intervention_class = intervention_class
        ins.indication = indication
