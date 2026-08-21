"""OpenAI web-search source adapter."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.searcher import search
from .planning import request_lineage


class WebSource:
    spec = SourceSpec(
        key="web",
        label="Web",
        worker_limit=32,
        evidence_class="general",
        jurisdiction="global",
        reads=("text",),
        feeds=("insights",),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for query in intent.queries:
            intent_ids, input_queries, document_refs = request_lineage([query])
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=query.text,
                    tracks=query.tracks,
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        return search(
            request.query,
            runtime.llm_client,
            max_tokens=max_tokens,
            max_uses=max_uses,
        )
