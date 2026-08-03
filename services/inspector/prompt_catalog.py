"""One declaration per model prompt Inspector sends, for publication and testing.

The grader owns its prompt text. This module owns the list of prompts, how to
render each one against a placeholder rubric, and which result fields and
interface labels each one produces.

Inspector sends one prompt per dimension per rubric variable, so the three
published dimension prompts are the real assembled instructions with the rubric's
own content shown as slots.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .models import DIMENSIONS, InspectionConfig, SectionSpec, VariableSpec
from .stages.grader import build_cross_section_prompt, build_dimension_prompt

TOOL = "inspector"

PLACEHOLDER_SECTION = SectionSpec(
    name="{section_name}",
    description="{section_description}",
    weight=1.0,
    variables=[
        VariableSpec(
            name="{variable_name}",
            description="{variable_description}",
        )
    ],
)

PLACEHOLDER_CONFIG = InspectionConfig(
    type_key="{type_key}",
    org="{org}",
    source_type="{source_type}",
    intervention_class="{intervention_class}",
    display_name="{display_name}",
    sections=[PLACEHOLDER_SECTION],
    grading_guidance="{grading_guidance}",
)

_DIMENSION_TITLE = {
    "completeness": "Completeness grading",
    "adherence": "Template adherence grading",
    "rigor": "Rigor grading",
}

_DIMENSION_RESULT_FIELDS = {
    "completeness": (
        "section_grades[].variable_grades[].dimensions.completeness",
        "section_grades[].variable_grades[].content_status",
    ),
    "adherence": ("section_grades[].variable_grades[].dimensions.adherence",),
    "rigor": ("section_grades[].variable_grades[].dimensions.rigor",),
}

# Completeness owns the presence decision, so it is the prompt behind the
# presence vocabulary as well as its own grade.
_DIMENSION_UI_LABELS = {
    "completeness": ("completeness", "presence"),
    "adherence": ("adherence",),
    "rigor": ("rigor",),
}


def _dimension_entry(dimension: str) -> CatalogEntry:
    return CatalogEntry(
        tool=TOOL,
        id=f"grader.{dimension}",
        stage=dimension,
        title=_DIMENSION_TITLE[dimension],
        builder_name="build_dimension_prompt",
        render=lambda dimension=dimension: build_dimension_prompt(
            dimension, PLACEHOLDER_SECTION, PLACEHOLDER_CONFIG.grading_guidance
        ),
        framing_slot="grading_guidance",
        result_fields=_DIMENSION_RESULT_FIELDS[dimension],
        ui_labels=_DIMENSION_UI_LABELS[dimension],
    )


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    *(_dimension_entry(dimension) for dimension in DIMENSIONS),
    CatalogEntry(
        tool=TOOL,
        id="grader.cross_section",
        stage="consistency",
        title="Cross-section consistency check",
        builder_name="build_cross_section_prompt",
        render=lambda: build_cross_section_prompt(PLACEHOLDER_CONFIG),
        framing_slot=None,
        result_fields=("cross_section_findings", "consistency_status"),
        ui_labels=("consistency",),
    ),
)
