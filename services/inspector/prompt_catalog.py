"""One declaration per model prompt Inspector sends, for publication and testing.

The assessor owns its prompt text. This module owns the list of prompts, how to
render each against a placeholder rubric, and which result fields each produces.

Inspector sends one prompt per rubric unit and one for the whole document, so the
published pair is the complete set. It was four - one per dimension plus
consistency - and merging the dimensions merged their prompts with them.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .models import InspectionConfig, SectionSpec, VariableSpec
from .stages.assessor import build_assessment_prompt, build_cross_section_prompt

TOOL = "inspector"

PLACEHOLDER_VARIABLE = VariableSpec(
    name="{variable_name}",
    description="{variable_description}",
    expectations="{variable_expectations}",
)

PLACEHOLDER_SECTION = SectionSpec(
    name="{section_name}",
    description="{section_description}",
    expectations="{section_expectations}",
    variables=[PLACEHOLDER_VARIABLE],
)

PLACEHOLDER_CONFIG = InspectionConfig(
    type_key="{type_key}",
    org="{org}",
    source_type="{source_type}",
    intervention_class="{intervention_class}",
    display_name="{display_name}",
    sections=[PLACEHOLDER_SECTION],
    stage_guidance="{stage_guidance}",
)


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="assessor.unit",
        stage="assessment",
        title="Rubric unit assessment",
        builder_name="build_assessment_prompt",
        render=lambda: build_assessment_prompt(
            PLACEHOLDER_SECTION,
            PLACEHOLDER_VARIABLE,
            PLACEHOLDER_CONFIG.stage_guidance,
        ),
        framing_slot="stage_guidance",
        result_fields=(
            "sections[].units[].findings[]",
            "sections[].units[].status",
        ),
        ui_labels=("finding", "status"),
    ),
    CatalogEntry(
        tool=TOOL,
        id="assessor.cross_section",
        stage="consistency",
        title="Cross-section consistency check",
        builder_name="build_cross_section_prompt",
        render=lambda: build_cross_section_prompt(PLACEHOLDER_CONFIG),
        framing_slot=None,
        result_fields=("document_findings[]", "consistency_status"),
        ui_labels=("consistency",),
    ),
)
