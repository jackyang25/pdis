"""Translate Scout units into Searcher's provider-agnostic retrieval intent.

Scout owns document meaning and block lineage. Searcher source adapters own how
that neutral intent becomes native web, literature, registry, or future-tool
requests. No source key or query grammar is hardcoded in this service.
"""

from __future__ import annotations

from services.searcher import RetrievalIntent, SourceQueryIntent

from ..models import Attribute, QueryIntent


def build_retrieval_intents(
    attribute_queries: dict[str, list[QueryIntent]],
    attributes: list[Attribute],
    *,
    indication: str,
    intervention_class: str,
) -> list[RetrievalIntent]:
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    return [
        RetrievalIntent(
            scope_ref=attribute_ref,
            topic=attribute.name.replace("_", " "),
            description=attribute.description,
            indication=indication,
            intervention_class=intervention_class,
            queries=tuple(
                SourceQueryIntent(
                    text=query.text,
                    tracks=tuple(query.tracks),
                    document_refs=tuple(query.doc_block_ids),
                )
                for query in queries
            ),
        )
        for attribute_ref, queries in attribute_queries.items()
        if queries and (attribute := attributes_by_name.get(attribute_ref)) is not None
    ]
