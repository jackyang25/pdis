"""One declaration per model prompt Archivist sends, for publication and testing.

Archivist sends two prompts, and they are catalogued separately because they answer
different questions from different inputs: one reads a document, and one files a value
that reading produced.

The extraction prompt is published in two pieces because it is sent in two pieces. The
reading rules are constant across every attribute and every document - that is what makes
the eight calls for one document share a cached prefix - while the attribute's definition
and its fence arrive at the end of the user message. Publishing only the constant half
would understate what the model is told, and publishing them merged would misdescribe how
they are sent.

`vaccine.shelf_life` is the attribute rendered for publication. It is the representative
case rather than an arbitrary one: it declares a quantity and three sibling attributes it
must not absorb, so the rendered prompt shows every part of the fence a reader needs to
understand. Its own words come from the shared vocabulary, so the published text is the
vocabulary's, not a paraphrase of it.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry
from shared.vocabulary import attribute_definitions

from .indexed_attributes import indexed_attribute, tag_vocabulary
from .stages.classifier import build_system_prompt as build_classifier_prompt
from .stages.extractor import build_attribute_instructions, build_system_prompt

TOOL = "archivist"

#: The attribute rendered for publication; see the module docstring.
REFERENCE_CLASS = "vaccine"
REFERENCE_ATTRIBUTE = "vaccine.shelf_life"
REFERENCE_FILTERABLE = "vaccine.target_population"


def _definitions() -> dict:
    return {
        definition.name: definition
        for definition in attribute_definitions(REFERENCE_CLASS)
    }


def _render_attribute_instructions() -> str:
    return build_attribute_instructions(
        indexed_attribute(REFERENCE_CLASS, REFERENCE_ATTRIBUTE), _definitions()
    )


def _render_classifier() -> str:
    return build_classifier_prompt(
        REFERENCE_FILTERABLE,
        _definitions()[REFERENCE_FILTERABLE].description,
        tag_vocabulary(REFERENCE_CLASS, REFERENCE_FILTERABLE),
    )


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="extractor.rules",
        stage="extraction-rules",
        title="Attribute reading rules",
        builder_name="build_system_prompt",
        render=build_system_prompt,
        # Archivist has no framing slot. What varies per reading is an attribute's own
        # definition from the shared vocabulary, which is published as the prompt below
        # rather than interpolated from a tool configuration.
        framing_slot=None,
        result_fields=(
            "records[].status",
            "records[].bound",
            "records[].stated",
            "records[].quote",
            "records[].condition_stated",
        ),
        ui_labels=("Stated", "Not stated", "Uncertain", "Minimum", "Optimal"),
    ),
    CatalogEntry(
        tool=TOOL,
        id="extractor.attribute",
        stage="extraction-attribute",
        title="Which attribute to read",
        builder_name="build_attribute_instructions",
        render=_render_attribute_instructions,
        framing_slot=None,
        result_fields=("records[].attribute",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="classifier.tags",
        stage="classification",
        title="Filing a value under its categories",
        builder_name="build_system_prompt",
        render=_render_classifier,
        framing_slot=None,
        result_fields=("records[].tags",),
        ui_labels=("Population", "Delivery"),
    ),
)
