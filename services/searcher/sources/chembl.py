"""ChEMBL compound retrieval, called directly through ChEMBL's molecule search.

Compounds only. The lane also searched ChEMBL targets, but a target record carries no
development facts - no phase, no approval - so it built no development record, and its
findings were `reference`, which nothing downstream reads for evidence: the requests ran
and reached nothing. A lane earns a request by what its output feeds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from ..calls import provider_request
from ..errors import RetrievalError
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
from .records import structured_excerpt, text

SEARCH_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json"
#: The molecule fields a finding reads, so the search returns those and nothing else.
FIELDS = (
    "molecule_chembl_id,pref_name,molecule_type,max_phase,first_approval,"
    "therapeutic_flag,black_box_warning,oral,parenteral"
)
MAX_RESULTS = 10
#: ChEMBL publishes no rate limit; five calls a second, process-wide.
MIN_REQUEST_INTERVAL_SECONDS = 0.2
#: ChEMBL's search is slow when its cache is cold: 36 s for one name live, under a second
#: once warm. The transport's default would cut the cold call off.
TIMEOUT_SECONDS = 60.0
DEADLINE_SECONDS = 150.0
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
        # ChEMBL is slow on its side (three seconds a search at the median, fifteen at
        # the tail, measured), so throughput comes from calls in flight, not pace.
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        # Off by default: it plans nothing until a caller names a product or target.
        default_enabled=False,
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
        # ChEMBL's own search, which matches a name against preferred names and
        # synonyms and ranks the matches: `pref_name__icontains` misses a brand name.
        payload = provider_request(
            runtime,
            self.spec,
            operation="molecule/search",
            url=SEARCH_URL,
            query={
                "q": request.option("entity_name"),
                "limit": self.spec.max_results,
                "only": FIELDS,
            },
            timeout=TIMEOUT_SECONDS,
            deadline_seconds=DEADLINE_SECONDS,
        )
        molecules = payload.get("molecules") if isinstance(payload, dict) else None
        if not isinstance(molecules, list):
            raise RetrievalError("ChEMBL", "invalid_response", "no molecule list")
        return _drug_findings([item for item in molecules if isinstance(item, dict)], request)


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
