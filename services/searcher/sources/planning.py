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
    anchors: Sequence[str] = (),
    limit: int = 0,
) -> list[tuple[dict[str, str], list[SourceQueryIntent]]]:
    """Group an intent's queries by the native scope each one resolves to.

    The first group is always the intent's own scope, carrying every query. It is
    the request this source made before any facet existed, and it is the only one
    guaranteed to match the source's own vocabulary. Facet-resolved scopes are
    *added* to it rather than substituted for it, because a precise request that
    names a product the source files differently returns nothing, and losing
    coverage is worse than lacking precision.

    ``anchors`` names the fields that carry the intent's scope rather than a
    query's narrowing. An anchor always takes the intent's value: a query that
    restates the scope in its own words has narrowed nothing, so honouring the
    restatement would spend a request on a term the source's index is not
    guaranteed to hold. Narrowing fields still vary freely.

    Queries resolving to the same scope share one request and keep every
    contributing intent in its lineage, so specificity never multiplies provider
    calls. ``limit`` is the source's own request budget: when narrowed scopes
    exceed it, precision is dropped in arrival order and the scope request is
    always kept.
    """
    baseline = {field: fallbacks.get(field, "").strip() for field in fields}
    baseline_key = tuple(baseline[field] for field in fields)
    anchored = frozenset(anchors)

    grouped: dict[tuple[str, ...], list[SourceQueryIntent]] = {
        baseline_key: list(intent.queries)
    }
    scopes: dict[tuple[str, ...], dict[str, str]] = {baseline_key: baseline}
    for query in intent.queries:
        scope = {
            field: baseline[field]
            if field in anchored
            else getattr(query.facets, field, "").strip() or baseline[field]
            for field in fields
        }
        key = tuple(scope[field] for field in fields)
        if key == baseline_key:
            continue
        scopes.setdefault(key, scope)
        grouped.setdefault(key, []).append(query)

    groups = [(scopes[key], queries) for key, queries in grouped.items()]
    return groups[:limit] if limit > 0 else groups


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
