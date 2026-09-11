"""Translate parser-authored extraction facts for model-facing source readers.

Shared by assessment and Ask. No consumer diagnoses file quality from its text.
"""

from typing import Any

EXTRACTION_WARNINGS = {
    "pdf_limited_structure": (
        "PDF page text and directly placed embedded raster images. Vector drawings "
        "and images nested in Form objects are not read; "
        "columns and tables may be misordered. Images follow page text, not reading "
        "order, and may be fragments. Citations do not establish a reconstructed page."
    ),
}


def extraction_context(metadata: dict[str, Any], *, include_page: bool = True) -> str:
    parts = []
    page = metadata.get("page")
    if include_page and type(page) is int and page > 0:
        parts.append(f"page={page}")
    warnings = metadata.get("extraction_warnings")
    if isinstance(warnings, list):
        for code in dict.fromkeys(code for code in warnings if isinstance(code, str)):
            description = EXTRACTION_WARNINGS.get(code, "Parser-reported extraction limitation.")
            parts.append(f"{code}: {description}")
    return "; ".join(parts)
