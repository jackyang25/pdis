"""ClinicalTrials.gov source adapter and structured-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.clinicaltrials import search_clinicaltrials
from .literature import active_tracks, build_registry_query, queries_for_track
from .planning import request_lineage


class ClinicalTrialsSource:
    spec = SourceSpec(
        key="clinicaltrials",
        label="ClinicalTrials.gov",
        worker_limit=8,
        evidence_domains=("clinical", "safety"),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        if not intent.queries:
            return []
        requests: list[SearchRequest] = []
        for track in active_tracks(intent):
            queries = queries_for_track(intent, track)
            intent_ids, input_queries, document_refs = request_lineage(queries)
            native_query = build_registry_query(queries)
            if not native_query:
                native_query = intent.topic
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=native_query,
                    tracks=(track,),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    options=(
                        ("condition", intent.indication),
                        ("intervention", intent.intervention_class),
                    ),
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        return search_clinicaltrials(
            request.query,
            condition=request.option("condition"),
            intervention=request.option("intervention"),
        )
