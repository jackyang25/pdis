"""ISRCTN international clinical-trial registry, called directly through its query API.

The API answers XML. This module reads only the elements a finding uses, and reads each
the way the registry states it: an outcome is either a structured measure or, on older
records, one block of text, so both are read rather than one silently returning nothing.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from ..errors import RetrievalError
from ..calls import provider_request
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
from .records import parse_datetime, structured_excerpt, text

QUERY_URL = "https://www.isrctn.com/api/query/format/default"
MAX_RESULTS = 10
#: ISRCTN publishes no rate limit. Eight calls a second, process-wide, answered cleanly in
#: a measured burst (half a second each), so four workers keep that pace.
MIN_REQUEST_INTERVAL_SECONDS = 0.125
_NS = {"i": "http://www.67bricks.com/isrctn"}


class ISRCTNSource:
    spec = SourceSpec(
        key="isrctn",
        label="ISRCTN",
        worker_limit=4,
        request_interval_seconds=MIN_REQUEST_INTERVAL_SECONDS,
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
        # Unscoped first, then the region-narrowed twin, never instead of it. The
        # narrowed request asks `recruitmentCountry`, so it finds where a trial actually
        # recruited rather than where its text mentions.
        for scope, queries, location in planned_variants(
            groups,
            region=intent.scope("region"),
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            clauses = [("condition", scope["condition"])]
            if scope["intervention"]:
                clauses.append(("intervention", scope["intervention"]))
            if location:
                clauses.append(("recruitmentCountry", location))
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=" AND ".join(f"{field}:{_quoted(value)}" for field, value in clauses),
                    tracks=tuple(active_tracks(intent)),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
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
        root = provider_request(
            runtime,
            self.spec,
            operation="query",
            url=QUERY_URL,
            query={"q": request.query, "limit": self.spec.max_results},
            headers={"Accept": "application/xml"},
            decode=_xml,
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for full_trial in root.findall("i:fullTrial", _NS):
            record = _record(full_trial)
            isrctn_id = record["isrctn_id"]
            if not isrctn_id:
                continue
            findings.append(
                Finding(
                    url=f"https://www.isrctn.com/{isrctn_id}",
                    title=record["title"] or isrctn_id,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    # When the registry assigned the number: the date the trial was first
                    # posted, which is how a registry record is dated.
                    published_at=parse_datetime(record["registered"]),
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
                            ("study_design", "Design"),
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
                        "nct": record["nct"],
                        "eudract": record["eudract"],
                        "doi": record["doi"],
                    },
                    record_key=f"isrctn:{isrctn_id}",
                    source=self.spec.key,
                    development_records=_development_records(record, isrctn_id),
                )
            )
        return findings


def _xml(raw: bytes) -> ET.Element:
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RetrievalError("ISRCTN", "invalid_response", "returned unparseable XML") from exc


def _quoted(value: str) -> str:
    """A query-language value, quoted when it holds a space so it is one term."""
    value = value.replace('"', " ").strip()
    return f'"{value}"' if any(character.isspace() for character in value) else value


def _record(full_trial: ET.Element) -> dict[str, Any]:
    trial = full_trial.find("i:trial", _NS)
    description = _child(trial, "i:trialDescription")
    participants = _child(trial, "i:participants")
    refs = _child(trial, "i:externalRefs")
    number = _child(trial, "i:isrctn")
    interventions = [
        {
            "type": _text(intervention, "i:interventionType"),
            "phase": _text(intervention, "i:phase"),
            "drugs": _text(intervention, "i:drugNames"),
            "description": _text(intervention, "i:description"),
        }
        for intervention in _all(trial, "i:interventions/i:intervention")
    ]
    return {
        "isrctn_id": f"ISRCTN{text(number.text)}" if number is not None and text(number.text) else "",
        "registered": number.get("dateAssigned", "") if number is not None else "",
        "title": _text(description, "i:title"),
        "scientific_title": _text(description, "i:scientificTitle"),
        "plain_english_summary": _text(description, "i:plainEnglishSummary"),
        "study_hypothesis": _text(description, "i:studyHypothesis"),
        "primary_outcomes": _outcomes(description, "primary"),
        "secondary_outcomes": _outcomes(description, "secondary"),
        "conditions": [
            _text(condition, "i:description") or _text(condition, "i:diseaseClass1")
            for condition in _all(trial, "i:conditions/i:condition")
        ],
        "interventions": interventions,
        "phase": next((item["phase"] for item in interventions if item["phase"]), ""),
        "drug_names": [item["drugs"] for item in interventions if item["drugs"]],
        "study_design": _text(_child(trial, "i:trialDesign"), "i:studyDesign"),
        "eligibility": {
            "inclusion": _text(participants, "i:inclusion"),
            "exclusion": _text(participants, "i:exclusion"),
            "age range": _text(participants, "i:ageRange"),
            "gender": _text(participants, "i:gender"),
        },
        "recruitment_countries": [
            text(country.text) for country in _all(participants, "i:recruitmentCountries/i:country")
        ],
        "target_enrolment": _text(participants, "i:targetEnrolment"),
        "sponsors": [
            _text(sponsor, "i:organisation") for sponsor in full_trial.findall("i:sponsor", _NS)
        ],
        "doi": _text(refs, "i:doi"),
        "eudract": _text(refs, "i:eudraCTNumber"),
        "nct": _text(refs, "i:clinicalTrialsGovNumber"),
    }


def _outcomes(description: ET.Element | None, kind: str) -> list[str]:
    """A trial's outcomes, whether stated as structured measures or as one text block."""
    measures = [
        " - ".join(
            part
            for part in (
                _text(measure, "i:variable"),
                _text(measure, "i:method"),
                _text(measure, "i:timepoints"),
            )
            if part
        )
        for measure in _all(description, f"i:{kind}Outcomes/i:outcomeMeasure")
    ]
    measures = [measure for measure in measures if measure]
    return measures or [value for value in [_text(description, f"i:{kind}Outcome")] if value]


def _development_records(record: dict[str, Any], record_id: str) -> list[DevelopmentRecord]:
    """One programme per intervention, named as the registry states it.

    `drugNames` is free text, so it is not split: splitting on commas turned "RTS,S/AS01"
    into "RTS" and "S/AS01". Which named products are one programme is Scout's identity
    layer to decide, not a punctuation rule's.
    """
    names = record["drug_names"]
    sponsor = next((name for name in record["sponsors"] if name), "")
    return [
        DevelopmentRecord(
            program_name=name,
            record_type="clinical_trial",
            record_id=record_id,
            sponsor=sponsor,
            phase=record["phase"],
        )
        for name in dict.fromkeys(names)
        if name.casefold() not in {"drug", "device", "vaccine", "biological"}
    ]


def _child(parent: ET.Element | None, path: str) -> ET.Element | None:
    return parent.find(path, _NS) if parent is not None else None


def _all(parent: ET.Element | None, path: str) -> list[ET.Element]:
    return parent.findall(path, _NS) if parent is not None else []


def _text(parent: ET.Element | None, path: str) -> str:
    element = _child(parent, path)
    return text(element.text) if element is not None else ""
