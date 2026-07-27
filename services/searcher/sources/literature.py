"""Source-native compilers for scientific-literature adapters."""

from __future__ import annotations

import re

from ..models import RetrievalIntent, SourceQueryIntent

_WEB_OPERATOR = re.compile(
    r"\b(?:site|filetype|inurl|intitle|related|cache|url):\S+",
    re.IGNORECASE,
)
_BARE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_TERM = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_LOW_SIGNAL_TERMS = {
    "a",
    "an",
    "and",
    "against",
    "current",
    "evidence",
    "for",
    "in",
    "latest",
    "of",
    "on",
    "primary",
    "pubmed",
    "recent",
    "research",
    "study",
    "target",
    "the",
    "to",
    "variable",
    "who",
}
_TRACK_TERMS = {
    "general": ("clinical", "evidence"),
    "geographic": ("implementation", "population"),
    "counterfactual": ("failure", "limitation", "adverse"),
    "precedent": ("historical", "development", "trial"),
}


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


def build_pubmed_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
) -> str:
    """Compile neutral intents into one bounded PubMed Boolean expression.

    The document-specific neutral queries are the semantic input. Canonical
    indication/entity anchors keep the OR-packed request on topic; the adapter
    only translates that input into PubMed grammar and never substitutes a
    generic field description for it.
    """
    groups = _anchor_groups(intent)
    track_terms = () if track == "general" else _TRACK_TERMS.get(track, ())
    anchors = " AND ".join(_pubmed_group(group) for group in groups if group)
    clauses = [
        _pubmed_clause(terms)
        for query in queries
        if (terms := _native_query_terms(query.text, intent, limit=10))
    ]
    clauses = list(dict.fromkeys(clauses))
    if track_terms:
        clauses.append(_pubmed_group(list(track_terms)))
    native = "(" + " OR ".join(clauses) + ")" if clauses else ""
    return " AND ".join(part for part in (anchors, native) if part)


def build_semantic_scholar_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
    *,
    max_terms: int = 24,
) -> str:
    """Compile a focused plain-text query without dropping neutral intents.

    Semantic Scholar has no Boolean request grammar, so terms are interleaved
    across every input intent before generic catalog wording is considered.
    This keeps one rate-limited request document-specific while its complete
    input bundle remains inspectable in request lineage.
    """
    output = [term for group in _anchor_groups(intent) for term in group]
    output = list(dict.fromkeys(output))
    seen = {term.casefold() for term in output}
    query_terms = [
        _native_query_terms(query.text, intent, limit=12) for query in queries
    ]
    for offset in range(max((len(terms) for terms in query_terms), default=0)):
        for terms in query_terms:
            if offset >= len(terms):
                continue
            term = terms[offset]
            if term.casefold() not in seen:
                output.append(term)
                seen.add(term.casefold())
    track_terms = () if track == "general" else _TRACK_TERMS.get(track, ("evidence",))
    for term in track_terms:
        if term.casefold() not in seen:
            output.append(term)
            seen.add(term.casefold())

    if len(output) < max_terms:
        for group in _fallback_concept_groups(intent):
            for term in group:
                if term.casefold() not in seen:
                    output.append(term)
                    seen.add(term.casefold())
    return " ".join(output[:max_terms])


def _anchor_groups(intent: RetrievalIntent) -> list[list[str]]:
    """Return explicit disease/product anchors, excluding generic field prose."""
    indication = _content_terms(intent.indication, limit=4, keep_short=True)
    explicit_entities = [
        entity.name
        for entity in intent.entities
        if entity.entity_type
        in {"disease", "pathogen", "vaccine", "drug", "compound", "device"}
    ]
    entity_terms = [
        term
        for name in explicit_entities
        for term in _content_terms(name, limit=5, keep_short=True)
    ]
    occupied = {term.casefold() for term in indication}
    entity_terms = [
        term for term in dict.fromkeys(entity_terms) if term.casefold() not in occupied
    ]
    return [group for group in (indication, entity_terms) if group]


def _fallback_concept_groups(intent: RetrievalIntent) -> list[list[str]]:
    """Return generic catalog wording only as a last-resort native fallback."""
    intervention = _content_terms(intent.intervention_class, limit=3)
    topic = _content_terms(intent.topic, limit=5)
    description = _content_terms(intent.description, limit=8)
    occupied = {term.casefold() for term in intervention}
    topic_terms: list[str] = []
    for term in topic:
        folded = term.casefold()
        if folded in occupied or folded in {item.casefold() for item in topic_terms}:
            continue
        topic_terms.append(term)
    occupied.update(term.casefold() for term in topic_terms)
    description_terms: list[str] = []
    for term in description:
        folded = term.casefold()
        if folded in occupied or folded in {item.casefold() for item in description_terms}:
            continue
        description_terms.append(term)
        if len(description_terms) >= 6:
            break
    return [
        group
        for group in (intervention, topic_terms, description_terms)
        if group
    ]


def _native_query_terms(
    text: str,
    intent: RetrievalIntent,
    *,
    limit: int,
) -> list[str]:
    """Translate one AI-authored neutral query into source-native content terms."""
    anchor_terms = {
        term.casefold()
        for group in _anchor_groups(intent)
        for term in group
    }
    terms = _content_terms(text, limit=limit + len(anchor_terms), keep_short=True)
    return [term for term in terms if term.casefold() not in anchor_terms][:limit]


def _content_terms(
    text: str,
    *,
    limit: int,
    keep_short: bool = False,
) -> list[str]:
    normalized = re.sub(r"[._/]+", " ", clean_query_text(text))
    return [
        term
        for term in _unique_terms(normalized)
        if (keep_short or len(term) >= 3)
        and len(term) >= 2
        and term.casefold() not in _LOW_SIGNAL_TERMS
    ][:limit]


def _pubmed_group(terms: list[str]) -> str:
    unique = list(dict.fromkeys(terms))
    if len(unique) == 1:
        return f"({unique[0]})"
    return "(" + " OR ".join(unique) + ")"


def _pubmed_clause(terms: list[str]) -> str:
    unique = list(dict.fromkeys(terms))
    if len(unique) == 1:
        return unique[0]
    return "(" + " AND ".join(unique) + ")"


def _unique_terms(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in _TERM.findall(text):
        folded = term.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        terms.append(term)
    return terms
