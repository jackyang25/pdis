"""Extractor for `source_type=product_profile` (WHO PPCs, TPPs, peer-org equivalents).

Deterministic. Reads chunker `ContentBlock`s for a product-profile document
and emits draft Claims — one per non-empty target column (Minimum /
Preferred / Optimistic) in each PPC/TPP table row.

This is the "recognition" step. It does NOT bind to attributes; that's
the binder's job. attribute_ref / evidence_strength / recency_tier are
left None for downstream stages to fill.
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable

from chunker.models import ContentBlock

from ..models import Claim


# Column-header names that signal "this is a target-value column" in a
# PPC/TPP table. The extractor is publisher-agnostic — it reads the
# headers on each table_row block and adapts.
TARGET_VALUE_COLUMNS = {"Minimum", "Preferred", "Optimistic"}

# Likely names of the row-label column (the "Variable" column in
# Gates TPPs, often "Variable" or "Characteristic" in WHO PPCs).
VARIABLE_LABEL_COLUMNS = {"Variable", "Characteristic", "Attribute"}


def extract_product_profile(
    blocks: Iterable[ContentBlock],
    source_id: str,
    *,
    intervention_class: str | None = None,
    therapeutic_area: str | None = None,
    extracted_at: str | None = None,
) -> list[Claim]:
    """
    Emit draft Claims from a parsed product-profile document.

    Args:
        blocks: chunker output for the source document.
        source_id: stable identifier for this document.
        intervention_class: optional scoping tag applied to every claim.
        therapeutic_area: optional scoping tag applied to every claim.
        extracted_at: ISO date for the extraction run (defaults to today).

    Returns:
        list of draft Claim objects. Every claim has:
          - statement, claim_type=performance (default), polarity=neutral
          - source_id, source_type=product_profile, source_locator
          - intervention_class, therapeutic_area (if provided)
          - attribute_ref=None, binding_confidence=None
          - evidence_strength=None, recency_tier=None
    """
    if extracted_at is None:
        extracted_at = _dt.date.today().isoformat()

    claims: list[Claim] = []
    for block in blocks:
        if not _is_ppc_table_row(block):
            continue

        headers = block.structural_meta.get("column_headers", [])
        variable_value = _find_variable_value(block, headers)
        target_cells = _extract_target_cells(block, headers)
        if not target_cells:
            continue

        for column_name, cell_value in target_cells:
            statement = _compose_statement(variable_value, column_name, cell_value)
            claims.append(
                Claim(
                    id="",  # assigned downstream
                    ordinal=-1,
                    statement=statement,
                    claim_type="performance",  # default; binder/appraiser can refine
                    polarity="neutral",
                    source_id=source_id,
                    source_type="product_profile",
                    source_locator=_build_locator(block, column_name, cell_value),
                    extracted_at=extracted_at,
                    intervention_class=intervention_class,
                    therapeutic_area=therapeutic_area,
                    attribute_ref=None,
                    binding_confidence=None,
                    evidence_strength=None,
                    recency_tier=None,
                    review_status="unverified",
                    version=1,
                )
            )
    return claims


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_ppc_table_row(block: ContentBlock) -> bool:
    if block.source_type != "table_row":
        return False
    headers = block.structural_meta.get("column_headers", [])
    if not headers:
        return False
    # A PPC-shape table has at least one target-value column and (usually)
    # a variable-label column.
    return any(_normalize_header(h) in TARGET_VALUE_COLUMNS for h in headers)


def _find_variable_value(block: ContentBlock, headers: list[str]) -> str:
    parsed = _parse_row_content(block.content, headers)
    for header_key, header_value in parsed.items():
        if _normalize_header(header_key) in VARIABLE_LABEL_COLUMNS:
            return header_value
    # Fallback: first non-target column.
    for header_key, header_value in parsed.items():
        if _normalize_header(header_key) not in TARGET_VALUE_COLUMNS:
            return header_value
    return ""


def _extract_target_cells(
    block: ContentBlock,
    headers: list[str],
) -> list[tuple[str, str]]:
    parsed = _parse_row_content(block.content, headers)
    targets: list[tuple[str, str]] = []
    for header_key, header_value in parsed.items():
        if _normalize_header(header_key) not in TARGET_VALUE_COLUMNS:
            continue
        cleaned = header_value.strip()
        if not cleaned:
            continue
        targets.append((_normalize_header(header_key), cleaned))
    return targets


def _parse_row_content(content: str, headers: list[str]) -> dict[str, str]:
    """
    Recover {header: value} from the chunker's table_row content string.

    The chunker emits table rows as "Header: Value, Header: Value, ...".
    Splitting on comma is fragile (commas inside values), so we anchor on
    each header name.
    """
    if not headers:
        return {}

    indexed: list[tuple[int, str]] = []
    for header in headers:
        if not header:
            continue
        marker = f"{header}:"
        position = content.find(marker)
        if position >= 0:
            indexed.append((position, header))
    indexed.sort()

    result: dict[str, str] = {}
    for i, (start, header) in enumerate(indexed):
        marker = f"{header}:"
        value_start = start + len(marker)
        value_end = indexed[i + 1][0] if i + 1 < len(indexed) else len(content)
        value = content[value_start:value_end].strip()
        if value.endswith(","):
            value = value[:-1].rstrip()
        result[header] = value
    return result


def _normalize_header(header: str) -> str:
    return (header or "").strip()


def _compose_statement(variable: str, column: str, value: str) -> str:
    variable = variable.strip() or "Attribute"
    column = column.strip().lower()
    # Trim very long values for the statement; full value is preserved in the quote.
    short_value = value if len(value) <= 200 else value[:197] + "..."
    return f"{column.capitalize()} value for {variable}: {short_value}"


def _build_locator(block: ContentBlock, column_name: str, cell_value: str) -> dict:
    locator: dict = {
        "quote": cell_value,
        "block_id": block.id,
        "row_content": block.content,
    }
    if block.structural_meta.get("page") is not None:
        locator["page"] = block.structural_meta["page"]
    if block.structural_meta.get("table_index") is not None:
        locator["table_index"] = block.structural_meta["table_index"]
    if block.structural_meta.get("row_index") is not None:
        locator["row_index"] = block.structural_meta["row_index"]
    locator["target_column"] = column_name
    return locator
