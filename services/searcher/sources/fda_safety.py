"""Conditional FDA safety-signal retrieval from openFDA.

This lane uses only document-stated product names. It keeps official label
warnings, spontaneous-report counts, device adverse-event reports, and recalls
as distinct structured observations. None is promoted to causal proof.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

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
from .openfda import MIN_REQUEST_INTERVAL_SECONDS, OPENFDA, first, openfda_search, phrase, strings
from .planning import request_lineage
from .records import parse_datetime, text

LABEL_WARNINGS = "label_warnings"
REPORTED_EVENTS = "reported_events"
DEVICE_EVENTS = "device_events"
DEVICE_RECALLS = "device_recalls"
DRUG_ENTITY_TYPES = {"drug", "compound", "vaccine"}
DEVICE_ENTITY_TYPES = {"device"}
PRODUCT_ENTITY_TYPES = tuple(sorted(DRUG_ENTITY_TYPES | DEVICE_ENTITY_TYPES))
MAX_PRODUCTS = 3
MAX_RESULTS = 10
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
        # openFDA's quota, shared with the `fda` lane.
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        rate_group=OPENFDA,
        # Off by default: it plans nothing until a caller names a product or target.
        default_enabled=False,
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
                (LABEL_WARNINGS, REPORTED_EVENTS)
                if product.entity_type in DRUG_ENTITY_TYPES
                else (DEVICE_EVENTS, DEVICE_RECALLS)
            )
            for operation in operations:
                requests.append(
                    SearchRequest(
                        scope_ref=intent.scope_ref,
                        source=self.spec.key,
                        query=_SEARCHES[operation](product.name),
                        tracks=tuple(active_tracks(intent)),
                        document_refs=document_refs,
                        intent_ids=intent_ids,
                        input_queries=input_queries,
                        operation=operation,
                        options=(("product_name", product.name),),
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
        read = _READERS.get(request.operation)
        if read is None:
            raise RuntimeError(f"Unsupported FDA safety operation: {request.operation}")
        return read(request, runtime)


def _drug_search(product: str) -> str:
    """A product as FAERS reports name it: as reported, or by openFDA's generic or brand."""
    name = phrase(product)
    return (
        f"patient.drug.medicinalproduct:{name} "
        f"patient.drug.openfda.generic_name:{name} "
        f"patient.drug.openfda.brand_name:{name}"
    )


_SEARCHES = {
    LABEL_WARNINGS: lambda product: (
        f"openfda.brand_name:{phrase(product)} openfda.generic_name:{phrase(product)}"
    ),
    REPORTED_EVENTS: _drug_search,
    DEVICE_EVENTS: lambda product: f"device.generic_name:{phrase(product)}",
    DEVICE_RECALLS: lambda product: f"product_description:{phrase(product)}",
}


def _drug_warnings(request: SearchRequest, runtime: SearchRuntime) -> list[Finding]:
    product = request.option("product_name")
    records = openfda_search(
        runtime, FDASafetySource.spec, "drug/label.json", request.query,
        limit=FDASafetySource.spec.max_results,
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        # The label's set id names it across revisions. A record without one is not a
        # label anyone can open, so it is not kept.
        set_id = text(record.get("set_id"))
        if not set_id:
            continue
        boxed = strings(record.get("boxed_warning"))
        # The current label format states warnings as `warnings_and_cautions`, the older
        # one as `warnings`; reading only the second missed every current-format label
        # without a boxed warning.
        warnings = strings(record.get("warnings_and_cautions")) or strings(record.get("warnings"))
        details = [*boxed, *warnings]
        if not details:
            continue
        names = record.get("openfda") if isinstance(record.get("openfda"), dict) else {}
        product_name = first(names.get("brand_name")) or first(names.get("generic_name")) or product
        signal = "Boxed warning" if boxed else "Official label warning"
        detail = " ".join(details)
        findings.append(
            Finding(
                url=(
                    "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?"
                    + urlencode({"setid": set_id})
                ),
                title=f"{product_name} · {signal}",
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=detail[:16_000],
                identifiers={"setid": set_id, "spl_id": text(record.get("id"))},
                record_key=f"fda_safety:label_warning:{set_id}",
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
    counts = openfda_search(
        runtime, FDASafetySource.spec, "drug/event.json", request.query,
        limit=FDASafetySource.spec.max_results,
        count="patient.reaction.reactionmeddrapt.exact",
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in counts:
        signal = text(record.get("term"))
        count = _integer(record.get("count"))
        if not signal or count is None:
            continue
        findings.append(
            Finding(
                # A query returning this reaction's reports for this product, so the count
                # can be checked: its total is the count shown.
                url="https://api.fda.gov/drug/event.json?"
                + urlencode(
                    {
                        "search": (
                            f"({request.query}) AND "
                            f"patient.reaction.reactionmeddrapt.exact:{phrase(signal)}"
                        ),
                        "limit": 1,
                    }
                ),
                title=f"{product} · {signal.title()} reports",
                query=request.query,
                retrieved_at=retrieved_at,
                excerpt=(
                    f"FAERS reported event: {signal.title()}. Report count: {count}. "
                    f"{FAERS_QUALIFICATION}"
                ),
                excerpt_kind="structured_fields",
                record_key=f"fda_safety:faers:{product}:{signal}",
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
    records = openfda_search(
        runtime, FDASafetySource.spec, "device/event.json", request.query,
        limit=FDASafetySource.spec.max_results,
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        report_number = text(record.get("report_number"))
        if not report_number:
            continue
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
            {"search": f'report_number:"{report_number}"', "limit": 1}
        )
        findings.append(
            Finding(
                url=url,
                title=f"{product_name} · {event_type}",
                query=request.query,
                retrieved_at=retrieved_at,
                published_at=parse_datetime(text(record.get("date_received")), "%Y%m%d"),
                excerpt=(detail + "\n" + MAUDE_QUALIFICATION).strip(),
                excerpt_kind="structured_fields",
                record_key=f"fda_safety:device_event:{report_number}",
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
    records = openfda_search(
        runtime, FDASafetySource.spec, "device/recall.json", request.query,
        limit=FDASafetySource.spec.max_results,
    )
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        recall_id = text(record.get("product_res_number"))
        if not recall_id:
            continue
        description = text(record.get("product_description")) or product
        classification = text(record.get("classification"))
        status = text(record.get("recall_status"))
        signal = classification or "Device recall"
        firm = text(record.get("recalling_firm"))
        reason = text(record.get("reason_for_recall"))
        detail = "\n".join(
            value
            for value in (
                f"Status: {status}" if status else "",
                f"Firm: {firm}" if firm else "",
                f"Reason: {reason}" if reason else "",
                f"Product: {description}",
            )
            if value
        )
        url = "https://api.fda.gov/device/recall.json?" + urlencode(
            {"search": f'product_res_number:"{recall_id}"', "limit": 1}
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
                excerpt_kind="structured_fields",
                record_key=f"fda_safety:recall:{recall_id}",
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


_READERS = {
    LABEL_WARNINGS: _drug_warnings,
    REPORTED_EVENTS: _faers_reactions,
    DEVICE_EVENTS: _device_events,
    DEVICE_RECALLS: _device_recalls,
}


def _integer(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _device_event_detail(record: dict, device: dict) -> str:
    parts: list[str] = []
    manufacturer = text(device.get("manufacturer_d_name"))
    if manufacturer:
        parts.append(f"Manufacturer: {manufacturer}")
    problems = strings(record.get("product_problems"))
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
