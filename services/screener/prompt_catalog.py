"""One declaration per model prompt Screener sends, for publication and testing.

Each stage owns its prompt text. Selection reads one question/document pair;
assessment judges that question against the combined selected source blocks.
This module publishes both prompts and the public fields assessment produces.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .stages.assessor import build_assessment_prompt
from .stages.selector import build_selection_prompt

TOOL = "screener"


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="selector.evidence",
        stage="select",
        title="Question evidence selection",
        builder_name="build_selection_prompt",
        render=build_selection_prompt,
        framing_slot=None,
        result_fields=(),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="assessor.question",
        stage="triage",
        title="Gate question triage",
        builder_name="build_assessment_prompt",
        render=build_assessment_prompt,
        # Screener has no framing slot. The bank supplies each question's whole text,
        # so there is nothing for a configuration to interpolate.
        framing_slot=None,
        result_fields=(
            "disciplines[].questions[].state",
            "disciplines[].questions[].cited_block_ids",
            "disciplines[].questions[].missing",
            "disciplines[].questions[].statement",
        ),
        ui_labels=("answered", "partly_answered", "not_found"),
    ),
)
