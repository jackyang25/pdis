"""One declaration per model prompt Chunker sends, for publication and testing.

Chunker sends a single prompt: it assigns each parsed block to one section of the
configured taxonomy. The taxonomy itself is domain content, so the published
prompt shows the section names as a slot rather than one document type's list.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .models import DocumentTypeConfig
from .stages.mapper import build_prompts

TOOL = "chunker"

PLACEHOLDER_CONFIG = DocumentTypeConfig(
    type_key="{type_key}",
    org="{org}",
    source_type="{source_type}",
    intervention_class="{intervention_class}",
    display_name="{display_name}",
    preamble="{preamble}",
    section_taxonomy=[
        {"name": "{section_name}", "description": "{section_description}"}
    ],
    disambiguation=["{disambiguation_rule}"],
)

PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="mapper.label",
        stage="mapper",
        title="Section assignment",
        builder_name="build_prompts",
        render=lambda: build_prompts([], PLACEHOLDER_CONFIG)[0],
        framing_slot="preamble",
        result_fields=("blocks[].section_label",),
        ui_labels=(),
    ),
)
