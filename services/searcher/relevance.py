"""Deterministic query-to-record relevance helpers.

Provider adapters use these helpers only after a source-native request has
returned a bounded candidate set.  They do not decide source applicability or
replace provider ranking; they preserve field specificity when one structured
request represents several source-neutral query intents.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

_TERM = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_LOW_SIGNAL = {
    "about",
    "and",
    "clinical",
    "current",
    "evidence",
    "for",
    "from",
    "latest",
    "recent",
    "research",
    "study",
    "the",
    "trial",
    "with",
}


def query_terms(queries: Iterable[str]) -> tuple[str, ...]:
    """Return stable, non-generic terms from every neutral input query."""
    terms: list[str] = []
    seen: set[str] = set()
    for query in queries:
        for term in _TERM.findall(query):
            folded = term.casefold()
            if len(folded) < 3 or folded in _LOW_SIGNAL or folded in seen:
                continue
            seen.add(folded)
            terms.append(folded)
    return tuple(terms)


def score_text(value: Any, terms: Sequence[str]) -> int:
    """Count distinct query terms represented in a structured value."""
    haystack = value_text(value).casefold()
    return sum(1 for term in terms if term in haystack)


def rank_records(
    records: Iterable[dict[str, Any]],
    queries: Iterable[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Rank a bounded structured candidate set without altering its records."""
    terms = query_terms(queries)
    indexed = list(enumerate(records))
    indexed.sort(
        key=lambda item: (
            -score_text(item[1], terms),
            item[0],
        )
    )
    return [record for _, record in indexed[:limit]]


def value_text(value: Any) -> str:
    """Flatten a JSON-like value for deterministic lexical comparison."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, Mapping):
        return "; ".join(
            f"{key}: {rendered}"
            for key, item in value.items()
            if (rendered := value_text(item))
        )
    if isinstance(value, (list, tuple)):
        return "; ".join(
            rendered for item in value if (rendered := value_text(item))
        )
    return str(value)
