"""One declaration per model prompt Aligner sends, for publication and testing.

Stage modules own their prompt text. This module owns the list of prompts and
how to render each one. Aligner's instructions carry its closed vocabularies
verbatim from `configs/alignment.yaml`, so a published prompt shows the exact
unit types and relations the model is allowed to choose.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .models import load_config
from .stages.extractor import build_extraction_prompt
from .stages.linker import build_alignment_prompt

TOOL = "aligner"

# Aligner has one source-type-neutral configuration, so the published prompts use
# the real vocabularies and leave only the per-run document role as a slot.
_CONFIG = load_config()

PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="extractor.extract",
        stage="extractor",
        title="Traceable unit extraction",
        builder_name="build_extraction_prompt",
        render=lambda: build_extraction_prompt(
            source_type="{source_type}",
            document_role="{document_role}",
            config=_CONFIG,
        ),
        framing_slot="document_roles",
        result_fields=("units",),
        ui_labels=("unit_type",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="linker.align",
        stage="linker",
        title="Cross-document relation",
        builder_name="build_alignment_prompt",
        render=lambda: build_alignment_prompt(_CONFIG),
        framing_slot=None,
        result_fields=("links", "stats"),
        ui_labels=("relation",),
    ),
)
