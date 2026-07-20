"""Open Targets entity evidence via one allowlisted ToolUniverse operation."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks
from .planning import request_lineage
from .tooluniverse_records import TOOLUNIVERSE_INTEGRATION, run_tool, text

SEARCH_TOOL = "OpenTargets_multi_entity_search_by_query_string"
MAX_RESULTS = 10


class OpenTargetsSource:
    spec = SourceSpec(
        key="open_targets",
        label="Open Targets",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL,),
        evidence_domains=("biological",),
        attribution=SourceAttribution(
            label="Open Targets Platform",
            url="https://platform.opentargets.org/",
            prefix="Target–disease data provided by",
        ),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        search_terms = list(
            dict.fromkeys(
                term
                for term in (
                    intent.indication.strip(),
                    *(entity.name for entity in intent.entities),
                )
                if term
            )
        )[:4]
        if not search_terms:
            search_terms = [intent.topic]
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=f"entity:{term}",
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                connector=TOOLUNIVERSE_INTEGRATION,
                operation=SEARCH_TOOL,
                options=(("query_string", term), ("limit", str(MAX_RESULTS))),
            )
            for term in search_terms
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        result = run_tool(
            runtime,
            SEARCH_TOOL,
            {
                "queryString": request.option("query_string"),
                "entityNames": ["target", "disease", "drug"],
                "page": {"index": 0, "size": MAX_RESULTS},
            },
        )
        if not isinstance(result, dict):
            raise RuntimeError("Open Targets returned an unexpected result shape")
        if result.get("status") == "error" or result.get("error"):
            raise RuntimeError(str(result.get("error") or "Open Targets failed"))
        data = result.get("data")
        search = data.get("search") if isinstance(data, dict) else None
        hits = search.get("hits", []) if isinstance(search, dict) else []
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            entity_id = text(hit.get("id"))
            entity_type = text(hit.get("entity")).lower()
            if not entity_id or entity_type not in {"target", "disease", "drug"}:
                continue
            findings.append(
                Finding(
                    url=(
                        "https://platform.opentargets.org/"
                        f"{entity_type}/{quote(entity_id)}"
                    ),
                    title=text(hit.get("name")) or entity_id,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=text(hit.get("description")) or None,
                    source=self.spec.key,
                )
            )
        return findings
