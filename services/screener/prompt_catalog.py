"""One declaration per model prompt Screener sends, for publication and testing.

The assessor owns its prompt text. This module owns the list of prompts and what
each produces.

Screener sends one prompt, once per queued question, so this single pair is the
complete set. Every question uses the same document-only prompt.
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
