"""Open Targets target-disease evidence, called directly through its GraphQL API.

The adapter deliberately retrieves association evidence, not entity-search
cards. It runs only for drug biological fields with a document-stated gene or
protein target; product configs decide which intervention classes enable it.

Open Targets addresses a disease and a target by ID, so a request is three calls: the
disease's ID from Open Targets' own search, the target's (unless the document stated an
Ensembl ID), then the evidence for the pair. The disease lookup is the same for every
target in a run and is made once.

The two lookups are not trusted alike. The disease is the run's configured indication, a
reviewed term, so the search's first hit is the platform's reading of it. A target is a name
the document stated, and Open Targets indexes human genes: a pathogen protein or a product
name would resolve to whichever human gene the search ranked first, and that gene's evidence
would be presented as the document's target's. So a target is accepted only as a hit whose
approved symbol is the stated name - a symbol is an HGNC identifier, compared as one - and a
name that is no symbol gets no evidence rather than someone else's.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..calls import provider_request
from ..errors import RetrievalError
from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks
from .planning import request_lineage
from .records import text

GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"
MAX_TARGETS = 4
MAX_RESULTS = 25
TARGET_ENTITY_TYPES = ("gene", "protein")
#: Open Targets publishes no rate limit; ten calls a second, process-wide.
MIN_REQUEST_INTERVAL_SECONDS = 0.1
SEARCH_QUERY = """
query Search($text: String!, $entity: String!) {
  search(queryString: $text, entityNames: [$entity], page: {index: 0, size: 5}) {
    hits { id name }
  }
}
"""
EVIDENCE_QUERY = """
query Evidence($disease: String!, $target: String!, $size: Int!) {
  disease(efoId: $disease) {
    id
    name
    evidences(ensemblIds: [$target], size: $size) {
      rows {
        id
        datasourceId
        datatypeId
        score
        literature
        urls { url }
        target { id approvedSymbol }
      }
    }
  }
}
"""


class OpenTargetsSource:
    spec = SourceSpec(
        key="open_targets",
        label="Open Targets",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        # Off by default: it plans nothing until a caller names a product or target.
        default_enabled=False,
        evidence_domains=("biological",),
        required_entity_types=TARGET_ENTITY_TYPES,
        attribution=SourceAttribution(
            label="Open Targets Platform",
            url="https://platform.opentargets.org/",
            prefix="Target-disease evidence provided by",
        ),
        evidence_class="molecular",
        jurisdiction="global",
        reads=("subject", "condition"),
        feeds=("insights",),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        targets = list(
            dict.fromkeys(
                entity
                for entity in intent.entities
                if entity.entity_type in TARGET_ENTITY_TYPES
            )
        )[:MAX_TARGETS]
        disease = intent.indication.strip()
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=f"target_disease:{target.name}|{disease}",
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                options=(
                    ("target_name", target.name),
                    ("target_identifier", target.identifier),
                    ("disease_name", disease),
                ),
            )
            for target in targets
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        disease_hits = self._search(runtime, request.option("disease_name"), "disease")
        disease_id = text(disease_hits[0].get("id")) if disease_hits else ""
        identifier = request.option("target_identifier")
        name = request.option("target_name")
        target_id = identifier if identifier.upper().startswith("ENSG") else next(
            (
                text(hit.get("id"))
                for hit in self._search(runtime, name, "target")
                if text(hit.get("name")).casefold() == name.strip().casefold()
            ),
            "",
        )
        # A name Open Targets does not know is an empty answer, not a failure: the
        # platform holds no evidence for it.
        if not (disease_id and target_id):
            return []
        data = self._query(
            runtime,
            "evidence",
            EVIDENCE_QUERY,
            {"disease": disease_id, "target": target_id, "size": self.spec.max_results},
        )
        disease = data.get("disease") if isinstance(data.get("disease"), dict) else {}
        rows = (disease.get("evidences") or {}).get("rows") or []
        if not isinstance(rows, list):
            raise RetrievalError(
                "Open Targets", "invalid_response", "evidence rows are not a list"
            )
        retrieved_at = datetime.now(timezone.utc)
        disease_name = text(disease.get("name")) or request.option("disease_name")
        findings: list[Finding] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_id = text(row.get("id"))
            if not row_id:
                continue
            target = row.get("target") if isinstance(row.get("target"), dict) else {}
            symbol = text(target.get("approvedSymbol")) or request.option("target_name")
            datasource = text(row.get("datasourceId")) or "Open Targets evidence"
            datatype = text(row.get("datatypeId"))
            score = row.get("score")
            excerpt_parts = [
                f"Target: {symbol}",
                f"Disease: {disease_name}",
                f"Evidence source: {datasource}",
            ]
            if datatype:
                excerpt_parts.append(f"Evidence type: {datatype}")
            if isinstance(score, (int, float)):
                excerpt_parts.append(f"Open Targets evidence score: {score:.3f}")
            literature = row.get("literature")
            if isinstance(literature, list) and literature:
                excerpt_parts.append(
                    "Literature identifiers: "
                    + ", ".join(str(value) for value in literature[:8])
                )
            findings.append(
                Finding(
                    url=_evidence_url(row, text(target.get("id")) or target_id, disease_id),
                    title=f"{symbol} — {disease_name} · {datasource}",
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt="\n".join(excerpt_parts),
                    excerpt_kind="structured_fields",
                    # The evidence row's own ID, which Open Targets assigns per row.
                    record_key=f"open_targets:{row_id}",
                    source=self.spec.key,
                )
            )
        return findings

    def _search(self, runtime: SearchRuntime, name: str, entity: str) -> list[dict[str, Any]]:
        """Open Targets' own search hits for a name, in its ranking."""
        if not name.strip():
            return []
        data = self._query(runtime, f"search/{entity}", SEARCH_QUERY, {"text": name, "entity": entity})
        hits = (data.get("search") or {}).get("hits") or []
        return [hit for hit in hits if isinstance(hit, dict)]

    def _query(
        self,
        runtime: SearchRuntime,
        operation: str,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        payload = provider_request(
            runtime,
            self.spec,
            operation=operation,
            url=GRAPHQL_URL,
            body={"query": query, "variables": variables},
        )
        if not isinstance(payload, dict):
            raise RetrievalError("Open Targets", "invalid_response", "unexpected result shape")
        # GraphQL answers a query it refuses with 200 and an `errors` list.
        if errors := payload.get("errors"):
            messages = "; ".join(
                text(error.get("message")) for error in errors if isinstance(error, dict)
            )
            raise RetrievalError("Open Targets", "rejected", messages or "query refused")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RetrievalError("Open Targets", "invalid_response", "no data")
        return data


def _evidence_url(row: dict, target_id: str, disease_id: str) -> str:
    """Where a reader checks the row: its own link, else the first paper it cites.

    Open Targets literature rows carry PubMed IDs, and Europe PMC addresses a PubMed
    record as `MED/<pmid>`. A row with neither falls back to the platform page listing
    this pair's evidence; that page is shared by every such row, which is why identity
    is the finding's `record_key`, not this URL.
    """
    urls = row.get("urls")
    for item in urls if isinstance(urls, list) else []:
        link = text(item.get("url")) if isinstance(item, dict) else ""
        if link.startswith(("https://", "http://")):
            return link
    literature = row.get("literature")
    if isinstance(literature, list):
        for value in literature:
            pmid = str(value).strip()
            if pmid.isdigit():
                return f"https://europepmc.org/article/MED/{pmid}"
    return (
        "https://platform.opentargets.org/evidence/"
        f"{quote(target_id)}/{quote(disease_id)}"
    )
