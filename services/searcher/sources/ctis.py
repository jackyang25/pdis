"""EU Clinical Trials Information System adapter via ToolUniverse."""

from __future__ import annotations

from datetime import datetime, timezone

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
    parse_datetime,
    ranked_records,
    relevant_excerpt,
    result_records,
    run_tool,
    text,
)

SEARCH_TOOL = "CTIS_search_trials_filtered"
MAX_CANDIDATES = 50
MAX_RESULTS = 10


class CTISSource:
    spec = SourceSpec(
        key="ctis",
        label="EU CTIS",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL,),
        evidence_domains=("clinical", "safety"),
        attribution=SourceAttribution(
            label="EU Clinical Trials Information System",
            url="https://euclinicaltrials.eu/",
            prefix="Trial data provided by",
        ),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        condition = intent.indication.strip() or intent.topic.strip()
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=f"medical_condition:{condition}",
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                connector=TOOLUNIVERSE_INTEGRATION,
                operation=SEARCH_TOOL,
                options=(
                    ("medical_condition", condition),
                    ("limit", str(MAX_CANDIDATES)),
                    ("ranking", "all_input_queries"),
                ),
            )
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        result = run_tool(
            runtime,
            SEARCH_TOOL,
            {
                "medical_condition": request.option("medical_condition"),
                "limit": int(request.option("limit", str(MAX_CANDIDATES))),
            },
        )
        records = ranked_records(
            result_records(result, "data"),
            request,
            limit=MAX_RESULTS,
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in records:
            ct_number = text(record.get("ct_number"))
            if not ct_number:
                continue
            url = f"https://euclinicaltrials.eu/ctis-public/view/{ct_number}"
            findings.append(
                Finding(
                    url=url,
                    title=text(record.get("title")) or ct_number,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    published_at=parse_datetime(
                        record.get("last_updated"),
                        "%d/%m/%Y",
                    ),
                    excerpt=relevant_excerpt(
                        record,
                        (
                            ("conditions", "Conditions"),
                            ("phase", "Phase"),
                            ("status", "Status code"),
                            ("sponsor", "Sponsor"),
                            ("countries", "Countries"),
                            ("age_group", "Age group"),
                            ("total_enrolled", "Enrollment"),
                            ("results_first_received", "Results posted"),
                            ("start_date_eu", "EU start date"),
                        ),
                        request,
                    ),
                    source=self.spec.key,
                    development_records=_development_records(record, ct_number),
                )
            )
        return findings


def _development_records(record: dict, record_id: str) -> list[DevelopmentRecord]:
    """Use a named investigational product only when CTIS returns one."""
    names: list[str] = []
    for key in ("product_name", "intervention_name", "investigational_product"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    return [
        DevelopmentRecord(
            program_name=name,
            record_type="clinical_trial",
            record_id=record_id,
            sponsor=text(record.get("sponsor")),
            phase=text(record.get("phase")),
            status=text(record.get("status")),
        )
        for name in dict.fromkeys(names)
    ]
