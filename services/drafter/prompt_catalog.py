"""One declaration per model prompt Drafter sends, for publication and testing.

Each stage owns its prompt text. The search plan is the one prompt with configured text in
it - each product type's search guidance - so it declares that slot and renders it as a
placeholder rather than any one config's words.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .stages.evidence_reader import build_system_prompt as build_evidence_reading_prompt
from .stages.search_planner import build_system_prompt as build_search_plan_prompt
from .stages.suggester import build_system_prompt as build_suggestion_prompt

TOOL = "drafter"


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL, id="search_planner.variable", stage="plan", title="Planning searches",
        builder_name="build_system_prompt", render=lambda: build_search_plan_prompt("{query_guidance}"),
        framing_slot="query_guidance", result_fields=(), ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL, id="evidence_reader.source", stage="evidence", title="Reading evidence",
        builder_name="build_system_prompt", render=build_evidence_reading_prompt, framing_slot=None,
        result_fields=("variables[].observations[]",), ui_labels=("comparable_product", "published_guidance"),
    ),
    CatalogEntry(
        tool=TOOL, id="suggester.variable", stage="suggest", title="Suggesting a target",
        builder_name="build_system_prompt", render=build_suggestion_prompt, framing_slot=None,
        result_fields=("variables[].suggestion",), ui_labels=("range", "statement", "insufficient"),
    ),
)
