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
from functools import lru_cache

from ..models import Finding

logger = logging.getLogger(__name__)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
REQUEST_TIMEOUT_SECONDS = 35  # match PubMed: tolerate rare slow calls (e.g. WARP latency)
MAX_RESULTS = 20
MAX_EXCERPT_CHARS = 6000

# CT.gov publishes no hard rate limit but asks clients to be considerate. The
# scout fans out many queries in parallel, so space request STARTS
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


def search_clinicaltrials(
    query: str,
    *,
    condition: str | None = None,
    intervention: str | None = None,
    max_results: int = MAX_RESULTS,
) -> list[Finding]:
    """Search ClinicalTrials.gov and return Findings. Never raises: any problem
    yields no registry findings, leaving other backends unaffected.

    CT.gov is a STRUCTURED registry that keyword-matches: long free-text queries
    (and non-English ones) return nothing or 400 "too complicated query". So when
    the caller knows the condition + intervention (the scout always does), we
    search those structured fields, which returns the real trial landscape. We
    fall back to free-text term search only when they are absent (e.g. the
    standalone searcher tool).
    """
    condition = (condition or "").strip()
    intervention = (intervention or "").strip()
    term = "" if (condition or intervention) else query.strip()
    try:
        studies = _fetch_studies(condition, intervention, term, max_results)
    except Exception as exc:  # noqa: BLE001 - one quiet line; the lane degrades gracefully
        logger.warning("ClinicalTrials.gov retrieval skipped (%s)", exc)
        return []

    # Provenance label: the structured terms actually searched, not the (ignored)
    # free-text query, so the UI's "searched: ..." reads honestly.
    label = " ".join(t for t in (condition, intervention) if t) or query
    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for study in studies:
        finding = _study_to_finding(study, label, retrieved_at)
        if finding is not None:
            findings.append(finding)
    return findings


@lru_cache(maxsize=512)
def _fetch_studies(
    condition: str,
    intervention: str,
    term: str,
    max_results: int,
) -> list[dict]:
    """Fetch raw studies for a structured (condition/intervention) or free-text
    query. Memoized: the scout issues the SAME (condition, intervention) for
    every query in a run, so the registry is hit once per product area, not once
    per query.
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
