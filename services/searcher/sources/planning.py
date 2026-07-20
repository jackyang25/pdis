"""Shared mechanics for lossless source-native request planning.

This module contains no source-selection policy. It only exposes deterministic
lineage helpers used by adapters so every neutral intent compiled into a native
request remains inspectable.
"""

from __future__ import annotations

from ..models import SourceQueryIntent


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
