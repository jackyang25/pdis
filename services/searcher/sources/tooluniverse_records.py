"""Shared mechanics for deterministic ToolUniverse record normalization.

ToolUniverse standardizes execution, not result schemas. Source adapters still
own their database-specific URLs and titles; these helpers only validate a
tool result and rank/excerpt structured records against the exact neutral input
queries carried by ``SearchRequest``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from ..models import SearchRequest, SearchRuntime
from ..relevance import query_terms, rank_records, score_text, value_text

TOOLUNIVERSE_INTEGRATION = "tooluniverse"
MAX_EXCERPT_CHARS = 16_000

def run_tool(
    runtime: SearchRuntime,
    operation: str,
    arguments: Mapping[str, Any],
) -> Any:
    """Execute one allowlisted operation through the injected connector."""
    connector = runtime.integrations.get(TOOLUNIVERSE_INTEGRATION)
    if connector is None or not callable(getattr(connector, "run", None)):
        raise RuntimeError("ToolUniverse connector is not configured")
    return connector.run(operation, arguments)


def result_records(result: Any, *collection_keys: str) -> list[dict[str, Any]]:
    """Validate a ToolUniverse envelope and return its structured records."""
    if not isinstance(result, dict):
        raise RuntimeError("ToolUniverse returned an unexpected result shape")
    if result.get("status") == "error" or result.get("error"):
        raise RuntimeError(str(result.get("error") or "ToolUniverse tool failed"))
    records: Any = _first_collection(result, collection_keys)
    if records is None and isinstance(result.get("data"), Mapping):
        # Some ToolUniverse wrappers retain the upstream provider envelope,
        # e.g. openFDA returns {data: {meta: ..., results: [...]}}.
        records = _first_collection(result["data"], collection_keys)
    if records is None:
        records = result.get("data", result.get("results", []))
    if not isinstance(records, list):
        raise RuntimeError("ToolUniverse returned a non-list record collection")
    return [record for record in records if isinstance(record, dict)]


def ranked_records(
    records: Iterable[dict[str, Any]],
    request: SearchRequest,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Rank a structured candidate set using every compiled neutral query.

    The provider query establishes database applicability (for example,
    condition + intervention). This deterministic second pass preserves field
    specificity without introducing another model or an untraced router.
    """
    return rank_records(records, request.input_queries, limit=limit)


def relevant_excerpt(
    record: Mapping[str, Any],
    fields: Sequence[tuple[str, str]],
    request: SearchRequest,
    *,
    max_chars: int = MAX_EXCERPT_CHARS,
) -> str | None:
    """Render the most query-relevant record fields into a bounded excerpt."""
    terms = query_terms(request.input_queries)
    candidates: list[tuple[int, int, str]] = []
    for index, (field, label) in enumerate(fields):
        text = value_text(record.get(field)).strip()
        if not text:
            continue
        candidates.append(
            (score_text(text, terms), index, f"{label}: {text}")
        )
    candidates.sort(key=lambda item: (-item[0], item[1]))
    output: list[str] = []
    size = 0
    for _, _, text in candidates:
        remaining = max_chars - size
        if remaining <= 0:
            break
        rendered = text if len(text) <= remaining else text[:remaining].rstrip() + "…"
        output.append(rendered)
        size += len(rendered) + 1
        if len(rendered) < len(text):
            break
    return "\n".join(output) or None


def parse_datetime(value: Any, *formats: str) -> datetime | None:
    """Parse a provider date as UTC without guessing unsupported formats."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass
    for date_format in formats:
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_collection(
    value: Mapping[str, Any],
    preferred_keys: Sequence[str],
) -> Any:
    for key in (*preferred_keys, "data", "results"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            return candidate
    return None
