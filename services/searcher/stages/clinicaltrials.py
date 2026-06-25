"""Direct ClinicalTrials.gov retrieval: query -> list[Finding].

A third retrieval backend alongside web and PubMed. The ClinicalTrials.gov API
v2 is free and keyless. Registry records are high-signal for two layers in
particular: a TERMINATED / WITHDRAWN trial (with its why-stopped reason) is
direct disconfirming/precedent evidence, and reported phase + status helps
ground conformity.

Deliberately robust: any HTTP/parse problem returns no findings, leaving the
other backends unaffected (mirrors the PubMed backend's contract).
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

from ..models import Finding

logger = logging.getLogger(__name__)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
REQUEST_TIMEOUT_SECONDS = 20
MAX_RESULTS = 20
MAX_EXCERPT_CHARS = 6000

# CT.gov publishes no hard rate limit but asks clients to be considerate. The
# monitor fans out many queries in parallel, so space request STARTS
# process-wide (same pattern as the PubMed backend), not per-thread.
_RATE_LOCK = threading.Lock()
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


def search_clinicaltrials(query: str, *, max_results: int = MAX_RESULTS) -> list[Finding]:
    """Search ClinicalTrials.gov and return Findings. Never raises: any problem
    yields no registry findings, leaving other backends unaffected."""
    try:
        studies = _fetch_studies(query, max_results=max_results)
    except Exception:
        logger.exception("ClinicalTrials.gov retrieval failed for query %r", query)
        return []

    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for study in studies:
        finding = _study_to_finding(study, query, retrieved_at)
        if finding is not None:
            findings.append(finding)
    return findings


def _fetch_studies(query: str, *, max_results: int) -> list[dict]:
    params = {
        "query.term": query,
        "pageSize": str(max_results),
        "format": "json",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "pdis-monitor/0.1 (mailto:devnull@example.com)"},
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
            logger.warning("ClinicalTrials.gov request failed (%s)", exc.code)
            raise
        except (urllib.error.URLError, TimeoutError):
            logger.warning("ClinicalTrials.gov request failed (network)")
            raise
    raise RuntimeError("unreachable")


def _study_to_finding(study: dict, query: str, retrieved_at: datetime) -> Finding | None:
    protocol = study.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    nct_id = (ident.get("nctId") or "").strip()
    if not nct_id:
        return None

    status_mod = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    desc = protocol.get("descriptionModule") or {}
    conditions = (protocol.get("conditionsModule") or {}).get("conditions") or []

    title = (
        ident.get("briefTitle") or ident.get("officialTitle") or f"Trial {nct_id}"
    ).strip()
    status = (status_mod.get("overallStatus") or "").strip()
    phases = ", ".join(design.get("phases") or [])
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
    )


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
