"""PubMed/PMC source adapter and its scientific-query policy."""

from __future__ import annotations

from ..models import RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec
from ..stages.pubmed import search_pubmed


class PubMedSource:
    spec = SourceSpec(key="pubmed", label="PubMed", worker_limit=8)

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        active_tracks = list(
            dict.fromkeys(track for query in intent.queries for track in query.tracks)
        ) or ["general"]
        requests: list[SearchRequest] = []
        for track in active_tracks:
            queries = [
                query
                for query in intent.queries
                if track in query.tracks or (track == "general" and not query.tracks)
            ]
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=_literature_query(intent, track, queries),
                    tracks=(track,),
                    document_refs=tuple(
                        dict.fromkeys(
                            ref for query in queries for ref in query.document_refs
                        )
                    ),
                )
            )
        return requests

    def search(self, request, runtime: SearchRuntime, *, max_tokens: int, max_uses: int):
        return search_pubmed(
            request.query,
            api_key=runtime.ncbi_api_key,
        )


def _literature_query(intent: RetrievalIntent, track: str, queries) -> str:
    qualifiers = {
        "general": "clinical evidence",
        "geographic": "low middle income countries implementation",
        "counterfactual": "failure limitation adverse outcome",
        "precedent": "historical trial prior development",
    }
    # Web operators are meaningful intent hints but invalid/noisy PubMed syntax.
    # Keep the document-shaped terms while removing provider-specific operators.
    intent_text = " ".join(
        word
        for query in queries[:2]
        for word in query.text.split()
        if not word.lower().startswith(("site:", "http://", "https://"))
    )
    return " ".join(
        part
        for part in (
            intent.indication,
            intent.intervention_class,
            intent.topic,
            intent_text,
            qualifiers.get(track, "evidence"),
        )
        if part
    )
