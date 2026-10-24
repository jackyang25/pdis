"""PubMed/PMC source adapter and its scientific-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.pubmed import NCBI_RATE_GROUP, search_pubmed
from .literature import active_tracks, build_pubmed_query, queries_for_track
from .planning import request_lineage


class PubMedSource:
    spec = SourceSpec(
        key="pubmed",
        label="PubMed",
        worker_limit=8,
        evidence_class="literature",
        jurisdiction="global",
        reads=("text", "condition", "intervention", "product", "population", "outcome", "subject"),
        feeds=("insights",),
        honors_date_bound=True,
        # Pacing is NCBI's, shared with every E-utilities call and dependent on whether
        # a key is configured, so the stage paces each call itself (`NCBI_RATE_GROUP`).
        rate_group=NCBI_RATE_GROUP,
        max_results=20,
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
                    query=build_pubmed_query(intent, track, queries),
                    tracks=(track,),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    options=(("published_since", intent.published_since),)
                    if intent.published_since
                    else (),
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int):
        return search_pubmed(
            request.query,
            runtime,
            max_results=self.spec.max_results,
            published_since=request.option("published_since"),
        )
