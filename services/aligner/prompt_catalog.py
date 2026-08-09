"""One declaration per model prompt Aligner sends, for publication and testing.

Two prompts, in the order a run uses them: read one document's requirements, then judge
each of them against the other document. The stages own their prompt text; this module
owns the list and what each one produces.

Neither prompt names a document type or a direction, and neither declares a framing
slot: the role description and the comparison's question come from
`configs/alignment.yaml` and travel in the user message, per requirement. So the text
published here is the whole of what every edge is told, and adding a comparison never
edits a prompt.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .stages.assessor import build_assessment_prompt
from .stages.requirements import build_requirements_prompt

TOOL = "aligner"


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="requirements.extract",
        stage="requirements",
        title="Reference document requirements",
        builder_name="build_requirements_prompt",
        render=build_requirements_prompt,
        # No framing slot, for the reason Expert has none: the comparison's question
        # and the document's role description reach the model in the user message, per
        # requirement, not interpolated into this prompt. The system prompt is the same
        # text for every edge, which is what a reader of the reference is being shown.
        framing_slot=None,
        result_fields=(
            "findings[].requirement",
            "findings[].reference_block_ids",
        ),
        ui_labels=("requirement",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="assessor.requirement",
        stage="compare",
        title="Requirement verdict",
        builder_name="build_assessment_prompt",
        render=build_assessment_prompt,
        framing_slot=None,
        result_fields=(
            "findings[].verdict",
            "findings[].statement",
            "findings[].gap",
            "findings[].comparison_block_ids",
        ),
        ui_labels=("meets", "exceeds", "falls short", "not comparable", "not addressed"),
    ),
)
