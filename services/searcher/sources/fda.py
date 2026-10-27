"""FDA regulatory evidence from openFDA: drug labels, and 510(k) clearances for devices."""

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
from .openfda import MIN_REQUEST_INTERVAL_SECONDS, OPENFDA, first, openfda_search, phrase, strings
from .planning import request_lineage
from .records import parse_datetime, structured_excerpt, text

DRUG_LABELS = "drug/label.json"
DEVICE_510K = "device/510k.json"
MAX_RESULTS = 10
#: The label sections an excerpt reads, in reading order. A label states its warnings
#: under `warnings_and_cautions` in the current format and `warnings` in the older one.
LABEL_SECTIONS = (
    ("indications_and_usage", "Indications and usage"),
    ("clinical_studies", "Clinical studies"),
    ("dosage_and_administration", "Dosage"),
    ("boxed_warning", "Boxed warning"),
    ("warnings_and_cautions", "Warnings and precautions"),
    ("warnings", "Warnings"),
    ("contraindications", "Contraindications"),
    ("drug_interactions", "Drug interactions"),
)


class FDASource:
    spec = SourceSpec(
        key="fda",
        label="FDA Regulatory",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        rate_group=OPENFDA,
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
        condition = phrase((intent.indication or intent.topic).strip())
        if intervention in {"device", "diagnostic"}:
            endpoint = DEVICE_510K
            # A 510(k) record names its device twice: `device_name` is the trade name,
            # `openfda.device_name` the product-code classification ("Antigen, RSV").
            # A condition is usually in the second. Asking both (openFDA reads a space
            # as OR) found 57 RSV clearances live where the trade name alone found 16,
            # and the one HIV clearance the trade name missed entirely.
            search = f"device_name:{condition} openfda.device_name:{condition}"
        else:
            endpoint = DRUG_LABELS
            # Only labels openFDA has harmonized: an unharmonized label carries no brand,
            # generic name or manufacturer, and was most of what a condition matched live
            # (8 of the first 10 for tuberculosis), each a finding with nothing to name it.
            search = f"indications_and_usage:{condition} AND _exists_:openfda.generic_name"
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=search,
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                operation=endpoint.removesuffix(".json"),
                options=(("endpoint", endpoint),),
            )
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        endpoint = request.option("endpoint")
        records = openfda_search(
            runtime, self.spec, endpoint, request.query, limit=self.spec.max_results
        )
        if endpoint == DEVICE_510K:
            return _clearances(records, request)
        return _labels(records, request)


def _labels(records: list[dict], request: SearchRequest) -> list[Finding]:
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        # `id` is one version of a label and `set_id` the label across its versions.
        # DailyMed addresses a label by its set id; the version id is what this finding
        # quotes, so it is the identity and the API query for it is the URL.
        spl_id = text(record.get("id"))
        if not spl_id:
            continue
        names = record.get("openfda") if isinstance(record.get("openfda"), dict) else {}
        brand = first(names.get("brand_name"))
        generic = first(names.get("generic_name"))
        title = brand or generic or "FDA drug label"
        if generic and generic.casefold() != title.casefold():
            title += f" ({generic})"
        sections = {
            field: " ".join(strings(record.get(field))) for field, _ in LABEL_SECTIONS
        }
        manufacturer = first(names.get("manufacturer_name"))
        findings.append(
            Finding(
                url="https://api.fda.gov/drug/label.json?"
                + urlencode({"search": f'id:"{spl_id}"'}),
                title=title,
                query=request.query,
                retrieved_at=retrieved_at,
                published_at=parse_datetime(record.get("effective_time"), "%Y%m%d"),
                excerpt_kind="structured_fields",
                identifiers={"spl_id": spl_id, "setid": text(record.get("set_id"))},
                record_key=f"fda:label:{spl_id}",
                excerpt=structured_excerpt(
                    {
                        **sections,
                        "manufacturer": manufacturer,
                        "route": strings(names.get("route")),
                        "pharm_class": strings(names.get("pharm_class_epc")),
                    },
                    (
                        *LABEL_SECTIONS,
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
                        sponsor=manufacturer,
                        status="FDA labeled",
                    )
                ],
            )
        )
    return findings


def _clearances(records: list[dict], request: SearchRequest) -> list[Finding]:
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        k_number = text(record.get("k_number"))
        if not k_number:
            continue
        device = text(record.get("device_name")) or k_number
        findings.append(
            Finding(
                url=(
                    "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/"
                    f"cfpmn/pmn.cfm?ID={quote(k_number)}"
                ),
                title=device,
                query=request.query,
                retrieved_at=retrieved_at,
                published_at=parse_datetime(record.get("decision_date"), "%Y-%m-%d", "%Y%m%d"),
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
                        program_name=device,
                        record_type="regulatory_clearance",
                        record_id=k_number,
                        sponsor=text(record.get("applicant")),
                        status=text(record.get("decision_description")),
                    )
                ],
            )
        )
    return findings
