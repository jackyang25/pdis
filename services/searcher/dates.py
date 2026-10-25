"""Provider dates that state less than a day.

A provider often states a year (Europe PMC, Semantic Scholar), a month (a PubMed issue, a
registry's `YYYY-MM`) or a season. Reading that as the first day of the period and then
comparing it to a window's lower bound drops a record the window admits: a paper dated
"2024" read as 1 January 2024 fails a window starting in June 2024, though it may well
have been published in December. So a partial date keeps its precision, and a lower bound
is compared with the latest day the stated date allows.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone

PUBLISHED_PRECISIONS = frozenset({"day", "month", "year"})


def partial_date(
    year: int,
    month: int | None = None,
    day: int | None = None,
) -> tuple[datetime | None, str]:
    """Return the first day the stated parts allow, and how precise they were."""
    try:
        if month is None:
            return datetime(year, 1, 1, tzinfo=timezone.utc), "year"
        if day is None:
            return datetime(year, month, 1, tzinfo=timezone.utc), "month"
        return datetime(year, month, day, tzinfo=timezone.utc), "day"
    except ValueError:
        if month is not None and 1 <= month <= 12:
            return partial_date(year, month)
        if 1 <= year <= 9999:
            return partial_date(year)
        return None, ""


def iso_partial_date(value: object) -> tuple[datetime | None, str]:
    """Read `YYYY`, `YYYY-MM` or `YYYY-MM-DD` (time ignored); anything else is no date."""
    if not isinstance(value, str):
        return None, ""
    text = value.strip()[:10]
    parts = text.split("-")
    if not parts or not all(part.isdigit() for part in parts) or len(parts[0]) != 4:
        return None, ""
    numbers = [int(part) for part in parts[:3]]
    return partial_date(*numbers)  # type: ignore[arg-type]


def latest_day(start: date, precision: str) -> date:
    """The last day a date stated to `precision` may be, starting from its first day."""
    if precision == "year":
        return date(start.year, 12, 31)
    if precision == "month":
        return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
    return start


def published_label(published_at: date | None, precision: str) -> str:
    """A publication date as a model is shown it: at the precision the source stated it,
    or that it stated none. Scout's judging stages and Drafter's suggestion read the same."""
    if published_at is None:
        return "not stated by the source"
    if precision == "year":
        return f"{published_at.year} (year only)"
    if precision == "month":
        return f"{published_at.year}-{published_at.month:02d} (month only)"
    return published_at.isoformat()
