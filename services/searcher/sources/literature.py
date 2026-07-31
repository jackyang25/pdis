"""Source-native compilers for scientific-literature adapters.

These compilers translate stated query facets into each provider's grammar. They
do not interpret query prose: a consumer that knows the condition, intervention,
population, and outcome states them on the intent, so no term extraction,
stopword list, or track-to-keyword table is needed or permitted here. Recovering
meaning from finished text is how an authored query loses its institution names
and phrase structure.
"""

from __future__ import annotations

import re

from ..models import RetrievalIntent, SourceQueryIntent

_WEB_OPERATOR = re.compile(
    r"\b(?:site|filetype|inurl|intitle|related|cache|url):\S+",
    re.IGNORECASE,
)
_BARE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
# PubMed treats these as grammar rather than content.
_PUBMED_RESERVED = re.compile(r'[()\[\]"]')


def active_tracks(intent: RetrievalIntent) -> list[str]:
    return list(
        dict.fromkeys(track for query in intent.queries for track in query.tracks)
    ) or ["general"]


def queries_for_track(
    intent: RetrievalIntent,
    track: str,
) -> list[SourceQueryIntent]:
    return [
        query
        for query in intent.queries
        if track in query.tracks or (track == "general" and not query.tracks)
    ]


def clean_query_text(text: str) -> str:
    """Remove web-only operators without changing the semantic words."""
    return " ".join(_BARE_URL.sub(" ", _WEB_OPERATOR.sub(" ", text)).split())


def query_phrases(
    intent: RetrievalIntent,
    query: SourceQueryIntent,
) -> list[str]:
    """Return one query's stated phrases, falling back to its intent scope.

    A consumer that stated no facets still carries meaning in its text, so the
    text is used whole rather than dismantled.
    """
    phrases = [clean_query_text(phrase) for phrase in query.facets.phrases()]
    if not phrases:
        fallback = clean_query_text(query.text) or clean_query_text(intent.topic)
        phrases = [fallback] if fallback else []
    return list(dict.fromkeys(phrase for phrase in phrases if phrase))


def scope_phrases(intent: RetrievalIntent) -> list[str]:
    """Return the disease and product anchors every query in this intent shares."""
    anchors = [clean_query_text(intent.indication)]
    anchors.extend(
        clean_query_text(entity.name)
        for entity in intent.entities
        if entity.entity_type
        in {"disease", "pathogen", "vaccine", "drug", "compound", "device"}
    )
    return list(dict.fromkeys(anchor for anchor in anchors if anchor))


def build_pubmed_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
) -> str:
    """Compile the track's intents into one bounded PubMed Boolean expression.

    Shared anchors are ANDed once. Each query contributes its own parenthesized
    clause, so several questions travel in one request without their phrases
    mixing into each other.
    """
    del track
    anchors = [_pubmed_phrase(phrase) for phrase in scope_phrases(intent)]
    clauses: list[str] = []
    for query in queries:
        phrases = [
            _pubmed_phrase(phrase)
            for phrase in query_phrases(intent, query)
            if phrase not in scope_phrases(intent)
        ]
        if not phrases:
            continue
        clause = " AND ".join(dict.fromkeys(phrases))
        clauses.append(clause if len(phrases) == 1 else f"({clause})")
    clauses = list(dict.fromkeys(clauses))
    parts = [*anchors]
    if clauses:
        parts.append("(" + " OR ".join(clauses) + ")" if len(clauses) > 1 else clauses[0])
    return " AND ".join(parts)


def build_semantic_scholar_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
    *,
    max_queries: int = 3,
    max_phrases: int = 8,
) -> str:
    """Compile a focused plain-text query that keeps stated phrases intact.

    Semantic Scholar has no Boolean grammar, so one request cannot separate many
    questions. Phrases are carried whole rather than split into interleaved terms,
    and the request is bounded to the leading queries because a plain-text engine
    degrades as concepts accumulate. Every contributing intent stays inspectable
    in request lineage regardless of what this text includes.
    """
    del track
    phrases: list[str] = []
    for query in queries[:max_queries]:
        for phrase in query_phrases(intent, query):
            if phrase not in phrases:
                phrases.append(phrase)
    # Anchors only earn a slot when no retained phrase already carries them.
    for anchor in scope_phrases(intent):
        if not any(anchor.casefold() in phrase.casefold() for phrase in phrases):
            phrases.insert(0, anchor)
    return " ".join(phrases[:max_phrases])


def _pubmed_phrase(phrase: str) -> str:
    """Quote a multi-word phrase so PubMed matches it as one concept."""
    cleaned = " ".join(_PUBMED_RESERVED.sub(" ", phrase).split())
    if not cleaned:
        return ""
    return f'"{cleaned}"' if " " in cleaned else cleaned
