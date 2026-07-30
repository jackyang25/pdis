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

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache

from ..models import DevelopmentRecord, Finding

logger = logging.getLogger(__name__)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
REQUEST_TIMEOUT_SECONDS = 35  # match PubMed: tolerate rare slow calls (e.g. WARP latency)
MAX_RESULTS = 20
MAX_EXCERPT_CHARS = 6000

# CT.gov publishes no hard rate limit but asks clients to be considerate. The
# scout fans out many queries in parallel, so space request STARTS
# process-wide (same pattern as the PubMed backend), not per-thread.
_RATE_LOCK = threading.Lock()
_FETCH_LOCK = threading.Lock()
_NEXT_ALLOWED = 0.0
RATE_INTERVAL = 0.12  # ~8 requests/sec across all threads
MAX_RETRIES_ON_429 = 2


def _throttle() -> None:
    """Block until at least RATE_INTERVAL has passed since the last request,
    globally across all threads."""
    global _NEXT_ALLOWED
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _NEXT_ALLOWED - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _NEXT_ALLOWED = now + RATE_INTERVAL




def fetch_clinicaltrials_studies(
    *,
    condition: str,
    intervention: str,
    term: str,
    max_results: int,
) -> list[dict]:
    """Return a bounded structured candidate set.

    The lock makes the memoized fetch single-flight. Scout plans one request per
    field, but fields in one run usually share the same registry filters; only
    the first request should reach the provider.
    """
    with _FETCH_LOCK:
        return _fetch_studies(condition, intervention, term, max_results)


@lru_cache(maxsize=512)
def _fetch_studies(
    condition: str,
    intervention: str,
    term: str,
    max_results: int,
) -> list[dict]:
    """Fetch raw studies for a structured (condition/intervention) or free-text
    query. Memoized by the full structured request.
    """
    if not (condition or intervention or term):
        return []
    params = {"pageSize": str(max_results), "format": "json"}
    if condition:
        params["query.cond"] = condition
    if intervention:
        params["query.intr"] = intervention
    if term:
        params["query.term"] = term
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "pdis-scout/0.1 (mailto:devnull@example.com)"},
    )
    for attempt in range(MAX_RETRIES_ON_429 + 1):
        _throttle()
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read())
            return data.get("studies", []) or []
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES_ON_429:
                time.sleep(RATE_INTERVAL * (2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            raise
    raise RuntimeError("unreachable")


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
        ident.get("briefTitle") or ident.get("officialTitle") or f"Trial {nct_id}"
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

    return Finding(
        url=f"https://clinicaltrials.gov/study/{nct_id}",
        title=full_title,
        query=query,
        retrieved_at=retrieved_at,
        excerpt=excerpt,
        published_at=_parse_date(_last_update(status_mod)),
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


def _last_update(status_mod: dict) -> str:
    for key in ("lastUpdatePostDateStruct", "startDateStruct"):
        struct = status_mod.get(key) or {}
        date = (struct.get("date") or "").strip()
        if date:
            return date
    return ""


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    parts = raw.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return datetime(year, month, day, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def _clean_text(text: str) -> str:
    return " ".join(text.split())
