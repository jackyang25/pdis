"""PubMed/PMC source adapter and its scientific-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.pubmed import search_pubmed
from .literature import active_tracks, build_pubmed_query, queries_for_track
from .planning import request_lineage


class PubMedSource:
    spec = SourceSpec(key="pubmed", label="PubMed", worker_limit=8)

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for track in active_tracks(intent):
            queries = queries_for_track(intent, track)
            intent_ids, input_queries, document_refs = request_lineage(queries)
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=build_pubmed_query(intent, track, queries),
                    tracks=(track,),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        return search_pubmed(
            request.query,
            api_key=runtime.ncbi_api_key,
        )
