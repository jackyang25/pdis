"""EU Clinical Trials Information System, called directly through its public search API.

The API is the one the CTIS public portal itself calls: a JSON POST of search criteria and
a page. It is undocumented, so this lane asks it one thing - trials for a medical condition
- and reads only the fields that search returns.

Findings feed insights, not the development landscape. The search names the products a
trial uses, but as one list of everything administered - investigational product,
comparator and placebo excipients alike - so a programme read from it could be "Lactose
Monohydrate".
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..calls import provider_request
from ..errors import RetrievalError
from ..models import (
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

SEARCH_URL = "https://euclinicaltrials.eu/ctis-public-api/search"
MAX_RESULTS = 10
#: The portal's own API publishes no limit. Four calls a second, process-wide, answered
#: cleanly in a measured burst (half a second each); two workers keep that pace.
MIN_REQUEST_INTERVAL_SECONDS = 0.25
#: CTIS reports a trial's status as a code. These are the labels its own record view
#: gives each code (checked against `/retrieve` live); 2 to 5 are all "Authorised".
_STATUS = {
    1: "Under evaluation",
    2: "Authorised",
    3: "Authorised",
    4: "Authorised",
    5: "Authorised",
    6: "Halted",
    7: "Suspended",
    8: "Ended",
    9: "Expired",
    10: "Revoked",
    11: "Not authorised",
    12: "Cancelled",
}


class CTISSource:
    spec = SourceSpec(
        key="ctis",
        label="EU CTIS",
        worker_limit=2,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        evidence_domains=("clinical", "safety"),
        attribution=SourceAttribution(
            label="EU Clinical Trials Information System",
            url="https://euclinicaltrials.eu/",
            prefix="Trial data provided by",
        ),
        evidence_class="registry",
        jurisdiction="eu",
        reads=("text", "condition"),
        feeds=("insights",),
        max_results=MAX_RESULTS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        # The condition is the whole request and is the intent's anchor, so no query can
        # vary it: one request per intent, carrying every query in its lineage.
        intent_ids, input_queries, document_refs = request_lineage(list(intent.queries))
        condition = (intent.indication or intent.topic).strip()
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=f"medicalCondition:{condition}",
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                options=(("medical_condition", condition),),
            )
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
    ) -> list[Finding]:
        payload = provider_request(
            runtime,
            self.spec,
            operation="search",
            url=SEARCH_URL,
            body={
                "pagination": {"page": 1, "size": self.spec.max_results},
                "searchCriteria": {"medicalCondition": request.option("medical_condition")},
            },
        )
        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise RetrievalError("EU CTIS", "invalid_response", "no result list")
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            ct_number = text(record.get("ctNumber"))
            if not ct_number:
                continue
            findings.append(
                Finding(
                    url=f"https://euclinicaltrials.eu/ctis-public/view/{ct_number}",
                    title=text(record.get("ctTitle")) or ct_number,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    # No publication date: the search returns only the EU start date and
                    # the date of the latest edit, and neither says when the trial was
                    # published. A record with no date is admitted by a window.
                    excerpt=structured_excerpt(
                        {**record, "status": _STATUS.get(record.get("ctStatus"), "")},
                        (
                            ("conditions", "Conditions"),
                            ("trialPhase", "Phase"),
                            ("status", "Status"),
                            ("product", "Products"),
                            ("primaryEndPoint", "Primary endpoint"),
                            ("endPoint", "Secondary endpoint"),
                            ("sponsor", "Sponsor"),
                            ("trialCountries", "Countries (sites)"),
                            ("ageGroup", "Age group"),
                            ("totalNumberEnrolled", "Enrollment"),
                            ("resultsFirstReceived", "Results posted"),
                            ("startDateEU", "EU start date"),
                        ),
                    ),
                    excerpt_kind="structured_fields",
                    identifiers={"euct": ct_number},
                    record_key=f"ctis:{ct_number}",
                    source=self.spec.key,
                )
            )
        return findings
