"""ClinicalTrials.gov source adapter and structured-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.clinicaltrials import (
    clinicaltrial_to_finding,
    fetch_clinicaltrials_studies,
)
from .literature import active_tracks
from .planning import facet_groups, planned_variants, request_lineage

MAX_RESULTS = 20
# CT.gov publishes no hard rate limit but asks clients to be considerate, and Scout
# fans out many requests at once: about eight calls a second, process-wide.
MIN_REQUEST_INTERVAL_SECONDS = 0.12


class ClinicalTrialsSource:
    spec = SourceSpec(
        key="clinicaltrials",
        label="ClinicalTrials.gov",
        worker_limit=8,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        evidence_domains=("clinical", "safety"),
        evidence_class="registry",
        jurisdiction="us",
        reads=("text", "condition", "intervention", "product", "region"),
        feeds=("insights", "landscape"),
        # `filter.advanced` on the study's first-posted date.
        honors_date_bound=True,
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        if not intent.queries:
            return []
        groups = facet_groups(
            intent,
            fields=("condition", "intervention"),
            fallbacks={
                "condition": intent.indication or intent.topic,
                "intervention": intent.intervention_class,
            },
            anchors=("condition",),
        )
        requests: list[SearchRequest] = []
        # Unscoped first, then the region-narrowed twin - added beside it, never instead
        # of it. A programme in one region still has to be judged against trials run
        # elsewhere, so restricting every request to its own geography would answer a
        # narrower question than the one asked.
        for scope, queries, location in planned_variants(
            groups,
            region=intent.scope("region"),
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            condition = scope["condition"]
            intervention = scope["intervention"]
            native_query = f"condition:{condition}"
            if intervention:
                native_query += f" AND intervention:{intervention}"
            if location:
                native_query += f" AND location:{location}"
            options = [
                ("condition", condition),
                ("intervention", intervention),
                ("region", location),
            ]
            if intent.published_since:
                options.append(("published_since", intent.published_since))
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=native_query,
                    tracks=tuple(active_tracks(intent)),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    options=tuple(options),
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int):
        studies = fetch_clinicaltrials_studies(
            runtime,
            rate_group=self.spec.rate_group,
            interval_seconds=self.spec.request_interval_seconds,
            condition=request.option("condition"),
            intervention=request.option("intervention"),
            region=request.option("region"),
            first_posted_since=request.option("published_since"),
            max_results=self.spec.max_results,
        )
        findings = [clinicaltrial_to_finding(study, request.query) for study in studies]
        return [finding for finding in findings if finding is not None]
