"""Direct ClinicalTrials.gov retrieval: query -> list[Finding].

A third retrieval backend alongside web and PubMed. The ClinicalTrials.gov API
v2 is free and keyless. Registry records are high-signal for two layers in
particular: a TERMINATED / WITHDRAWN trial (with its why-stopped reason) is
direct disconfirming/precedent evidence, and reported phase + status helps
ground conformity.

Transport/parse failures propagate to the source controller, which records a
failed outcome without affecting other adapters.
"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone

from ..calls import provider_call
from ..dates import iso_partial_date
from ..models import DevelopmentRecord, Finding, SearchRuntime
from ..transport import fetch_json, user_agent

logger = logging.getLogger(__name__)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
REQUEST_TIMEOUT_SECONDS = 35  # match PubMed: tolerate rare slow calls (e.g. WARP latency)
MAX_EXCERPT_CHARS = 6000

#: The parts of a study record this lane reads, and nothing else. A full record carries
#: every location, outcome measure and result table: 100 full studies came back as 7 MB
#: against 0.4 MB projected (measured live), for fields no stage reads.
STUDY_FIELDS = "|".join(
    (
        "protocolSection.identificationModule",
        "protocolSection.statusModule",
        "protocolSection.designModule.phases",
        "protocolSection.descriptionModule.briefSummary",
        "protocolSection.conditionsModule.conditions",
        "protocolSection.armsInterventionsModule",
        "protocolSection.sponsorCollaboratorsModule.leadSponsor",
        "hasResults",
    )
)


def fetch_clinicaltrials_studies(
    runtime: SearchRuntime,
    *,
    rate_group: str,
    interval_seconds: float,
    condition: str,
    intervention: str,
    max_results: int,
    region: str = "",
    first_posted_since: str = "",
) -> list[dict]:
    """Return the provider's own top `max_results` studies, in its order.

    Made at most once per run for one set of filters: Scout plans one request per field,
    and fields in one run usually share the same registry filters. The list is a copy,
    because the answer is shared; its records are shared too and are read, never altered.
    """
    if not (condition or intervention):
        return []
    params = {
        "pageSize": str(max_results),
        "format": "json",
        "fields": STUDY_FIELDS,
    }
    if condition:
        params["query.cond"] = condition
    if intervention:
        params["query.intr"] = intervention
    if region:
        # The provider's own location field. A region in `query.term` would match
        # studies that mention the place, not studies running there.
        params["query.locn"] = region
    if first_posted_since:
        # The provider applies the window, so the page holds the top studies inside it
        # rather than the top studies overall with the old ones discarded afterwards.
        params["filter.advanced"] = (
            f"AREA[StudyFirstPostDate]RANGE[{first_posted_since},MAX]"
        )
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"

    def load() -> list[dict]:
        data = fetch_json(
            url,
            provider="ClinicalTrials.gov",
            headers={"User-Agent": user_agent(runtime.contact_email)},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        return (data.get("studies", []) if isinstance(data, dict) else []) or []

    return list(
        provider_call(
            runtime,
            rate_group=rate_group,
            interval_seconds=interval_seconds,
            operation="studies",
            arguments=params,
            load=load,
        )
    )


def clinicaltrial_to_finding(study: dict, query: str) -> Finding | None:
    """Normalize one ClinicalTrials.gov record with exact request provenance."""
    retrieved_at = datetime.now(timezone.utc)
    protocol = study.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    nct_id = (ident.get("nctId") or "").strip()
    if not nct_id:
        return None

    status_mod = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    desc = protocol.get("descriptionModule") or {}
    conditions = (protocol.get("conditionsModule") or {}).get("conditions") or []
    arms = protocol.get("armsInterventionsModule") or {}
    interventions = arms.get("interventions") or []
    arm_groups = arms.get("armGroups") or []
    intervention_roles = _intervention_source_roles(interventions, arm_groups)
    sponsor_module = protocol.get("sponsorCollaboratorsModule") or {}
    lead_sponsor = sponsor_module.get("leadSponsor") or {}

    title = (
        ident.get("briefTitle") or ident.get("officialTitle") or nct_id
    ).strip()
    status = (status_mod.get("overallStatus") or "").strip()
    phases = ", ".join(_phase_label(value) for value in (design.get("phases") or []))
    why_stopped = (status_mod.get("whyStopped") or "").strip()
    summary = (desc.get("briefSummary") or "").strip()
    has_results = bool(study.get("hasResults"))

    status_label = status.replace("_", " ").title()
    title_parts = [title]
    if phases:
        title_parts.append(phases)
    if status_label:
        title_parts.append(status_label)
    full_title = " | ".join(title_parts)

    # Lead the excerpt with the status/why-stopped/results signals: those are
    # exactly what the precedent + counterfactual layers need (a terminated
    # trial with a reason is disconfirming evidence). Summary follows for depth.
    parts: list[str] = []
    if status_label:
        parts.append(f"Status: {status_label}.")
    if phases:
        parts.append(f"Phase: {phases}.")
    if conditions:
        parts.append(f"Conditions: {', '.join(conditions)}.")
    if why_stopped:
        parts.append(f"Why stopped: {why_stopped}.")
    parts.append("Has posted results." if has_results else "No posted results.")
    if summary:
        parts.append(summary)
    excerpt = _clean_text(" ".join(parts)) or None
    if excerpt and len(excerpt) > MAX_EXCERPT_CHARS:
        excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."

    published_at, precision = iso_partial_date(
        (status_mod.get("studyFirstPostDateStruct") or {}).get("date")
    )
    return Finding(
        url=f"https://clinicaltrials.gov/study/{nct_id}",
        title=full_title,
        query=query,
        retrieved_at=retrieved_at,
        excerpt=excerpt,
        excerpt_kind="structured_fields",
        # First posted, not last updated: a registry record's publication is when it
        # appeared, and reading the latest edit let a decade-old trial pass a window
        # because someone corrected its contact details last month.
        published_at=published_at,
        published_precision=precision,
        identifiers={"nct": nct_id},
        record_key=f"clinicaltrials:{nct_id}",
        source="clinicaltrials",
        development_records=[
            DevelopmentRecord(
                program_name=name,
                record_type="clinical_trial",
                record_id=nct_id,
                sponsor=str(lead_sponsor.get("name") or "").strip(),
                phase=phases,
                status=status_label,
                source_role=intervention_roles.get(name.casefold(), "unknown"),
            )
            for name in _intervention_names(interventions)
        ],
    )


def _intervention_names(interventions: object) -> list[str]:
    """Return explicit registry intervention names without parsing prose."""
    if not isinstance(interventions, list):
        return []
    names: list[str] = []
    for intervention in interventions:
        if not isinstance(intervention, dict):
            continue
        name = str(intervention.get("name") or "").strip()
        if name and name.casefold() not in {"drug", "device", "vaccine", "biological"}:
            names.append(name)
    return list(dict.fromkeys(names))


def _intervention_source_roles(
    interventions: object,
    arm_groups: object,
) -> dict[str, str]:
    """Map interventions to roles stated by ClinicalTrials.gov arm metadata.

    Names and arm labels are provider-owned identifiers. This function never
    infers a role from intervention prose.
    """
    if not isinstance(interventions, list) or not isinstance(arm_groups, list):
        return {}

    roles_by_label: dict[str, str] = {}
    names_by_label: dict[str, list[str]] = {}
    for group in arm_groups:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or "").strip().casefold()
        source_role = _arm_type_source_role(group.get("type"))
        if label and source_role:
            roles_by_label[label] = source_role
        for raw_name in group.get("interventionNames") or []:
            name = str(raw_name or "").strip()
            if label and name:
                names_by_label.setdefault(label, []).append(name)

    roles_by_name: dict[str, set[str]] = {}
    for intervention in interventions:
        if not isinstance(intervention, dict):
            continue
        name = str(intervention.get("name") or "").strip()
        if not name:
            continue
        labels = {
            str(label or "").strip().casefold()
            for label in intervention.get("armGroupLabels") or []
            if str(label or "").strip()
        }
        labels.update(
            label
            for label, names in names_by_label.items()
            if name in names
        )
        roles_by_name.setdefault(name.casefold(), set()).update(
            roles_by_label[label]
            for label in labels
            if label in roles_by_label
        )

    return {
        name: next(iter(roles)) if len(roles) == 1 else "unknown"
        for name, roles in roles_by_name.items()
    }


def _arm_type_source_role(value: object) -> str:
    return {
        "EXPERIMENTAL": "experimental",
        "ACTIVE_COMPARATOR": "comparator",
        "PLACEBO_COMPARATOR": "control",
        "SHAM_COMPARATOR": "control",
        "NO_INTERVENTION": "control",
    }.get(str(value or "").strip().upper(), "")


def _phase_label(value: object) -> str:
    labels = {
        "EARLY_PHASE1": "Early Phase 1",
        "PHASE1": "Phase 1",
        "PHASE2": "Phase 2",
        "PHASE3": "Phase 3",
        "PHASE4": "Phase 4",
        "NA": "Not applicable",
    }
    text = str(value or "").strip()
    return labels.get(text, text.replace("_", " ").title())


def _clean_text(text: str) -> str:
    return " ".join(text.split())
