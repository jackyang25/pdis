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
    "current",
    "evidence",
    "for",
    "in",
    "latest",
    "of",
    "on",
    "recent",
    "research",
    "study",
    "the",
    "to",
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
    """Compile every track intent into one PubMed Boolean expression.

    PubMed supports Boolean expressions, so disjunction is the native way to
    preserve diverse generated phrasings without multiplying API searches.
    """
    clauses = list(
        dict.fromkeys(
            cleaned
            for query in queries
            if (cleaned := clean_query_text(query.text))
        )
    )
    base = clean_query_text(
        " ".join((intent.indication, intent.intervention_class, intent.topic))
    )
    if not clauses:
        return " ".join((base, *_TRACK_TERMS.get(track, ("evidence",)))).strip()
    alternatives = " OR ".join(f"({clause})" for clause in clauses)
    return f"({base}) AND ({alternatives})" if base else alternatives


def build_semantic_scholar_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
    *,
    max_terms: int = 24,
) -> str:
    """Compile all intent variants into one focused plain-text paper query.

    Semantic Scholar relevance search accepts plain text and no special query
    syntax. A giant concatenation is noisy, while taking the first variants is
    lossy. This compiler retains the stable field context, then samples unique
    semantic terms round-robin from every input so no later intent is starved.
    """
    base_text = clean_query_text(
        " ".join((intent.indication, intent.intervention_class, intent.topic))
    )
    output = _unique_terms(base_text)
    seen = {term.casefold() for term in output}
    for term in _TRACK_TERMS.get(track, ("evidence",)):
        if term.casefold() not in seen:
            output.append(term)
            seen.add(term.casefold())

    streams = [
        [
            term
            for term in _unique_terms(clean_query_text(query.text))
            if term.casefold() not in seen
            and term.casefold() not in _LOW_SIGNAL_TERMS
        ]
        for query in queries
    ]
    cursor = 0
    while len(output) < max_terms and any(streams):
        stream = streams[cursor % len(streams)]
        cursor += 1
        if not stream:
            continue
        term = stream.pop(0)
        folded = term.casefold()
        if folded in seen:
            continue
        output.append(term)
        seen.add(folded)
    return " ".join(output)


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
