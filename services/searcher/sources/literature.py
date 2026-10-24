"""Source-native compilers for scientific-literature adapters.

These compilers translate stated query facets into each provider's grammar. They
do not interpret query prose: a consumer that knows the condition, intervention,
population, and outcome states them on the intent, so no term extraction,
stopword list, or track-to-keyword table is needed or permitted here. Recovering
meaning from finished text is how an authored query loses its institution names
and phrase structure.

Facets carry roles, and a role decides how a value is used:

* The **anchor** (`condition`) scopes every request for one intent. It is one
  value, required once. The other names a document shares are not further
  anchors: requiring every pathogen, product, and institution it mentions at the
  same time describes no real record.
* One **subject** phrase is what a single query asks. Subjects from different
  queries are alternatives, so they are joined with OR.
* Remaining facets **qualify** meaning for downstream assessment. They are not
  added to the expression, because a Boolean AND makes each one a further
  coincidence a record must satisfy, and two exact phrases required together
  already describe almost nothing. Their meaning is not lost: they stay in
  request lineage, and the semantic stages read the retrieved passage itself.

The anchor is never quoted. PubMed's Automatic Term Mapping is what maps
"respiratory syncytial virus infection" to its MeSH heading, and a quoted phrase
turns it off: measured live, the quoted anchor returned 2 records where the
unquoted one returned 33 for the same subject.
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
# Europe PMC's Lucene-like syntax treats these as grammar, and a leading hyphen as NOT.
_LUCENE_RESERVED = re.compile(r'[+!(){}\[\]^"~*?:\\/]|(?:(?<=\s)|^)-')
# A value spanning these separators is a list of concepts, not one phrase.
_CONCEPT_SEPARATOR = re.compile(r"[,;/]|\band\b", re.IGNORECASE)
# Ordered by how specifically each names what a query asks about.
_SUBJECT_FACETS = ("outcome", "intervention", "population")
_ANCHOR_ENTITY_TYPES = frozenset(
    {"disease", "pathogen", "vaccine", "drug", "compound", "device"}
)


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


def subject_phrase(intent: RetrievalIntent, query: SourceQueryIntent) -> str:
    """Return the one phrase this query is asking about.

    The most specific stated facet wins. A query that stated none still carries
    its meaning in its own text, which is used whole rather than dismantled.
    """
    for name in _SUBJECT_FACETS:
        value = clean_query_text(getattr(query.facets, name, ""))
        if value:
            return value
    return clean_query_text(query.text) or clean_query_text(intent.topic)


def scope_phrases(intent: RetrievalIntent) -> list[str]:
    """Return the disease and product names every query in this intent shares."""
    anchors = [clean_query_text(intent.indication)]
    anchors.extend(
        clean_query_text(entity.name)
        for entity in intent.entities
        if entity.entity_type in _ANCHOR_ENTITY_TYPES
    )
    return list(dict.fromkeys(anchor for anchor in anchors if anchor))


def anchor_phrase(intent: RetrievalIntent) -> str:
    """Return the one phrase that scopes every request for this intent.

    A document names its pathogens, comparators, and institutions, so the shared
    names are a list of what it mentions rather than a set of things one record
    must be about at once. The stated indication is preferred because it is the
    scope the document was validated against; the remaining names stay available
    to grammars that can use an extra phrase without requiring it.
    """
    return next(iter(scope_phrases(intent)), clean_query_text(intent.topic))


def context_phrases(intent: RetrievalIntent) -> list[str]:
    """Return the shared names that are not the anchor."""
    anchor = anchor_phrase(intent)
    return [phrase for phrase in scope_phrases(intent) if phrase != anchor]


def subject_phrases(
    intent: RetrievalIntent,
    queries: list[SourceQueryIntent],
) -> list[str]:
    """Return each query's subject once, excluding anchors already applied.

    The anchor itself is excluded too. A free-text intent states no condition, so its
    anchor falls back to its own topic - which is also its one query's text - and the
    request asked for the same sentence twice, once as scope and once as subject.
    """
    anchors = {phrase.casefold() for phrase in scope_phrases(intent)}
    anchors.add(anchor_phrase(intent).casefold())
    subjects: list[str] = []
    for query in queries:
        phrase = subject_phrase(intent, query)
        if not phrase or phrase.casefold() in anchors:
            continue
        if phrase not in subjects:
            subjects.append(phrase)
    return subjects


def build_pubmed_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
) -> str:
    """Compile the track's intents into one reachable PubMed expression.

    The shape is ``anchor AND (subject OR subject ...)``. The anchor keeps the
    request on topic exactly once; subjects are alternatives, so adding a query
    widens coverage instead of further constraining every record. Subjects are
    quoted so their words stay together; PubMed searches an unindexed quoted phrase
    as its words and says so, which the adapter records on the outcome.
    """
    del track
    return _boolean_query(
        _unquoted_term(anchor_phrase(intent), _PUBMED_RESERVED),
        [_pubmed_term(phrase) for phrase in subject_phrases(intent, queries)],
    )


def build_europepmc_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
) -> str:
    """Compile the track's intents into one Europe PMC Boolean expression.

    The same ``anchor AND (subject OR subject ...)`` shape as PubMed, because Europe
    PMC's syntax ANDs every bare word: the plain-text compiler it used before required
    each query's subject and every qualifier at once, so a second query narrowed the
    request instead of widening it. Subjects are grouped words rather than quoted
    phrases, because Europe PMC searches a quoted phrase exactly and, unlike PubMed,
    has no fallback when the phrase is absent (a stated outcome quoted returned 0
    records live; the same words grouped returned hundreds).
    """
    del track
    return _boolean_query(
        _unquoted_term(anchor_phrase(intent), _LUCENE_RESERVED),
        [
            _unquoted_term(phrase, _LUCENE_RESERVED)
            for phrase in subject_phrases(intent, queries)
        ],
    )


def _boolean_query(anchor: str, subjects: list[str]) -> str:
    subjects = [subject for subject in dict.fromkeys(subjects) if subject]
    parts = [anchor] if anchor else []
    if subjects:
        parts.append(
            "(" + " OR ".join(subjects) + ")" if len(subjects) > 1 else subjects[0]
        )
    return " AND ".join(parts)


def _unquoted_term(phrase: str, reserved: re.Pattern[str]) -> str:
    """Render a phrase as grouped words: each word required, none of them quoted."""
    cleaned = " ".join(reserved.sub(" ", phrase).split())
    if not cleaned:
        return ""
    return f"({cleaned})" if " " in cleaned else cleaned


def build_semantic_scholar_query(
    intent: RetrievalIntent,
    track: str,
    queries: list[SourceQueryIntent],
    *,
    max_queries: int = 2,
    max_phrases: int = 8,
) -> str:
    """Compile a focused plain-text query that keeps stated phrases intact.

    Semantic Scholar has no Boolean grammar, so an added phrase is a relevance
    hint rather than a requirement. Qualifier facets are therefore included here
    and excluded from PubMed: the same phrase that would gate a Boolean request
    only sharpens a plain-text one. Phrases are carried whole rather than split
    into interleaved terms, and the request is bounded because a plain-text engine
    degrades as concepts accumulate. Every contributing intent stays inspectable
    in request lineage regardless of what this text includes.
    """
    del track
    phrases = [anchor_phrase(intent), *context_phrases(intent)]
    for query in queries[:max_queries]:
        stated = [clean_query_text(phrase) for phrase in query.facets.phrases()]
        for phrase in stated or [subject_phrase(intent, query)]:
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return " ".join(phrases[:max_phrases])


def _pubmed_term(phrase: str) -> str:
    """Render one phrase in PubMed grammar.

    A single phrase is quoted so its words stay together. A value spanning
    several concepts is left unquoted: quoting it would search for the separators
    themselves and match nothing, and splitting it would mean this module
    deciding what the parts mean.
    """
    cleaned = " ".join(_PUBMED_RESERVED.sub(" ", phrase).split())
    if not cleaned:
        return ""
    if " " not in cleaned or _CONCEPT_SEPARATOR.search(cleaned):
        return cleaned
    return f'"{cleaned}"'
