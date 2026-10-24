"""FDA regulatory-evidence adapter via allowlisted ToolUniverse operations."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote, urlencode

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
    result_records,
    run_tool,
    structured_excerpt,
    text,
)

DRUG_LABEL_TOOL = "FDA_search_drug_labels"
DEVICE_510K_TOOL = "OpenFDA_search_device_510k"
MAX_RESULTS = 10
MIN_REQUEST_INTERVAL_SECONDS = 0.3
#: openFDA counts every call from one client together, whichever lane makes it.
OPENFDA_RATE_GROUP = "openfda"


class FDASource:
    spec = SourceSpec(
        key="fda",
        label="FDA Regulatory",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        rate_group=OPENFDA_RATE_GROUP,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(DRUG_LABEL_TOOL, DEVICE_510K_TOOL),
        evidence_domains=("clinical", "safety", "regulatory", "product"),
        attribution=SourceAttribution(
            label="U.S. Food and Drug Administration",
            url="https://open.fda.gov/",
            prefix="Regulatory data provided by",
        ),
        evidence_class="regulatory",
        jurisdiction="us",
        reads=("text", "condition", "intervention"),
        feeds=("insights", "landscape"),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        # The product class selects the openFDA endpoint and the condition is the
        # intent's anchor, so no query can vary the request: one per intent, carrying
        # every query in its lineage.
        intervention = intent.intervention_class.strip().casefold()
        intent_ids, input_queries, document_refs = request_lineage(list(intent.queries))
        condition = (intent.indication or intent.topic).strip()
        if intervention in {"device", "diagnostic"}:
            operation = DEVICE_510K_TOOL
            phrase = _lucene_phrase(condition)
            # A 510(k) record names its device twice: `device_name` is the trade name,
            # `openfda.device_name` the product-code classification ("Antigen, RSV").
            # A condition is usually in the second. Asking both (openFDA reads a space
            # as OR) found 57 RSV clearances live where the trade name alone found 16,
            # and the one HIV clearance the trade name missed entirely.
            native_query = f'device_name:"{phrase}" openfda.device_name:"{phrase}"'
            options: tuple[tuple[str, str], ...] = (("search", native_query),)
        else:
            operation = DRUG_LABEL_TOOL
            native_query = f"indication:{condition}"
            options = (("indication", condition),)
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
                operation=operation,
                options=options,
            )
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        if request.operation == DRUG_LABEL_TOOL:
            return _search_labels(request, runtime)
        if request.operation == DEVICE_510K_TOOL:
            return _search_devices(request, runtime)
        raise RuntimeError(f"Unsupported FDA operation: {request.operation}")


def _search_labels(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    result = run_tool(
        runtime,
        FDASource.spec,
        DRUG_LABEL_TOOL,
        {
            "indication": request.option("indication"),
            "limit": FDASource.spec.max_results,
        },
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in result_records(result, "data"):
        # The tool's `spl_id` is openFDA's `id`: one version of a label, not the set id
        # that names the label across versions. It was being sent to DailyMed as a set
        # id, which DailyMed answers with an empty page (checked live), and a label with
        # no id fell back to the API's documentation page - one URL for every such label.
        spl_id = text(record.get("spl_id"))
        if not spl_id:
            continue
        brand = text(record.get("brand_name"))
        generic = text(record.get("generic_name"))
        title = brand or generic or "FDA drug label"
        if generic and generic.casefold() != title.casefold():
            title += f" ({generic})"
        url = "https://api.fda.gov/drug/label.json?" + urlencode(
            {"search": f'id:"{spl_id}"'}
        )
        findings.append(
            Finding(
                url=url,
                title=title,
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt_kind="structured_fields",
                identifiers={"spl_id": spl_id},
                record_key=f"fda:label:{spl_id}",
                excerpt=structured_excerpt(
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
        FDASource.spec,
        DEVICE_510K_TOOL,
        {
            "search": request.option("search"),
            "limit": FDASource.spec.max_results,
        },
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in result_records(result, "results"):
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
                excerpt_kind="structured_fields",
                identifiers={"k_number": k_number},
                record_key=f"fda:510k:{k_number}",
                excerpt=structured_excerpt(
                    record,
                    (
                        ("decision_description", "Decision"),
                        ("applicant", "Applicant"),
                        ("advisory_committee_description", "Review panel"),
                        ("product_code", "Product code"),
                        ("statement_or_summary", "Statement or summary"),
                        ("decision_date", "Decision date"),
                    ),
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
