"""One declaration per model prompt Screener sends, for publication and testing.

The assessor owns its prompt text. This module owns the list of prompts and what
each produces.

Screener sends one prompt, once per queued question, so this single pair is the
complete set. It is rendered with context available, because that variant is the
larger one — it carries the extra decision and the preference rule — and publishing
the smaller variant would understate what the model is told.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .stages.assessor import build_assessment_prompt

TOOL = "screener"


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="assessor.question",
        stage="triage",
        title="Gate question triage",
        builder_name="build_assessment_prompt",
        render=lambda: build_assessment_prompt(True),
        # Screener has no framing slot. The bank supplies each question's whole text,
        # so there is nothing for a configuration to interpolate.
        framing_slot=None,
        result_fields=(
            "disciplines[].questions[].state",
            "disciplines[].questions[].source",
            "disciplines[].questions[].statement",
        ),
        ui_labels=("answered", "absent"),
    ),
)
