"""ChEMBL compound retrieval via ToolUniverse.

Compounds only. The lane also searched ChEMBL targets, but a target record carries no
development facts - no phase, no approval - so it built no development record, and its
findings were `reference`, which nothing downstream reads for evidence: the requests ran
and reached nothing. A lane earns a request by what its output feeds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from ..models import (
    DevelopmentRecord,
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
    result_records,
    run_tool,
    structured_excerpt,
    text,
)

DRUG_TOOL = "ChEMBL_search_drugs"
MAX_RESULTS = 10
MAX_ENTITIES = 6
DRUG_TYPES = ("compound", "drug")
#: ChEMBL's `max_phase` vocabulary. 0.5 is its early phase 1; -1 means the phase is
#: unknown and null that no clinical phase is recorded. Neither of those is a phase, so
#: neither becomes one: the record states no phase rather than "Preclinical".
_PHASES = {
    0.5: "Early Phase 1",
    1.0: "Phase 1",
    2.0: "Phase 2",
    3.0: "Phase 3",
    4.0: "Phase 4",
}


class ChEMBLSource:
    spec = SourceSpec(
        key="chembl",
        label="ChEMBL",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(DRUG_TOOL,),
        evidence_domains=("biological",),
        required_entity_types=DRUG_TYPES,
        attribution=SourceAttribution(
            label="ChEMBL",
            url="https://www.ebi.ac.uk/chembl/",
            prefix="Compound data provided by",
        ),
        evidence_class="molecular",
        jurisdiction="global",
        reads=("subject",),
        feeds=("landscape",),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        intent_ids, input_queries, document_refs = request_lineage(list(intent.queries))
        entities = [
            entity
            for entity in dict.fromkeys(intent.entities)
            if entity.entity_type in DRUG_TYPES
        ]
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=f"drug:{entity.name}",
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                connector=TOOLUNIVERSE_INTEGRATION,
                operation=DRUG_TOOL,
                options=(("entity_name", entity.name),),
            )
            for entity in entities[:MAX_ENTITIES]
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        if request.operation != DRUG_TOOL:
            raise RuntimeError(f"Unsupported ChEMBL operation: {request.operation}")
        result = run_tool(
            runtime,
            self.spec,
            DRUG_TOOL,
            {"query": request.option("entity_name"), "limit": self.spec.max_results},
        )
        return _drug_findings(result_records(result, "molecules"), request)


def _drug_findings(records: list[dict], request: SearchRequest) -> list[Finding]:
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
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
                excerpt=structured_excerpt(
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
                ),
                excerpt_kind="structured_fields",
                identifiers={"chembl": chembl_id},
                record_key=f"chembl:{chembl_id}",
                source="chembl",
                evidence_role="reference",
                development_records=[
                    DevelopmentRecord(
                        program_name=text(record.get("pref_name")) or chembl_id,
                        record_type="compound_catalog",
                        record_id=chembl_id,
                        phase=_phase_label(record.get("max_phase")),
                        status=(
                            f"First approved {record.get('first_approval')}"
                            if record.get("first_approval")
                            else ""
                        ),
                    )
                ],
            )
        )
    return findings


def _phase_label(value: object) -> str:
    try:
        phase = float(str(value))
    except (TypeError, ValueError):
        return ""
    return _PHASES.get(phase, "")
