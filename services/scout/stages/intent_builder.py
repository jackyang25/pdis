"""Build Searcher's provider-agnostic retrieval intents from Scout units.

Scout owns document meaning and block lineage. Searcher source adapters own how
that neutral intent becomes native web, literature, registry, or future-tool
requests. No source key or query grammar is hardcoded in this service.
"""

from __future__ import annotations

import hashlib

from services.searcher import RetrievalEntity, RetrievalIntent, SourceQueryIntent

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
            document_target=attribute.document_target,
            definition_mode=attribute.definition_mode,
            evidence_domain=attribute.evidence_domain,
            entities=tuple(
                RetrievalEntity(
                    name=entity.name,
                    entity_type=entity.entity_type,
                    identifier=entity.identifier,
                )
                for entity in attribute.entities
            ),
            queries=tuple(
                SourceQueryIntent(
                    text=query.text,
                    tracks=tuple(query.tracks),
                    document_refs=tuple(query.doc_block_ids),
                    target_refs=tuple(query.target_ids),
                    intent_id=_intent_id(attribute_ref, query),
                )
                for query in queries
            ),
        )
        for attribute_ref, queries in attribute_queries.items()
        if queries and (attribute := attributes_by_name.get(attribute_ref)) is not None
    ]


def _intent_id(attribute_ref: str, query: QueryIntent) -> str:
    """Derive a stable, source-neutral identity at Scout's ownership boundary."""
    material = "\n".join(
        (
            attribute_ref,
            query.text,
            *query.tracks,
            *query.doc_block_ids,
            *query.target_ids,
        )
    )
    return "q-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
