"""Which of the run's requests reached each finding.

Insights carry the coverage tracks and numeric targets of the requests that found
their sources. That lineage was rebuilt by matching query strings: a finding's
`queries` against every request's `query`, so two lanes sending the same text shared
one entry, and a request reached through a different spelling had none. A finding
already says how it was reached - Searcher stamps a `RetrievalPath` naming the lane,
the native query, the connector and the operation of every request that returned it -
and a request is identified by exactly those within one scope. So the lineage is read
from the path to the request, whose tracks, targets and intent IDs Scout planned.
"""

from __future__ import annotations

from typing import Iterable

from services.searcher import Finding, SearchRequest

_ExactKey = tuple[str, str, str, str, str]
_LaneKey = tuple[str, str, str]


class RetrievalLineage:
    """The planned requests of one run, addressable by a finding's retrieval paths."""

    def __init__(self, requests: Iterable[SearchRequest]) -> None:
        self._exact: dict[_ExactKey, list[SearchRequest]] = {}
        self._by_lane: dict[_LaneKey, list[SearchRequest]] = {}
        for request in requests:
            exact = (request.scope_ref, request.source, request.query,
                     request.connector, request.operation)
            self._exact.setdefault(exact, []).append(request)
            self._by_lane.setdefault(exact[:3], []).append(request)

    def requests_for(self, scope_ref: str, finding: Finding) -> list[SearchRequest]:
        """Every request of ``scope_ref`` that returned ``finding``, in path order.

        A path records the connector and operation when the request named them; one
        recorded before Searcher knew them (lane and query only) matches the lane's
        requests with that query.
        """
        found: dict[int, SearchRequest] = {}
        for path in finding.retrieval_paths:
            key = (scope_ref, path.lane, path.query, path.connector, path.operation)
            matches = self._exact.get(key) or (
                [] if path.connector or path.operation
                else self._by_lane.get(key[:3], [])
            )
            for request in matches:
                found.setdefault(id(request), request)
        return list(found.values())

    def tracks(self, scope_ref: str, findings: Iterable[Finding]) -> list[str]:
        return list(dict.fromkeys(
            track
            for finding in findings
            for request in self.requests_for(scope_ref, finding)
            for track in request.tracks
        ))

    def target_ids(self, scope_ref: str, findings: Iterable[Finding]) -> list[str]:
        return list(dict.fromkeys(
            target_id
            for finding in findings
            for request in self.requests_for(scope_ref, finding)
            for target_id in request.target_refs
        ))
