"""Shared mechanics for lossless source-native request planning.

This module contains no source-selection policy. It only exposes deterministic
lineage helpers used by adapters so every neutral intent compiled into a native
request remains inspectable.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..models import RetrievalIntent, SourceQueryIntent


def facet_groups(
    intent: RetrievalIntent,
    *,
    fields: Sequence[str],
    fallbacks: Mapping[str, str],
) -> list[tuple[dict[str, str], list[SourceQueryIntent]]]:
    """Group an intent's queries by the native scope each one resolves to.

    A field-addressed source can only vary its request by the facets its API
    accepts. Queries resolving to the same scope share one request and keep every
    contributing intent in its lineage, so specificity is gained without
    multiplying provider calls. Queries that state no facets all resolve to the
    intent's own scope, which is the single request such a source made before any
    facet existed.
    """
    grouped: dict[tuple[str, ...], list[SourceQueryIntent]] = {}
    scopes: dict[tuple[str, ...], dict[str, str]] = {}
    for query in intent.queries:
        scope = {
            field: getattr(query.facets, field, "").strip()
            or fallbacks.get(field, "").strip()
            for field in fields
        }
        key = tuple(scope[field] for field in fields)
        scopes.setdefault(key, scope)
        grouped.setdefault(key, []).append(query)
    return [(scopes[key], queries) for key, queries in grouped.items()]


def request_lineage(
    queries: list[SourceQueryIntent],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return aligned intent IDs, input texts, and unioned document refs."""
    unique = list(dict.fromkeys(queries))
    return (
        tuple(query.intent_id for query in unique),
        tuple(query.text for query in unique),
        tuple(
            dict.fromkeys(
                ref
                for query in unique
                for ref in query.document_refs
            )
        ),
    )
