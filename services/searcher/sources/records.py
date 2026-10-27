"""Reading provider records: a field's text, a provider date, and a record's excerpt.

Records arrive in the provider's order and are kept in it. An earlier pass re-ranked them
by counting query words in their flattened JSON and kept the top few, so the records a
model saw were chosen by substring matches over field names and boilerplate rather than by
the provider's own ranking - and the request had asked for more records than were ever
kept. A request now asks for the number it keeps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

MAX_EXCERPT_CHARS = 16_000


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
        rendered_value = value_text(record.get(field)).strip()
        if not rendered_value:
            continue
        remaining = max_chars - size
        if remaining <= 0:
            break
        line = f"{label}: {rendered_value}"
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


def text(value: Any) -> str:
    """A provider string with its whitespace collapsed, or blank for anything else."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def bounded(passage: str, max_chars: int = MAX_EXCERPT_CHARS) -> str:
    return passage if len(passage) <= max_chars else passage[:max_chars].rstrip() + "..."


def parse_datetime(value: Any, *formats: str) -> datetime | None:
    """Parse a full provider date as UTC without guessing unsupported formats."""
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if stripped.endswith("Z"):
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            pass
    for date_format in formats:
        try:
            return datetime.strptime(stripped, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
