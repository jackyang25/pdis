"""FDA regulatory-evidence adapter via allowlisted ToolUniverse operations."""

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
from .planning import facet_groups, request_lineage
from .tooluniverse_records import (
    TOOLUNIVERSE_INTEGRATION,
    parse_datetime,
    ranked_records,
    relevant_excerpt,
    result_records,
    run_tool,
    text,
)

DRUG_LABEL_TOOL = "FDA_search_drug_labels"
DEVICE_510K_TOOL = "OpenFDA_search_device_510k"
MAX_CANDIDATES = 20
MAX_RESULTS = 10
MIN_REQUEST_INTERVAL_SECONDS = 0.3
# openFDA is the tightest connector lane in the suite, so one intent stays
# close to the single request it made before facet narrowing existed.
MAX_REQUESTS_PER_INTENT = 2


class FDASource:
    spec = SourceSpec(
        key="fda",
        label="FDA Regulatory",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        max_requests_per_intent=MAX_REQUESTS_PER_INTENT,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(DRUG_LABEL_TOOL, DEVICE_510K_TOOL),
        evidence_domains=("clinical", "safety", "regulatory", "product"),
        attribution=SourceAttribution(
            label="U.S. Food and Drug Administration",
            url="https://open.fda.gov/",
            prefix="Regulatory data provided by",
        ),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        # The product class selects the openFDA endpoint, so it stays the intent's
        # rather than a per-query facet. Only the searched condition varies.
        intervention = intent.intervention_class.strip().casefold()
        requests: list[SearchRequest] = []
        for scope, queries in facet_groups(
            intent,
            fields=("condition",),
            fallbacks={"condition": intent.indication or intent.topic},
            anchors=("condition",),
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            condition = scope["condition"]
            if intervention in {"device", "diagnostic"}:
                operation = DEVICE_510K_TOOL
                native_query = f'device_name:"{_lucene_phrase(condition)}"'
                options = (
                    ("search", native_query),
                    ("limit", str(MAX_CANDIDATES)),
                    ("ranking", "all_input_queries"),
                )
            else:
                operation = DRUG_LABEL_TOOL
                native_query = f"indication:{condition}"
                options = (
                    ("indication", condition),
                    ("limit", str(MAX_CANDIDATES)),
                    ("ranking", "all_input_queries"),
                )
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
                    options=options,
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
        if request.operation == DRUG_LABEL_TOOL:
            return _search_labels(request, runtime)
        if request.operation == DEVICE_510K_TOOL:
            return _search_devices(request, runtime)
        raise RuntimeError(f"Unsupported FDA operation: {request.operation}")


def _search_labels(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    result = run_tool(
        runtime,
        DRUG_LABEL_TOOL,
        {
            "indication": request.option("indication"),
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
        spl_id = text(record.get("spl_id"))
        brand = text(record.get("brand_name"))
        generic = text(record.get("generic_name"))
        title = brand or generic or "FDA drug label"
        if generic and generic.casefold() != title.casefold():
            title += f" ({generic})"
        url = (
            "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
            + quote(spl_id)
            if spl_id
            else "https://open.fda.gov/apis/drug/label/"
        )
        findings.append(
            Finding(
                url=url,
                title=title,
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=relevant_excerpt(
                    record,
                    (
                        ("indications_and_usage", "Indications and usage"),
                        ("clinical_studies", "Clinical studies"),
                        ("dosage_and_administration", "Dosage"),
                        ("boxed_warning", "Boxed warning"),
                        ("warnings_and_precautions", "Warnings and precautions"),
                        ("contraindications", "Contraindications"),
                        ("drug_interactions", "Drug interactions"),
                        ("manufacturer", "Manufacturer"),
                        ("route", "Route"),
                        ("pharm_class", "Pharmacologic class"),
                    ),
                    request,
                ),
                source="fda",
                development_records=[
                    DevelopmentRecord(
                        program_name=brand or generic or title,
                        record_type="regulatory_label",
                        record_id=spl_id,
                        sponsor=text(record.get("manufacturer")),
                        status="FDA labeled",
                    )
                ],
            )
        )
    return findings


def _search_devices(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    result = run_tool(
        runtime,
        DEVICE_510K_TOOL,
        {
            "search": request.option("search"),
            "limit": int(request.option("limit", str(MAX_CANDIDATES))),
        },
    )
    records = ranked_records(
        result_records(result, "results"),
        request,
        limit=MAX_RESULTS,
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        k_number = text(record.get("k_number"))
        if not k_number:
            continue
        findings.append(
            Finding(
                url=(
                    "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/"
                    f"cfpmn/pmn.cfm?ID={quote(k_number)}"
                ),
                title=text(record.get("device_name")) or k_number,
                query=request.query,
                retrieved_at=retrieved_at,
                published_at=parse_datetime(
                    record.get("decision_date"),
                    "%Y%m%d",
                    "%Y-%m-%d",
                ),
                excerpt=relevant_excerpt(
                    record,
                    (
                        ("decision_description", "Decision"),
                        ("applicant", "Applicant"),
                        ("advisory_committee_description", "Review panel"),
                        ("product_code", "Product code"),
                        ("statement_or_summary", "Statement or summary"),
                        ("decision_date", "Decision date"),
                    ),
                    request,
                ),
                source="fda",
                development_records=[
                    DevelopmentRecord(
                        program_name=text(record.get("device_name")) or k_number,
                        record_type="regulatory_clearance",
                        record_id=k_number,
                        sponsor=text(record.get("applicant")),
                        status=text(record.get("decision_description")),
                    )
                ],
            )
        )
    return findings


def _lucene_phrase(value: str) -> str:
    return value.replace("\\", " ").replace('"', " ").strip()
