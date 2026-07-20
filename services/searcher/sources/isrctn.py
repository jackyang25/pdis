"""ISRCTN international clinical-trial registry adapter via ToolUniverse."""

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
    ranked_records,
    relevant_excerpt,
    result_records,
    run_tool,
    text,
)

SEARCH_TOOL = "ISRCTN_search_trials_fielded"
MAX_CANDIDATES = 50
MAX_RESULTS = 10


class ISRCTNSource:
    spec = SourceSpec(
        key="isrctn",
        label="ISRCTN",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL,),
        evidence_domains=("clinical", "safety"),
        attribution=SourceAttribution(
            label="ISRCTN registry",
            url="https://www.isrctn.com/",
            prefix="Trial data provided by",
        ),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        condition = intent.indication.strip() or intent.topic.strip()
        intervention = intent.intervention_class.strip()
        native_query = f"condition:{condition}"
        if intervention:
            native_query += f" AND intervention:{intervention}"
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=native_query,
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                connector=TOOLUNIVERSE_INTEGRATION,
                operation=SEARCH_TOOL,
                options=(
                    ("condition", condition),
                    ("intervention", intervention),
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
        arguments: dict[str, object] = {
            "condition": request.option("condition"),
            "limit": int(request.option("limit", str(MAX_CANDIDATES))),
        }
        if intervention := request.option("intervention"):
            arguments["intervention"] = intervention
        result = run_tool(runtime, SEARCH_TOOL, arguments)
        records = ranked_records(
            result_records(result, "data"),
            request,
            limit=MAX_RESULTS,
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in records:
            isrctn_id = text(record.get("isrctn_id"))
            if not isrctn_id:
                continue
            findings.append(
                Finding(
                    url=f"https://www.isrctn.com/{isrctn_id}",
                    title=text(record.get("title")) or isrctn_id,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=relevant_excerpt(
                        record,
                        (
                            ("scientific_title", "Scientific title"),
                            ("plain_english_summary", "Summary"),
                            ("study_hypothesis", "Hypothesis"),
                            ("conditions", "Conditions"),
                            ("interventions", "Interventions"),
                            ("primary_outcomes", "Primary outcomes"),
                            ("secondary_outcomes", "Secondary outcomes"),
                            ("phase", "Phase"),
                            ("eligibility", "Eligibility"),
                            ("recruitment_countries", "Recruitment countries"),
                            ("target_enrolment", "Target enrollment"),
                            ("sponsors", "Sponsors"),
                        ),
                        request,
                    ),
                    source=self.spec.key,
                    development_records=_development_records(record, isrctn_id),
                )
            )
        return findings


def _development_records(record: dict, record_id: str) -> list[DevelopmentRecord]:
    names: list[str] = []
    raw_names = record.get("drug_names") or []
    if isinstance(raw_names, str):
        raw_names = [raw_names]
    if isinstance(raw_names, list):
        for value in raw_names:
            if not isinstance(value, str):
                continue
            names.extend(part.strip() for part in value.split(",") if part.strip())
    sponsors = record.get("sponsors") or []
    sponsor = ""
    if isinstance(sponsors, list) and sponsors:
        first = sponsors[0]
        if isinstance(first, dict):
            sponsor = text(first.get("organisation"))
        elif isinstance(first, str):
            sponsor = first.strip()
    status = text(record.get("recruitment_status")) or text(record.get("status"))
    return [
        DevelopmentRecord(
            program_name=name,
            record_type="clinical_trial",
            record_id=record_id,
            sponsor=sponsor,
            phase=text(record.get("phase")),
            status=status,
        )
        for name in dict.fromkeys(names)
        if name.casefold() not in {"drug", "device", "vaccine", "biological"}
    ]
