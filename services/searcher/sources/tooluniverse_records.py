"""Shared mechanics for ToolUniverse-backed adapters.

ToolUniverse standardizes execution, not result schemas. Source adapters still own their
database-specific URLs, titles and identities; these helpers only run an allowlisted tool
(paced against its provider and reused within a run), validate the tool's envelope, and
render a record's fields into an excerpt.

Records arrive in the provider's order and are kept in it. An earlier pass re-ranked
them by counting query words in their flattened JSON and kept the top few, so the
records a model saw were chosen by substring matches over field names and boilerplate
rather than by the provider's own ranking - and the request had asked for more records
than were ever kept. A request now asks for the number it keeps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ..calls import provider_call
from ..errors import RetrievalError
from ..models import SearchRuntime, SourceSpec

TOOLUNIVERSE_INTEGRATION = "tooluniverse"
MAX_EXCERPT_CHARS = 16_000


def run_tool(
    runtime: SearchRuntime,
    spec: SourceSpec,
    operation: str,
    arguments: Mapping[str, Any],
) -> Any:
    """Execute one allowlisted operation through the injected connector.

    Paced against the lane's rate group and made at most once per run for one set of
    arguments. The returned value may be shared with another request: read it, never
    alter it.
    """
    connector = runtime.integrations.get(TOOLUNIVERSE_INTEGRATION)
    if connector is None or not callable(getattr(connector, "run", None)):
        raise RetrievalError(
            spec.label, "not_configured", "ToolUniverse connector is not configured"
        )
    return provider_call(
        runtime,
        rate_group=spec.rate_group,
        interval_seconds=spec.request_interval_seconds,
        operation=operation,
        arguments=arguments,
        load=lambda: connector.run(operation, dict(arguments)),
    )


def result_records(result: Any, *collection_keys: str) -> list[dict[str, Any]]:
    """Validate a ToolUniverse envelope and return its structured records."""
    if not isinstance(result, dict):
        raise RetrievalError(
            "ToolUniverse", "invalid_response", "unexpected result shape"
        )
    if result.get("status") == "error" or result.get("error"):
        raise RetrievalError(
            "ToolUniverse", "tool_error", str(result.get("error") or "tool failed")
        )
    records: Any = _first_collection(result, collection_keys)
    if records is None and isinstance(result.get("data"), Mapping):
        # Some ToolUniverse wrappers retain the upstream provider envelope,
        # e.g. openFDA returns {data: {meta: ..., results: [...]}}.
        records = _first_collection(result["data"], collection_keys)
    if records is None:
        records = result.get("data", result.get("results", []))
    if not isinstance(records, list):
        raise RetrievalError(
            "ToolUniverse", "invalid_response", "non-list record collection"
        )
    return [record for record in records if isinstance(record, dict)]


def structured_excerpt(
    record: Mapping[str, Any],
    fields: Sequence[tuple[str, str]],
    *,
    max_chars: int = MAX_EXCERPT_CHARS,
) -> str | None:
    """Render a record's fields, in their declared order, into a bounded excerpt.

    The same record always yields the same excerpt. Ordering fields by the request's
    query words made one record's excerpt depend on which request returned it, so two
    lanes - or two attributes - quoting one trial quoted different text.
    """
    output: list[str] = []
    size = 0
    for field, label in fields:
        text = value_text(record.get(field)).strip()
        if not text:
            continue
        remaining = max_chars - size
        if remaining <= 0:
            break
        line = f"{label}: {text}"
        rendered = line if len(line) <= remaining else line[:remaining].rstrip() + "…"
        output.append(rendered)
        size += len(rendered) + 1
        if len(rendered) < len(line):
            break
    return "\n".join(output) or None


def value_text(value: Any) -> str:
    """Flatten a JSON-like provider value for display."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, Mapping):
        return "; ".join(
            f"{key}: {rendered}"
            for key, item in value.items()
            if (rendered := value_text(item))
        )
    if isinstance(value, (list, tuple)):
        return "; ".join(
            rendered for item in value if (rendered := value_text(item))
        )
    return str(value)


def parse_datetime(value: Any, *formats: str) -> datetime | None:
    """Parse a full provider date as UTC without guessing unsupported formats."""
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
