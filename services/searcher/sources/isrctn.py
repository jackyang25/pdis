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
from .planning import facet_groups, planned_variants, request_lineage
from .tooluniverse_records import (
    TOOLUNIVERSE_INTEGRATION,
    result_records,
    run_tool,
    structured_excerpt,
    text,
)

SEARCH_TOOL = "ISRCTN_search_trials_fielded"
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
        evidence_class="registry",
        jurisdiction="uk",
        reads=("text", "condition", "intervention", "product", "region"),
        feeds=("insights", "landscape"),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        groups = facet_groups(
            intent,
            fields=("condition", "intervention"),
            fallbacks={
                "condition": intent.indication or intent.topic,
                "intervention": intent.intervention_class,
            },
            anchors=("condition",),
        )
        requests: list[SearchRequest] = []
        # Unscoped first, then the region-narrowed twin, never instead of it. ISRCTN
        # compiles `country` to `recruitmentCountry`, so the narrowed request asks
        # where a trial actually recruited rather than where its text mentions.
        for scope, queries, location in planned_variants(
            groups,
            region=intent.scope("region"),
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            condition = scope["condition"]
            intervention = scope["intervention"]
            native_query = f"condition:{condition}"
            if intervention:
                native_query += f" AND intervention:{intervention}"
            if location:
                native_query += f" AND recruitmentCountry:{location}"
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
                    operation=SEARCH_TOOL,
                    options=(
                        ("condition", condition),
                        ("intervention", intervention),
                        ("region", location),
                    ),
                )
            )
        return requests

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        arguments: dict[str, object] = {
            "condition": request.option("condition"),
            "limit": self.spec.max_results,
        }
        if intervention := request.option("intervention"):
            arguments["intervention"] = intervention
        if region := request.option("region"):
            arguments["country"] = region
        result = run_tool(runtime, self.spec, SEARCH_TOOL, arguments)
        records = result_records(result, "data")
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
                    excerpt=structured_excerpt(
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
                    ),
                    excerpt_kind="structured_fields",
                    # The registry's own cross-references: the same trial registered
                    # elsewhere is the same record, so it merges with that registry's copy.
                    identifiers={
                        "isrctn": isrctn_id,
                        "nct": text(record.get("clinicaltrials_gov_number")),
                        "eudract": text(record.get("eudract_number")),
                        "doi": text(record.get("doi")),
                    },
                    record_key=f"isrctn:{isrctn_id}",
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
