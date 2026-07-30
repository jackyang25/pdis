from __future__ import annotations

from typing import Any


def serialize_table_row(
    headers: list[str],
    values: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    """Serialize one parsed table row without discarding its cell boundaries."""
    fragments: list[str] = []
    cells: list[dict[str, Any]] = []
    cursor = 0

    for column_index, value in enumerate(values):
        if not value.strip():
            continue

        header = headers[column_index].strip() if column_index < len(headers) else ""
        prefix = f"{header}: " if header else ""
        fragment = f"{prefix}{value}"
        if fragments:
            cursor += 2  # Length of the canonical ", " separator.

        content_start = cursor
        value_start = content_start + len(prefix)
        content_end = content_start + len(fragment)
        cells.append(
            {
                "column_index": column_index,
                "header": header,
                "value": value,
                "content_start": content_start,
                "content_end": content_end,
                "value_start": value_start,
                "value_end": content_end,
            }
        )
        fragments.append(fragment)
        cursor = content_end

    return ", ".join(fragments), cells
