"""Translate parser-authored extraction facts for model-facing source readers.

Shared by assessment and Ask. No consumer diagnoses file quality from its text.
"""

import json
from pathlib import Path
from typing import Any

EXTRACTION_WARNINGS: dict[str, str] = json.loads(
    Path(__file__).with_name("document-extraction.json").read_text(encoding="utf-8")
)


def extraction_context(metadata: dict[str, Any], *, include_page: bool = True) -> str:
    parts = []
    page = metadata.get("page")
    if include_page and type(page) is int and page > 0:
        parts.append(f"page={page}")
    slide = metadata.get("slide")
    if type(slide) is int and slide > 0:
        parts.append(f"slide={slide}")
    scope = metadata.get("visual_scope")
    if isinstance(scope, str) and scope in {"full_slide", "full_page"}:
        parts.append(f"visual_scope={scope}; overview of the same source, not independent evidence")
    part = metadata.get("document_part")
    if isinstance(part, str) and part:
        parts.append(f"document_part={part}")
    part_kind = metadata.get("document_part_kind")
    if isinstance(part_kind, str) and part_kind:
        parts.append(f"document_part_kind={part_kind}")
    note_id = metadata.get("note_id")
    if isinstance(note_id, (str, int)) and not isinstance(note_id, bool):
        parts.append(f"note_id={note_id}")
    warnings = metadata.get("extraction_warnings")
    visual_kind = metadata.get("unsupported_visual_kind")
    if isinstance(visual_kind, str) and visual_kind in {"drawing", "chart", "diagram", "embedded_object"}:
        parts.append(f"unsupported_visual_kind={visual_kind}")
    if isinstance(warnings, list):
        for code in dict.fromkeys(code for code in warnings if isinstance(code, str)):
            description = EXTRACTION_WARNINGS.get(code, "Parser-reported extraction limitation.")
            parts.append(f"{code}: {description}")
    return "; ".join(parts)
