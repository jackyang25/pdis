"""Conditional FDA safety-signal retrieval through ToolUniverse.

This lane uses only document-stated product names. It keeps official label
warnings, spontaneous-report counts, device adverse-event reports, and recalls
as distinct structured observations. None is promoted to causal proof.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from ..models import (
    Finding,
    RetrievalIntent,
    SafetyObservationRecord,
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
    text,
)

DRUG_WARNING_TOOL = "FDA_get_warnings_by_drug_name"
FAERS_REACTION_TOOL = "FAERS_count_reactions_by_drug_event"
DEVICE_EVENT_TOOL = "OpenFDA_search_device_adverse_events"
DEVICE_RECALL_TOOL = "OpenFDA_search_device_recalls"
DRUG_ENTITY_TYPES = {"drug", "compound", "vaccine"}
DEVICE_ENTITY_TYPES = {"device"}
PRODUCT_ENTITY_TYPES = tuple(sorted(DRUG_ENTITY_TYPES | DEVICE_ENTITY_TYPES))
MAX_PRODUCTS = 3
MAX_RESULTS = 10
MIN_REQUEST_INTERVAL_SECONDS = 0.3
FAERS_QUALIFICATION = (
    "FAERS contains spontaneous reports. Counts do not measure incidence and "
    "do not establish that the product caused the event."
)
MAUDE_QUALIFICATION = (
    "MAUDE reports are unverified safety reports and do not establish causation."
)


class FDASafetySource:
    spec = SourceSpec(
        key="fda_safety",
        label="FDA Safety",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(
            DRUG_WARNING_TOOL,
            FAERS_REACTION_TOOL,
            DEVICE_EVENT_TOOL,
            DEVICE_RECALL_TOOL,
        ),
        evidence_domains=("safety",),
        required_entity_types=PRODUCT_ENTITY_TYPES,
        attribution=SourceAttribution(
            label="U.S. Food and Drug Administration",
            url="https://open.fda.gov/",
            prefix="Safety data provided by",
        ),
        evidence_class="regulatory",
        jurisdiction="us",
        reads=("subject",),
        feeds=("safety",),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        products = list(
            dict.fromkeys(
                entity
                for entity in intent.entities
                if entity.entity_type in PRODUCT_ENTITY_TYPES
            )
        )[:MAX_PRODUCTS]
        requests: list[SearchRequest] = []
        for product in products:
            operations = (
                (DRUG_WARNING_TOOL, f"label_warnings:{product.name}"),
                (FAERS_REACTION_TOOL, f"reported_events:{product.name}"),
            ) if product.entity_type in DRUG_ENTITY_TYPES else (
                (DEVICE_EVENT_TOOL, f"device_events:{product.name}"),
                (DEVICE_RECALL_TOOL, f"device_recalls:{product.name}"),
            )
            for operation, native_query in operations:
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
                        options=(
                            ("product_name", product.name),
                            ("limit", str(MAX_RESULTS)),
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
        max_uses: int,
    ) -> list[Finding]:
        if request.operation == DRUG_WARNING_TOOL:
            return _drug_warnings(request, runtime)
        if request.operation == FAERS_REACTION_TOOL:
            return _faers_reactions(request, runtime)
        if request.operation == DEVICE_EVENT_TOOL:
            return _device_events(request, runtime)
        if request.operation == DEVICE_RECALL_TOOL:
            return _device_recalls(request, runtime)
        raise RuntimeError(f"Unsupported FDA safety operation: {request.operation}")


def _drug_warnings(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    product = request.option("product_name")
    result = run_tool(
        runtime,
        DRUG_WARNING_TOOL,
        {"drug_name": product, "limit": MAX_RESULTS, "skip": 0},
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for index, record in enumerate(result_records(result, "results")[:MAX_RESULTS]):
        boxed = _strings(record.get("boxed_warning"))
        warnings = _strings(record.get("warnings"))
        details = [*boxed, *warnings]
        if not details:
            continue
        brand = _first(record.get("openfda.brand_name"))
        generic = _first(record.get("openfda.generic_name"))
        product_name = brand or generic or product
        signal = "Boxed warning" if boxed else "Official label warning"
        detail = " ".join(details)
        url = (
            "https://api.fda.gov/drug/label.json?"
            + urlencode({"search": f'openfda.generic_name:"{product}"', "limit": 1})
            + f"#record-{index + 1}"
        )
        findings.append(
            Finding(
                url=url,
                title=f"{product_name} · {signal}",
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=detail[:16_000],
                source="fda_safety",
                safety_observations=[
                    SafetyObservationRecord(
                        product_name=product_name,
                        record_type="label_warning",
                        source_system="fda_label",
                        label=signal,
                        detail=detail[:2_000],
                        qualification="Official FDA labeling language.",
                    )
                ],
            )
        )
    return findings


def _faers_reactions(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    product = request.option("product_name")
    result = run_tool(
        runtime,
        FAERS_REACTION_TOOL,
        {"medicinalproduct": product},
    )
    if isinstance(result, dict) and (result.get("error") or result.get("status") == "error"):
        raise RuntimeError(str(result.get("error") or "FAERS retrieval failed"))
    records = result if isinstance(result, list) else []
    retrieved_at = datetime.now(timezone.utc)
    base_url = "https://api.fda.gov/drug/event.json?" + urlencode(
        {
            "search": f"patient.drug.medicinalproduct:{product}",
            "count": "patient.reaction.reactionmeddrapt.exact",
        }
    )
    findings: list[Finding] = []
    for record in records[:MAX_RESULTS]:
        if not isinstance(record, dict):
            continue
        signal = text(record.get("term"))
        count = _integer(record.get("count"))
        if not signal or count is None:
            continue
        findings.append(
            Finding(
                url=base_url + "#" + quote(signal.casefold()),
                title=f"{product} · {signal.title()} reports",
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=(
                    f"FAERS reported event: {signal.title()}. Report count: {count}. "
                    f"{FAERS_QUALIFICATION}"
                ),
                source="fda_safety",
                evidence_role="reference",
                safety_observations=[
                    SafetyObservationRecord(
                        product_name=product,
                        record_type="reported_event",
                        source_system="faers",
                        label=signal.title(),
                        report_count=count,
                        qualification=FAERS_QUALIFICATION,
                    )
                ],
            )
        )
    return findings


def _device_events(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    product = request.option("product_name")
    search = f'device.generic_name:"{_lucene_phrase(product)}"'
    result = run_tool(
        runtime,
        DEVICE_EVENT_TOOL,
        {"search": search, "limit": MAX_RESULTS, "skip": 0},
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in result_records(result, "results")[:MAX_RESULTS]:
        report_number = text(record.get("report_number"))
        devices = record.get("device") if isinstance(record.get("device"), list) else []
        device = devices[0] if devices and isinstance(devices[0], dict) else {}
        product_name = (
            text(device.get("brand_name"))
            or text(device.get("generic_name"))
            or product
        )
        event_type = text(record.get("event_type")) or "Device adverse-event report"
        detail = _device_event_detail(record, device)
        url = "https://api.fda.gov/device/event.json?" + urlencode(
            {"search": f'report_number:"{report_number or product}"', "limit": 1}
        )
        findings.append(
            Finding(
                url=url,
                title=f"{product_name} · {event_type}",
                query=request.query,
                retrieved_at=retrieved_at,
                published_at=parse_datetime(text(record.get("date_received")), "%Y%m%d"),
                excerpt=(detail + "\n" + MAUDE_QUALIFICATION).strip(),
                source="fda_safety",
                evidence_role="reference",
                safety_observations=[
                    SafetyObservationRecord(
                        product_name=product_name,
                        record_type="device_event",
                        source_system="maude",
                        label=event_type,
                        detail=detail[:2_000],
                        qualification=MAUDE_QUALIFICATION,
                    )
                ],
            )
        )
    return findings


def _device_recalls(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    product = request.option("product_name")
    search = f'product_description:"{_lucene_phrase(product)}"'
    result = run_tool(
        runtime,
        DEVICE_RECALL_TOOL,
        {"search": search, "limit": MAX_RESULTS, "skip": 0},
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in result_records(result, "results")[:MAX_RESULTS]:
        recall_id = text(record.get("product_res_number")) or text(record.get("cfres_id"))
        description = text(record.get("product_description")) or product
        classification = text(record.get("classification"))
        status = text(record.get("recall_status"))
        signal = classification or "Device recall"
        detail_parts = [
            value
            for value in (
                f"Status: {status}" if status else "",
                f"Firm: {text(record.get('recalling_firm'))}" if text(record.get("recalling_firm")) else "",
                f"Reason: {text(record.get('reason_for_recall'))}" if text(record.get("reason_for_recall")) else "",
                f"Product: {description}",
            )
            if value
        ]
        detail = "\n".join(detail_parts)
        url = "https://api.fda.gov/device/recall.json?" + urlencode(
            {"search": f'product_res_number:"{recall_id or product}"', "limit": 1}
        )
        findings.append(
            Finding(
                url=url,
                title=f"{description} · {signal}",
                query=request.query,
                retrieved_at=retrieved_at,
                published_at=parse_datetime(
                    text(record.get("event_date_posted")), "%Y%m%d", "%Y-%m-%d"
                ),
                excerpt=detail,
                source="fda_safety",
                safety_observations=[
                    SafetyObservationRecord(
                        product_name=description,
                        record_type="recall",
                        source_system="fda_recall",
                        label=signal,
                        detail=detail[:2_000],
                        qualification="FDA recall record; status and scope may change.",
                    )
                ],
            )
        )
    return findings


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _first(value: object) -> str:
    values = _strings(value)
    return values[0] if values else ""


def _integer(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _lucene_phrase(value: str) -> str:
    return value.replace("\\", " ").replace('"', " ").strip()


def _device_event_detail(record: dict, device: dict) -> str:
    parts: list[str] = []
    manufacturer = text(device.get("manufacturer_d_name"))
    if manufacturer:
        parts.append(f"Manufacturer: {manufacturer}")
    problems = _strings(record.get("product_problems"))
    if problems:
        parts.append("Product problems: " + ", ".join(problems[:8]))
    narratives = record.get("mdr_text")
    if isinstance(narratives, list):
        for narrative in narratives:
            if not isinstance(narrative, dict):
                continue
            description = text(narrative.get("text"))
            if description:
                parts.append("Report narrative: " + description[:1_500])
                break
    return "\n".join(parts)
