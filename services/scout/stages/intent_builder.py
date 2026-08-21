"""Build Searcher's provider-agnostic retrieval intents from Scout units.

Scout owns document meaning and block lineage. Searcher source adapters own how
that neutral intent becomes native web, literature, registry, or future-tool
requests. No source key or query grammar is hardcoded in this service.
"""

from __future__ import annotations

import hashlib

from services.searcher import RetrievalEntity, RetrievalIntent, SourceQueryIntent

from ..models import (
    PROGRAM_QUERY_SETS,
    PROGRAM_SCOPE_KEY,
    Attribute,
    QueryIntent,
    RetrievalScopeLedger,
)


def build_program_intents(
    scope: RetrievalScopeLedger,
    *,
    published_since: str = "",
) -> list[tuple[RetrievalIntent, tuple[str, ...]]]:
    """Build the run's own intents, paired with the lanes each is planned against.

    Returned with their lanes rather than planned here, because which lanes a set targets
    is the set's own declaration and `plan_requests` takes sources per call. The caller
    plans each pair, which keeps this function free of the source registry.

    Every intent carries `scope_ref = PROGRAM_SCOPE_KEY`, so its findings land in their
    own bucket. Nothing else changes: `_search_all` keys by `scope_ref` already, and the
    development landscape ignores the key entirely.

    Text is composed rather than authored, which is the one place this differs from the
    per-variable path. There is no document variable to read a question out of - the
    subject is the event, and the scope is the run's own condition and class. The web
    lane reads only query text, so the scope has to be in the text to reach it at all.
    """
    condition = scope.value("condition")
    intervention = scope.value("intervention")
    if not condition:
        # Without a condition there is no program to ask about, and a bare event subject
        # would return announcements from every field of medicine.
        return []
    built: list[tuple[RetrievalIntent, tuple[str, ...]]] = []
    for name, query_set in PROGRAM_QUERY_SETS.items():
        # A set may declare no subjects, which means its lane's request is built from the
        # run's own scope rather than from a phrase - WHO GHO searches indicator names by
        # the condition and never reads query text. It still gets one query, because a
        # request with no query carries no lineage, and a request nothing can be traced
        # back to is one a reader cannot ask about.
        subjects = query_set.subjects or ("",)
        queries = tuple(
            SourceQueryIntent(
                text=" ".join(
                    part for part in (condition, intervention, subject) if part
                ),
                tracks=(name,),
            )
            for subject in subjects
        )
        built.append(
            (
                RetrievalIntent(
                    scope_ref=PROGRAM_SCOPE_KEY,
                    topic=name,
                    description=query_set.reason,
                    indication=condition,
                    intervention_class=intervention,
                    region=scope.value("region"),
                    published_since=published_since,
                    queries=queries,
                ),
                query_set.lanes,
            )
        )
    return built


def build_retrieval_intents(
    attribute_queries: dict[str, list[QueryIntent]],
    attributes: list[Attribute],
    *,
    scope: RetrievalScopeLedger,
    published_since: str = "",
) -> list[RetrievalIntent]:
    """Copy the run's scope onto every intent, and the attribute's meaning onto its own.

    One ledger rather than a parameter per dimension. Loose parameters were how region
    went missing: adding a dimension meant adding an argument here, threading it through
    the caller, and remembering both - and nothing failed when you did neither. A ledger
    is complete by construction, so a new dimension arrives filled or explicitly unset.
    """
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    return [
        RetrievalIntent(
            scope_ref=attribute_ref,
            topic=attribute.name.replace("_", " "),
            description=attribute.description,
            indication=scope.value("condition"),
            intervention_class=scope.value("intervention"),
            # Carried on every attribute's intent, which is the point: an attribute
            # whose own text never names a country is still searched in the right one.
            region=scope.value("region"),
            # Stated on the intent so a source that can bound at the provider does,
            # rather than every source answering without the window and the run
            # discarding what it already paid for.
            published_since=published_since,
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
                    facets=query.facets,
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
            *query.facets.phrases(),
        )
    )
    return "q-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
