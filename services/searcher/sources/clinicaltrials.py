"""ClinicalTrials.gov source adapter and structured-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..relevance import rank_records
from ..stages.clinicaltrials import (
    clinicaltrial_to_finding,
    fetch_clinicaltrials_studies,
)
from .literature import active_tracks
from .planning import facet_groups, request_lineage

MAX_CANDIDATES = 100
MAX_RESULTS = 20


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
        for scope, queries in facet_groups(
            intent,
            fields=("condition", "intervention"),
            fallbacks={
                "condition": intent.indication or intent.topic,
                "intervention": intent.intervention_class,
            },
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            condition = scope["condition"]
            intervention = scope["intervention"]
            native_query = f"condition:{condition}"
            if intervention:
                native_query += f" AND intervention:{intervention}"
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=native_query,
                    tracks=tuple(active_tracks(intent)),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    options=(
                        ("condition", condition),
                        ("intervention", intervention),
                        ("candidate_limit", str(MAX_CANDIDATES)),
                        ("ranking", "all_input_queries"),
                    ),
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        studies = fetch_clinicaltrials_studies(
            condition=request.option("condition"),
            intervention=request.option("intervention"),
            term="",
            max_results=int(
                request.option("candidate_limit", str(MAX_CANDIDATES))
            ),
        )
        ranked = rank_records(studies, request.input_queries, limit=MAX_RESULTS)
        findings = [
            clinicaltrial_to_finding(study, request.query)
            for study in ranked
        ]
        return [finding for finding in findings if finding is not None]
