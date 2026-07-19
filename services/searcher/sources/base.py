"""Retrieval-source adapter contract."""

from __future__ import annotations

from typing import Protocol

from ..models import Finding, RetrievalIntent, SearchRequest, SearchRuntime, SourceSpec


class SourceAdapter(Protocol):
    """A source plans native requests and normalizes responses to Findings."""

    spec: SourceSpec

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]: ...

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]: ...
