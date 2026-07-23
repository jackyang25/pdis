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
    "recent",
    "research",
    "study",
    "target",
    "the",
    "to",
    "variable",
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
    """Compile a concise PubMed expression from stable intent semantics.

    Neutral query variants deliberately include web operators, institutions,
    and several languages. Treating each full sentence as an AND-heavy PubMed
    clause makes a single foreign-language or regulator-oriented variant erase
    an otherwise valid literature search. PubMed therefore uses the canonical
    indication, intervention, field topic, and definition. Every neutral input
    remains recorded on ``SearchRequest.input_queries`` for lineage, while the
    provider receives a bounded expression in its own useful grammar.
    """
    del queries  # Coverage is retained by request lineage, not query concatenation.
    groups = _stable_concept_groups(intent)
    track_terms = () if track == "general" else _TRACK_TERMS.get(track, ())
    if track_terms:
        groups.append(list(track_terms))
    return " AND ".join(_pubmed_group(group) for group in groups if group)


def build_semantic_scholar_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
    *,
    max_terms: int = 24,
) -> str:
    """Compile one focused plain-text paper query from canonical semantics.

    The relevance endpoint has no Boolean grammar. Mixing multilingual web
    phrasings and authority names into one bag of words materially lowers
    recall, so the native request uses the stable field contract instead. The
    full neutral bundle remains attached to the request as auditable lineage.
    """
    del queries
    output = [term for group in _stable_concept_groups(intent) for term in group]
    output = list(dict.fromkeys(output))
    seen = {term.casefold() for term in output}
    track_terms = () if track == "general" else _TRACK_TERMS.get(track, ("evidence",))
    for term in track_terms:
        if term.casefold() not in seen:
            output.append(term)
            seen.add(term.casefold())

    return " ".join(output[:max_terms])


def _stable_concept_groups(intent: RetrievalIntent) -> list[list[str]]:
    """Return provider-neutral concept groups from the canonical field shape."""
    indication = _content_terms(intent.indication, limit=4)
    intervention = _content_terms(intent.intervention_class, limit=3)
    topic = _content_terms(intent.topic, limit=5)
    description = _content_terms(intent.description, limit=8)

    occupied = {term.casefold() for term in indication + intervention}
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
        for group in (indication, intervention, topic_terms, description_terms)
        if group
    ]


def _content_terms(text: str, *, limit: int) -> list[str]:
    normalized = re.sub(r"[._/]+", " ", clean_query_text(text))
    return [
        term
        for term in _unique_terms(normalized)
        if len(term) >= 3 and term.casefold() not in _LOW_SIGNAL_TERMS
    ][:limit]


def _pubmed_group(terms: list[str]) -> str:
    unique = list(dict.fromkeys(terms))
    if len(unique) == 1:
        return f"({unique[0]})"
    return "(" + " OR ".join(unique) + ")"


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
