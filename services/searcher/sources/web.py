"""OpenAI web-search source adapter."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.searcher import search


class WebSource:
    spec = SourceSpec(key="web", label="Web", worker_limit=32)

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=query.text,
                tracks=query.tracks,
                document_refs=query.document_refs,
            )
            for query in intent.queries
        ]

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        return search(
            request.query,
            runtime.llm_client,
            max_tokens=max_tokens,
            max_uses=max_uses,
        )
