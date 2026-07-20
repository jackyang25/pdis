"""ChEMBL compound and target retrieval via ToolUniverse."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

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
from .tooluniverse_records import (
    TOOLUNIVERSE_INTEGRATION,
    relevant_excerpt,
    result_records,
    run_tool,
    text,
)

DRUG_TOOL = "ChEMBL_search_drugs"
TARGET_TOOL = "ChEMBL_search_targets"
MAX_RESULTS = 10
DRUG_TYPES = {"drug", "compound"}
TARGET_TYPES = {"protein", "gene", "antigen", "biomarker"}


class ChEMBLSource:
    spec = SourceSpec(
        key="chembl",
        label="ChEMBL",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(DRUG_TOOL, TARGET_TOOL),
        evidence_domains=("biological",),
        required_entity_types=tuple(sorted(DRUG_TYPES | TARGET_TYPES)),
        attribution=SourceAttribution(
            label="ChEMBL",
            url="https://www.ebi.ac.uk/chembl/",
            prefix="Compound and target data provided by",
        ),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        requests: list[SearchRequest] = []
        entities = list(dict.fromkeys(intent.entities))
        for entity in entities[:6]:
            if entity.entity_type in DRUG_TYPES:
                operation = DRUG_TOOL
                native_query = f"drug:{entity.name}"
            elif entity.entity_type in TARGET_TYPES:
                operation = TARGET_TOOL
                native_query = f"target:{entity.name}"
            else:
                continue
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=native_query,
                    tracks=tuple(active_tracks(intent)),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TOOLUNIVERSE_INTEGRATION,
                    operation=operation,
                    options=(("entity_name", entity.name), ("limit", str(MAX_RESULTS))),
                )
            )
        return requests

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        if request.operation == DRUG_TOOL:
            return _search_drugs(request, runtime)
        if request.operation == TARGET_TOOL:
            return _search_targets(request, runtime)
        raise RuntimeError(f"Unsupported ChEMBL operation: {request.operation}")


def _search_drugs(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    result = run_tool(
        runtime,
        DRUG_TOOL,
        {"query": request.option("entity_name"), "limit": MAX_RESULTS},
    )
    return _drug_findings(result_records(result, "molecules"), request)


def _drug_findings(records: list[dict], request: SearchRequest) -> list[Finding]:
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records[:MAX_RESULTS]:
        chembl_id = text(record.get("molecule_chembl_id"))
        if not chembl_id:
            continue
        findings.append(
            Finding(
                url=(
                    "https://www.ebi.ac.uk/chembl/explore/compound/"
                    + quote(chembl_id)
                ),
                title=text(record.get("pref_name")) or chembl_id,
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=relevant_excerpt(
                    record,
                    (
                        ("molecule_type", "Molecule type"),
                        ("max_phase", "Maximum phase"),
                        ("first_approval", "First approval"),
                        ("therapeutic_flag", "Therapeutic"),
                        ("black_box_warning", "Black-box warning"),
                        ("oral", "Oral"),
                        ("parenteral", "Parenteral"),
                    ),
                    request,
                ),
                source="chembl",
            )
        )
    return findings


def _search_targets(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    result = run_tool(
        runtime,
        TARGET_TOOL,
        {
            "pref_name__contains": request.option("entity_name"),
            "limit": MAX_RESULTS,
            "fields": ["target_chembl_id", "pref_name", "organism", "target_type"],
        },
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in result_records(result, "targets")[:MAX_RESULTS]:
        chembl_id = text(record.get("target_chembl_id"))
        if not chembl_id:
            continue
        findings.append(
            Finding(
                url="https://www.ebi.ac.uk/chembl/explore/target/" + quote(chembl_id),
                title=text(record.get("pref_name")) or chembl_id,
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=relevant_excerpt(
                    record,
                    (("organism", "Organism"), ("target_type", "Target type")),
                    request,
                ),
                source="chembl",
            )
        )
    return findings
