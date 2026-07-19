"""ClinicalTrials.gov source adapter and structured-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.clinicaltrials import search_clinicaltrials


class ClinicalTrialsSource:
    spec = SourceSpec(
        key="clinicaltrials",
        label="ClinicalTrials.gov",
        worker_limit=8,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        if not intent.queries:
            return []
        query = next(
            (item for item in intent.queries if "general" in item.tracks),
            intent.queries[0],
        )
        words = [
            word
            for word in query.text.split()
            if not word.lower().startswith(("site:", "http://", "https://"))
        ]
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=" ".join([intent.topic, *words[:12]]),
                tracks=query.tracks,
                document_refs=query.document_refs,
                options=(
                    ("condition", intent.indication),
                    ("intervention", intent.intervention_class),
                ),
            )
        ]

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        return search_clinicaltrials(
            request.query,
            condition=request.option("condition"),
            intervention=request.option("intervention"),
        )
