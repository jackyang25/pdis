"""One declaration per model prompt Scout sends, for publication and testing.

Stage modules own their prompt text. This module owns nothing but the list of
prompts, how to render each one with placeholder document content, and which
result fields and interface labels each one produces. Rendering lives here so
the snapshot test, the reference generator, and the documentation page share a
single convention instead of maintaining separate accessor maps.

Placeholder fields are written as visible slots (``{field_name}``) so a
published prompt reads as the real assembled instruction with obvious gaps where
a document's own content is interpolated.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

from .models import (
    QUANTITATIVE_SEMANTIC_FIELDS,
    Attribute,
    ComparisonRule,
    NumericExpression,
    QuantitativeFieldLink,
    QuantitativeTarget,
    ScoutTypeConfig,
    SemanticSlot,
)
from .stages import (
    announcement_reader,
    context_validator,
    conformity,
    evidence_reviewer,
    drift_classifier,
    evidence_assessor,
    insight_extractor,
    insight_reconciler,
    precedent_classifier,
    projection_classifier,
    query_extractor,
    scope_resolver,
    target_resolver,
    target_reviewer,
    unit_extractor,
)

INDICATION = "{indication}"
#: The run's stated geography, read from the document. A visible slot for the same reason
#: the others are: the published prompt should show the section a run actually sends.
REGION = "{region}"
# Deliberately one word. This placeholder now passes through `search_term`, which
# de-underscores a tag on its way into prose, so `{intervention_class}` would be
# published as `{intervention class}` and read as a broken placeholder. It matches the
# label a reader sees over the field in the configuration rail.
INTERVENTION_CLASS = "{intervention}"
SOURCE_TYPE = "{source_type}"

PLACEHOLDER_ATTRIBUTE = Attribute(
    name="{field_name}",
    description="{field_description}",
    block_ids=["{block_id}"],
    document_target="{document_target}",
    target_resolved=True,
    target_resolution_reason="{resolution_reason}",
)

PLACEHOLDER_TARGET = QuantitativeTarget(
    expression=NumericExpression(
        kind="bound", unit="{unit}", value=0.0, comparator=">="
    ),
    role="threshold",
    quote="{target_quote}",
    doc_block_ids=["{block_id}"],
    field_links=[
        QuantitativeFieldLink(attribute_ref="{field_name}", relation="defines")
    ],
    semantic_profile={
        "measure": SemanticSlot(state="specified", value="{measure}"),
    },
    comparison_contract={
        name: (
            ComparisonRule(mode="exact", scope="{measure}")
            if name == "measure"
            else ComparisonRule(mode="unknown", reason="{comparison_reason}")
        )
        for name in QUANTITATIVE_SEMANTIC_FIELDS
    },
)

PLACEHOLDER_CONFIG = ScoutTypeConfig(
    type_key="{type_key}",
    org="{org}",
    source_type=SOURCE_TYPE,
    intervention_class=INTERVENTION_CLASS,
    display_name="{display_name}",
    query_extraction_guidance="{query_extraction_guidance}",
    sources=["{source_key}"],
)


TOOL = "scout"

PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        tool=TOOL,
        id="context_validator.validate",
        stage="context_validator",
        title="Configured indication check",
        builder_name="build_system_prompt",
        render=lambda: context_validator.build_system_prompt(INDICATION),
        framing_slot=None,
        result_fields=("context_validation.status",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="announcement_reader.read",
        stage="announcement_reader",
        title="Program named in an announcement",
        builder_name="build_system_prompt",
        render=lambda: announcement_reader.build_system_prompt(),
        framing_slot=None,
        result_fields=("development_landscape[].record_types",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="scope_resolver.run_scope",
        stage="scope_resolver",
        title="Run geography from the document",
        builder_name="build_system_prompt",
        render=lambda: scope_resolver.build_system_prompt("region"),
        framing_slot=None,
        result_fields=("retrieval_scope.region",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="unit_extractor.extract",
        stage="unit_extractor",
        title="Document claim extraction",
        builder_name="build_system_prompt",
        render=lambda: unit_extractor.build_system_prompt(
            INTERVENTION_CLASS, SOURCE_TYPE, INDICATION
        ),
        framing_slot=None,
        result_fields=("variables[].name", "variables[].description"),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="target_resolver.ledger",
        stage="target_resolver",
        title="Canonical claim resolution",
        builder_name="build_ledger_system_prompt",
        render=lambda: target_resolver.build_ledger_system_prompt(
            [PLACEHOLDER_ATTRIBUTE], [PLACEHOLDER_ATTRIBUTE]
        ),
        framing_slot=None,
        result_fields=("variables[].document_target", "variables[].document_spans"),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="conformity.document_ledger",
        stage="conformity",
        title="Quantitative target mapping",
        builder_name="build_document_ledger_system_prompt",
        render=lambda: conformity.build_document_ledger_system_prompt(
            [PLACEHOLDER_ATTRIBUTE],
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
            framing="{quantitative_target_framing}",
        ),
        framing_slot="quantitative_target_framing",
        result_fields=("quantitative_ledger.targets[]",),
        ui_labels=("alignment",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="conformity.measurement",
        stage="conformity",
        title="External measurement mapping",
        builder_name="build_measurement_system_prompt",
        render=lambda: conformity.build_measurement_system_prompt(
            (PLACEHOLDER_ATTRIBUTE,),
            target=PLACEHOLDER_TARGET,
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
        ),
        framing_slot=None,
        result_fields=("conformity[].measurements[]",),
        ui_labels=("alignment",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="query_extractor.general",
        stage="query_extractor",
        title="General query planning",
        builder_name="build_system_prompt_for_variable",
        render=lambda: query_extractor.build_system_prompt_for_variable(
            PLACEHOLDER_CONFIG,
            indication=INDICATION,
            attribute=PLACEHOLDER_ATTRIBUTE,
            quantitative_targets=[PLACEHOLDER_TARGET],
            queries_per_variable=1,
        ),
        # This builder inserts it; the other three query-extractor builders do not.
        framing_slot="query_extraction_guidance",
        result_fields=("stats.queries",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="query_extractor.geographic",
        stage="query_extractor",
        title="Geographic query planning",
        builder_name="build_system_prompt_for_geographic_variable",
        render=lambda: query_extractor.build_system_prompt_for_geographic_variable(
            PLACEHOLDER_CONFIG,
            indication=INDICATION,
            attribute=PLACEHOLDER_ATTRIBUTE,
            geographic_queries_per_variable=1,
            region=REGION,
        ),
        framing_slot=None,
        result_fields=("stats.queries",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="query_extractor.counterfactual",
        stage="query_extractor",
        title="Counterfactual query planning",
        builder_name="build_system_prompt_for_counterfactual_variable",
        render=lambda: query_extractor.build_system_prompt_for_counterfactual_variable(
            PLACEHOLDER_CONFIG,
            indication=INDICATION,
            attribute=PLACEHOLDER_ATTRIBUTE,
            counterfactual_queries_per_variable=1,
        ),
        framing_slot=None,
        result_fields=("stats.queries",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="query_extractor.precedent",
        stage="query_extractor",
        title="Precedent query planning",
        builder_name="build_system_prompt_for_precedent_variable",
        render=lambda: query_extractor.build_system_prompt_for_precedent_variable(
            PLACEHOLDER_CONFIG,
            indication=INDICATION,
            attribute=PLACEHOLDER_ATTRIBUTE,
            precedent_queries_per_variable=1,
        ),
        framing_slot=None,
        result_fields=("stats.queries",),
        ui_labels=("precedent",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="query_extractor.adjacent",
        stage="query_extractor",
        title="Adjacent query planning",
        builder_name="build_system_prompt_for_adjacent_variable",
        render=lambda: query_extractor.build_system_prompt_for_adjacent_variable(
            PLACEHOLDER_CONFIG,
            indication=INDICATION,
            attribute=PLACEHOLDER_ATTRIBUTE,
            adjacent_queries_per_variable=1,
        ),
        framing_slot=None,
        result_fields=("stats.queries",),
        ui_labels=("precedent",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="insight_extractor.extract",
        stage="insight_extractor",
        title="Source insight extraction",
        builder_name="build_system_prompt",
        render=lambda: insight_extractor.build_system_prompt(
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
            attribute_ref=PLACEHOLDER_ATTRIBUTE.name,
            attribute_description=PLACEHOLDER_ATTRIBUTE.description,
        ),
        framing_slot=None,
        result_fields=("matches[].insight",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="insight_reconciler.reconcile",
        stage="insight_reconciler",
        title="Source insight identity reconciliation",
        builder_name="build_reconciliation_system_prompt",
        render=insight_reconciler.build_reconciliation_system_prompt,
        framing_slot=None,
        result_fields=("matches[].insight",),
        ui_labels=(),
    ),
    CatalogEntry(
        tool=TOOL,
        id="drift_classifier.classify",
        stage="drift_classifier",
        title="Evidence relationship classification",
        builder_name="build_system_prompt",
        render=lambda: drift_classifier.build_system_prompt(
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
            framing="{drift_framing}",
        ),
        framing_slot="drift_framing",
        result_fields=("matches[].relation",),
        ui_labels=("relationships",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="evidence_assessor.assess",
        stage="evidence_assessor",
        title="Grounding assessment",
        builder_name="build_system_prompt",
        render=lambda: evidence_assessor.build_system_prompt(
            attribute=PLACEHOLDER_ATTRIBUTE,
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
            framing="{evidence_framing}",
        ),
        framing_slot="evidence_framing",
        result_fields=("assessments[].strength",),
        ui_labels=("grounding",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="precedent_classifier.classify",
        stage="precedent_classifier",
        title="Precedent coverage and outcome",
        builder_name="build_system_prompt",
        render=lambda: precedent_classifier.build_system_prompt(
            attribute=PLACEHOLDER_ATTRIBUTE,
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
            framing="{precedent_framing}",
        ),
        framing_slot="precedent_framing",
        result_fields=("precedents[].precedent", "precedents[].outcome"),
        ui_labels=("precedent",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="conformity.reconciliation",
        stage="conformity",
        title="Document-wide claim reconciliation",
        builder_name="build_reconciliation_system_prompt",
        render=conformity.build_reconciliation_system_prompt,
        framing_slot=None,
        result_fields=("quantitative_ledger.targets[].id",),
        ui_labels=("alignment",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="target_reviewer.prefill",
        stage="target_reviewer",
        title="Numeric target review recommendation",
        builder_name="build_review_system_prompt",
        render=target_reviewer.build_review_system_prompt,
        framing_slot=None,
        result_fields=("quantitative_ledger.targets[].ai_recommendation",),
        ui_labels=("alignment",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="evidence_reviewer.prefill",
        stage="evidence_reviewer",
        title="Measurement admission recommendation",
        builder_name="build_review_system_prompt",
        render=evidence_reviewer.build_review_system_prompt,
        framing_slot=None,
        result_fields=("quantitative_ledger.reviews[].ai_recommendation",),
        ui_labels=("alignment",),
    ),
    CatalogEntry(
        tool=TOOL,
        id="projection_classifier.classify",
        stage="projection_classifier",
        title="Projection role classification",
        builder_name="build_system_prompt",
        render=lambda: projection_classifier.build_system_prompt(
            indication=INDICATION,
            intervention_class=INTERVENTION_CLASS,
        ),
        framing_slot=None,
        result_fields=("development_landscape[].role",),
        ui_labels=(),
    ),
)
