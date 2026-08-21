"""Semantic Scholar adapter executed through an injected ToolUniverse connector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import (
    active_tracks,
    build_semantic_scholar_query,
    queries_for_track,
)
from .planning import request_lineage

TOOLUNIVERSE_INTEGRATION = "tooluniverse"
SEARCH_TOOL = "SemanticScholar_search_papers"
MAX_RESULTS = 10
MAX_EXCERPT_CHARS = 16_000
# The issued Semantic Scholar key is limited to one request per second across
# all endpoints. Stay deliberately below that threshold rather than relying on
# ToolUniverse's generic keyed-account assumption.
MIN_REQUEST_INTERVAL_SECONDS = 1.1


class SemanticScholarSource:
    spec = SourceSpec(
        key="semantic_scholar",
        label="Semantic Scholar",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL,),
        attribution=SourceAttribution(
            label="Semantic Scholar",
            url="https://www.semanticscholar.org/?utm_source=api",
            prefix="Academic metadata provided by",
        ),
        evidence_class="literature",
        jurisdiction="global",
        reads=("text", "condition", "intervention", "product", "population", "outcome", "subject"),
        feeds=("insights",),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for track in active_tracks(intent):
            queries = queries_for_track(intent, track)
            intent_ids, input_queries, document_refs = request_lineage(queries)
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=build_semantic_scholar_query(intent, track, queries),
                    tracks=(track,),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TOOLUNIVERSE_INTEGRATION,
                    operation=SEARCH_TOOL,
                    options=(
                        ("limit", str(MAX_RESULTS)),
                        # Scout needs evidence text, not title-only metadata.
                        ("include_abstract", "true"),
                    ),
                )
            )
        return requests

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        connector = runtime.integrations.get(TOOLUNIVERSE_INTEGRATION)
        if connector is None or not callable(getattr(connector, "run", None)):
            raise RuntimeError("ToolUniverse connector is not configured")
        result = connector.run(
            SEARCH_TOOL,
            {
                "query": request.query,
                "limit": int(request.option("limit", str(MAX_RESULTS))),
                "include_abstract": request.option("include_abstract") == "true",
            },
        )
        records = _records(result)
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in records:
            url = _paper_url(record)
            if not url:
                continue
            excerpt = _text(record.get("abstract")) or _text(record.get("tldr"))
            if len(excerpt) > MAX_EXCERPT_CHARS:
                excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."
            findings.append(
                Finding(
                    url=url,
                    title=_text(record.get("title")) or url,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=excerpt or None,
                    source=self.spec.key,
                )
            )
        return findings

def _records(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        if result.get("status") == "error" or result.get("error"):
            raise RuntimeError(str(result.get("error") or "Semantic Scholar failed"))
        result = result.get("data", result.get("results", []))
    if not isinstance(result, list):
        raise RuntimeError("Semantic Scholar returned an unexpected result shape")
    records: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            raise RuntimeError(str(item["error"]))
        records.append(item)
    return records


def _paper_url(record: dict[str, Any]) -> str:
    doi_url = _text(record.get("doi_url"))
    if doi_url:
        return doi_url
    doi = _text(record.get("doi"))
    if doi:
        return f"https://doi.org/{doi.removeprefix('https://doi.org/')}"
    url = _text(record.get("url"))
    if url:
        return url
    paper_id = _text(record.get("paper_id") or record.get("paperId"))
    return f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
