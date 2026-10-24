"""Open Targets target-disease evidence via ToolUniverse.

The adapter deliberately retrieves association evidence, not entity-search
cards. It runs only for drug biological fields with a document-stated gene or
protein target; product configs decide which intervention classes enable it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

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
from .tooluniverse_records import TOOLUNIVERSE_INTEGRATION, run_tool, text

EVIDENCE_TOOL = "OpenTargets_get_evidence_by_datasource"
MAX_TARGETS = 4
MAX_RESULTS = 25
TARGET_ENTITY_TYPES = ("gene", "protein")


class OpenTargetsSource:
    spec = SourceSpec(
        key="open_targets",
        label="Open Targets",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(EVIDENCE_TOOL,),
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
                connector=TOOLUNIVERSE_INTEGRATION,
                operation=EVIDENCE_TOOL,
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
        arguments: dict[str, object] = {
            "disease_name": request.option("disease_name"),
            "size": self.spec.max_results,
        }
        identifier = request.option("target_identifier")
        if identifier.upper().startswith("ENSG"):
            arguments["ensemblId"] = identifier
        else:
            arguments["gene_symbol"] = request.option("target_name")
        result = run_tool(runtime, self.spec, EVIDENCE_TOOL, arguments)
        disease = _disease_payload(result)
        rows = ((disease.get("evidences") or {}).get("rows") or [])
        if not isinstance(rows, list):
            raise RetrievalError(
                "Open Targets", "invalid_response", "evidence rows are not a list"
            )

        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            target = row.get("target") if isinstance(row.get("target"), dict) else {}
            target_id = text(target.get("id")) or identifier
            symbol = text(target.get("approvedSymbol")) or request.option("target_name")
            disease_id = text(disease.get("id"))
            disease_name = text(disease.get("name")) or request.option("disease_name")
            datasource = text(row.get("datasourceId")) or "Open Targets evidence"
            datatype = text(row.get("datatypeId"))
            score = row.get("score")
            reference = _row_reference(row)
            # An evidence row has no id of its own in this query. What tells two rows of
            # one datasource apart is the record each points at - a provider link or the
            # literature it cites. A row with neither cannot be cited distinctly, so it is
            # not kept; it used to be addressed by its position in the response, which
            # changed whenever the response did.
            if not (reference and target_id and disease_id):
                continue
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
                    url=_evidence_url(row, target_id, disease_id),
                    title=f"{symbol} — {disease_name} · {datasource}",
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt="\n".join(excerpt_parts),
                    excerpt_kind="structured_fields",
                    record_key=(
                        f"open_targets:{target_id}:{disease_id}:{datasource}:{reference}"
                    ),
                    source=self.spec.key,
                )
            )
        return findings


def _disease_payload(result: object) -> dict:
    if not isinstance(result, dict):
        raise RetrievalError("Open Targets", "invalid_response", "unexpected result shape")
    if result.get("status") == "error" or result.get("error"):
        raise RetrievalError(
            "Open Targets", "tool_error", str(result.get("error") or "query failed")
        )
    data = result.get("data")
    disease = data.get("disease") if isinstance(data, dict) else None
    if not isinstance(disease, dict):
        return {}
    return disease


def _row_reference(row: dict) -> str:
    """The provider link or the literature an evidence row points at, or blank."""
    link = _row_link(row)
    if link:
        return link
    literature = row.get("literature")
    if isinstance(literature, list):
        cited = [str(value).strip() for value in literature if str(value).strip()]
        if cited:
            return "literature:" + ",".join(cited)
    return ""


def _row_link(row: dict) -> str:
    urls = row.get("urls")
    if isinstance(urls, list):
        for item in urls:
            if isinstance(item, dict):
                url = text(item.get("url"))
                if url.startswith(("https://", "http://")):
                    return url
    return ""


def _evidence_url(row: dict, target_id: str, disease_id: str) -> str:
    """Where a reader checks the row: its own link, else the first paper it cites.

    Open Targets literature rows carry PubMed IDs, and Europe PMC addresses a PubMed
    record as `MED/<pmid>`. A row with neither falls back to the platform page listing
    this pair's evidence; that page is shared by every such row, which is why identity
    is the finding's `record_key`, not this URL.
    """
    link = _row_link(row)
    if link:
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
