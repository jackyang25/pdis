"""Pydantic response models for the API.

These mirror the dataclasses in services/, but expose only what the
frontend needs. Keep them lean and explicit — Pydantic schemas are the
wire contract.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DocumentType(BaseModel):
    key: str  # "{org}_{source_type}_{intervention}"
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    supports: dict[str, bool]  # Native tool availability discovered by the UI.


class DocumentTypesResponse(BaseModel):
    document_types: list[DocumentType]


class IndicationsResponse(BaseModel):
    indications: list[str]


class ImageAssetOut(BaseModel):
    media_type: str
    data_base64: str
    sha256: str
    source_media_type: str


class ContentBlockOut(BaseModel):
    id: str
    doc_id: str
    ordinal: int
    block_type: str
    content: str
    heading_stack: list[str]
    section_label: str | None = None
    # Parser provenance, surfaced for debugging/inspection: structural_meta holds
    # paragraph/table/row index, page, column headers, image index; style_hint
    # holds the source style name, bold flag, and parser source tag.
    structural_meta: dict[str, Any] = Field(default_factory=dict)
    style_hint: dict[str, Any] = Field(default_factory=dict)
    image: ImageAssetOut | None = None
    # Document provenance stamped by each pipeline. Present on the service block, so
    # the wire shape carries it too: a round trip through this model must not
    # silently discard fields a caller supplied or a service produced.
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None


class ChunkerRunResponse(BaseModel):
    doc_id: str
    blocks: list[ContentBlockOut]


class RetrievalPathOut(BaseModel):
    query: str
    lane: str
    connector: str = ""
    operation: str = ""


class SourceAttributionOut(BaseModel):
    label: str
    url: str
    prefix: str = "Source data provided by"


class DevelopmentRecordOut(BaseModel):
    program_name: str
    # Every member of `DEVELOPMENT_RECORD_TYPES`. `announcement` was added to the domain and
    # this list did not follow, so any run whose announcement reader produced a record failed
    # at the response boundary after the whole analysis had succeeded.
    # `test_api_schema_vocabulary.py` compares the two.
    record_type: Literal[
        "clinical_trial",
        "compound_catalog",
        "regulatory_label",
        "regulatory_clearance",
        "announcement",
    ]
    record_id: str = ""
    sponsor: str = ""
    phase: str = ""
    status: str = ""
    source_role: Literal[
        "experimental", "comparator", "control", "co_intervention", "unknown"
    ] = "unknown"


class IndicatorRecordOut(BaseModel):
    indicator_code: str
    indicator_name: str
    place: str
    spatial_type: str
    year: int
    value: float | None = None
    value_text: str = ""
    parent_place: str = ""


class SafetyObservationRecordOut(BaseModel):
    product_name: str
    record_type: Literal["label_warning", "reported_event", "device_event", "recall"]
    source_system: Literal["fda_label", "faers", "maude", "fda_recall"]
    label: str
    detail: str = ""
    report_count: int | None = None
    qualification: str = ""
    source_role: Literal[
        "experimental", "comparator", "control", "co_intervention", "unknown"
    ] = "unknown"


class FindingOut(BaseModel):
    url: str
    title: str
    query: str
    retrieved_at: str
    excerpt: str | None = None
    published_at: str | None = None
    source: str = "unknown"
    evidence_role: Literal["evidence", "reference"] = "evidence"
    development_records: list[DevelopmentRecordOut] = Field(default_factory=list)
    safety_observations: list[SafetyObservationRecordOut] = Field(default_factory=list)
    indicator_records: list[IndicatorRecordOut] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    source_lanes: list[str] = Field(default_factory=list)
    source_labels: dict[str, str] = Field(default_factory=dict)
    source_attributions: dict[str, SourceAttributionOut] = Field(default_factory=dict)
    retrieval_paths: list[RetrievalPathOut] = Field(default_factory=list)
    title_source_lane: str = ""
    excerpt_source_lane: str = ""
    published_source_lane: str = ""


class SearchLaneOut(BaseModel):
    """One native request a lane made, so absence can be read for what it was."""

    source: str
    #: The query the provider actually received, not the text the reader typed.
    query: str
    status: Literal["complete", "failed", "skipped"] = "complete"
    #: Why this lane produced nothing: an adapter failure, or the planner's reason for
    #: ruling the lane out before it ran.
    detail: str = ""
    #: What this request returned, before cross-lane deduplication.
    returned: int = 0


class SearcherRunResponse(BaseModel):
    query: str
    findings: list[FindingOut]
    #: Every request every selected lane made. A lane returning nothing appears here
    #: with `returned: 0`; it cannot appear in `findings` at all, which is why a run
    #: that reported only findings could not distinguish a true null from a failure.
    lanes: list[SearchLaneOut] = Field(default_factory=list)


class SearchSourceOut(BaseModel):
    key: str
    label: str
    default_enabled: bool
    configured: bool = True
    attribution: SourceAttributionOut | None = None
    evidence_domains: list[str] = Field(default_factory=list)
    required_entity_types: list[str] = Field(default_factory=list)
    #: What this lane is responsible for and whose setting it describes. Published so a
    #: client groups by the lane's own declaration instead of keeping a second table
    #: that drifts the moment a lane is added.
    evidence_class: str = "general"
    jurisdiction: str = "global"
    #: Scope dimensions this lane can act on. Published so a client can say which of
    #: its inputs a given lane will actually use, rather than implying all of them.
    reads: list[str] = Field(default_factory=list)
    #: Whether the lane can bound results by date at the provider. A client showing a
    #: date control needs to say which lanes it actually narrows.
    honors_date_bound: bool = False


class InsightOut(BaseModel):
    id: str = ""
    statement: str
    query: str
    query_tracks: list[str] = Field(default_factory=list)
    retrieval_target_ids: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut]
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    attribute_ref: str | None = None


class MatchOut(BaseModel):
    insight: InsightOut
    relation: Literal["contradicts", "extends", "confirms", "unrelated"]
    reason: str
    doc_block_ids: list[str] = Field(default_factory=list)


class EvidenceAssessmentOut(BaseModel):
    attribute_ref: str
    strength: Literal["well_grounded", "partial", "thin", "unsupported", "unknown"]
    reason: str
    doc_target: str = ""
    doc_block_ids: list[str] = Field(default_factory=list)
    supporting_insight_ids: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut]


class FunnelStatsOut(BaseModel):
    queries: int
    findings: int
    unique_findings: int
    insights: int
    matches: int
    assessments: int


class SearchTraceOut(BaseModel):
    attribute_ref: str
    lane: str
    query: str
    connector: str = ""
    operation: str = ""
    request_options: dict[str, str] = Field(default_factory=dict)
    tracks: list[str] = Field(default_factory=list)
    doc_block_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    intent_ids: list[str] = Field(default_factory=list)
    input_queries: list[str] = Field(default_factory=list)
    applicability: Literal["applicable", "not_applicable"] = "applicable"
    applicability_reason: str = ""
    status: Literal["complete", "failed", "skipped"] = "complete"
    error: str = ""
    finding_count: int = 0
    source_urls: list[str] = Field(default_factory=list)
    # A subset of source_urls: retrieved, then held out because the source dated
    # them before the requested window. Undated findings are never listed here.
    excluded_before_window: list[str] = Field(default_factory=list)


class EvidenceEntityOut(BaseModel):
    name: str
    entity_type: str
    identifier: str = ""


class SemanticSlotOut(BaseModel):
    state: Literal["specified", "not_specified", "unknown", "other"]
    value: str = ""
    other: str = ""

    @model_validator(mode="after")
    def validate_state_payload(self) -> "SemanticSlotOut":
        if self.state == "specified" and not self.value.strip():
            raise ValueError("specified semantic slot requires a value")
        if self.state == "specified" and self.other.strip():
            raise ValueError("specified semantic slot cannot carry other text")
        if self.state == "other" and not self.other.strip():
            raise ValueError("other semantic slot requires an explanation")
        if self.state == "other" and self.value.strip():
            raise ValueError("other semantic slot cannot carry a specified value")
        if self.state not in {"specified", "other"} and (self.value or self.other):
            raise ValueError("absent or unknown semantic slots cannot carry values")
        return self


class QuantitativeSemanticProfileOut(BaseModel):
    """The one shared semantic shape for document targets and source values."""

    measure: SemanticSlotOut
    endpoint: SemanticSlotOut
    intervention: SemanticSlotOut
    population: SemanticSlotOut
    regimen: SemanticSlotOut
    time_horizon: SemanticSlotOut
    statistic: SemanticSlotOut
    conditions: SemanticSlotOut

    @model_validator(mode="after")
    def validate_measure(self) -> "QuantitativeSemanticProfileOut":
        if self.measure.state != "specified":
            raise ValueError("quantitative semantic profile requires a specified measure")
        return self


class DocumentSpanOut(BaseModel):
    quote: str = Field(min_length=1)
    block_ids: list[str] = Field(min_length=1)


class NumericExpressionOut(BaseModel):
    kind: Literal[
        "point_estimate", "range", "bound", "confidence_interval", "count",
        "rate", "other", "unknown",
    ]
    unit: str = ""
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    comparator: Literal["", "=", ">", ">=", "<", "<="] = ""

    @model_validator(mode="after")
    def validate_expression(self) -> "NumericExpressionOut":
        if self.kind not in {"other", "unknown"} and not self.unit:
            raise ValueError("numeric expression requires a unit")
        if self.kind in {"point_estimate", "count", "rate"}:
            if self.value is None or self.comparator:
                raise ValueError(f"{self.kind} requires value and no comparator")
        elif self.kind == "bound":
            if self.value is None or not self.comparator or not self.unit:
                raise ValueError("bound requires value, unit, and comparator")
        elif self.kind in {"range", "confidence_interval"}:
            if (
                self.lower is None
                or self.upper is None
                or self.lower > self.upper
                or self.value is not None
                or self.comparator
            ):
                raise ValueError(f"{self.kind} requires ordered lower and upper values")
        return self


class QuantitativeFieldLinkOut(BaseModel):
    attribute_ref: str
    relation: Literal["defines", "constrains", "context_for"]
    reason: str = ""


class ComparisonRuleOut(BaseModel):
    mode: Literal["exact", "compatible", "unconstrained", "unknown"]
    scope: str = ""
    reason: str = ""

    @model_validator(mode="after")
    def validate_shape(self) -> "ComparisonRuleOut":
        self.scope = " ".join(self.scope.split())
        self.reason = " ".join(self.reason.split())
        if self.mode in {"exact", "compatible"} and not self.scope:
            raise ValueError(f"{self.mode} comparison rule requires a scope")
        if self.mode == "unconstrained" and self.scope:
            raise ValueError("unconstrained comparison rule cannot carry a scope")
        if self.mode == "unknown" and not self.reason:
            raise ValueError("unknown comparison rule requires a reason")
        return self


class QuantitativeComparisonContractOut(BaseModel):
    measure: ComparisonRuleOut
    endpoint: ComparisonRuleOut
    intervention: ComparisonRuleOut
    population: ComparisonRuleOut
    regimen: ComparisonRuleOut
    time_horizon: ComparisonRuleOut
    statistic: ComparisonRuleOut
    conditions: ComparisonRuleOut

    @model_validator(mode="after")
    def validate_measure(self) -> "QuantitativeComparisonContractOut":
        if self.measure.mode != "exact":
            raise ValueError("quantitative measure comparison must be exact")
        return self


class QuantitativeTargetOut(BaseModel):
    id: str
    expression: NumericExpressionOut
    role: Literal["threshold", "optimal", "other"]
    quote: str
    doc_block_ids: list[str] = Field(default_factory=list)
    field_links: list[QuantitativeFieldLinkOut] = Field(min_length=1)
    semantic_profile: QuantitativeSemanticProfileOut
    comparison_contract: QuantitativeComparisonContractOut
    semantic_provenance: dict[str, list[DocumentSpanOut]]
    provenance_spans: list[DocumentSpanOut] = Field(min_length=1)
    ai_recommendation: Literal["confirm", "exclude", "flag"] = "flag"
    ai_review_reason: str = ""
    review_status: Literal["needs_review", "approved", "rejected"] = "approved"


class QuantitativeStatementDispositionOut(BaseModel):
    quote: str
    block_ids: list[str] = Field(min_length=1)
    disposition: Literal["context_only", "non_scalar", "range_or_set", "uncertain"]
    reason: str
    attribute_refs: list[str] = Field(default_factory=list)


class QuantitativeLedgerReviewOut(BaseModel):
    unit_id: str
    block_id: str
    quote: str
    classification: Literal[
        "target", "partial_target", "context_only", "non_scalar", "range_or_set",
        "non_numeric", "uncertain"
    ]
    reason: str
    attribute_refs: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    review_status: Literal["resolved", "needs_review", "accepted_exclusion"] = "resolved"


class QuantitativeLedgerOut(BaseModel):
    status: Literal["complete", "not_applicable", "uncertain"]
    reason: str = ""
    block_ids: list[str] = Field(default_factory=list)
    reviews: list[QuantitativeLedgerReviewOut] = Field(default_factory=list)
    targets: list[QuantitativeTargetOut] = Field(default_factory=list)


class VariableOut(BaseModel):
    name: str
    description: str
    block_ids: list[str] = Field(default_factory=list)
    document_target: str = ""
    document_spans: list[DocumentSpanOut] = Field(default_factory=list)
    definition_mode: Literal["fixed", "dynamic"] = "fixed"
    target_resolved: bool = False
    target_resolution_reason: str = ""
    evidence_domain: str = "general"
    entities: list[EvidenceEntityOut] = Field(default_factory=list)
    quantitative_target_ids: list[str] = Field(default_factory=list)
    quantitative_statement_dispositions: list[QuantitativeStatementDispositionOut] = Field(
        default_factory=list
    )
    quantitative_target_status: Literal[
        "not_evaluated", "present", "not_applicable", "uncertain"
    ] = "not_evaluated"
    quantitative_target_status_reason: str = ""


class TernaryDecisionOut(BaseModel):
    state: Literal["yes", "no", "unknown"]
    reason: str = ""


class SemanticDimensionAssessmentOut(BaseModel):
    source: SemanticSlotOut
    compatibility: TernaryDecisionOut


class MeasurementSemanticDimensionsOut(BaseModel):
    measure: SemanticDimensionAssessmentOut
    endpoint: SemanticDimensionAssessmentOut
    intervention: SemanticDimensionAssessmentOut
    population: SemanticDimensionAssessmentOut
    regimen: SemanticDimensionAssessmentOut
    time_horizon: SemanticDimensionAssessmentOut
    statistic: SemanticDimensionAssessmentOut
    conditions: SemanticDimensionAssessmentOut


class MeasurementSemanticAssessmentOut(BaseModel):
    source_ownership: TernaryDecisionOut
    dimensions: MeasurementSemanticDimensionsOut


class EvidenceUnitIdentityOut(BaseModel):
    status: Literal["resolved", "record_level", "uncertain"]
    group: SemanticSlotOut
    cohort: SemanticSlotOut
    reason: str


class MeasurementOut(BaseModel):
    expression: NumericExpressionOut
    candidate_id: str = ""
    url: str = ""
    insight_id: str = ""
    source_quote: str = ""
    source_record_id: str = ""
    source_identity_status: Literal["canonical", "title_fallback", "url_fallback"] = "url_fallback"
    evidence_unit_id: str = ""
    evidence_unit: EvidenceUnitIdentityOut
    semantic_assessment: MeasurementSemanticAssessmentOut
    semantic_status: Literal["comparable", "contextual", "incompatible", "unknown"] = "unknown"
    semantic_reason: str = ""
    evidence_mode: Literal["prose", "structured_fact"] = "prose"
    ai_recommendation: Literal["admit", "reject", "flag"] = "flag"
    ai_review_reason: str = ""
    admission_status: Literal[
        "needs_review", "approved", "rejected", "not_eligible", "auto_admitted"
    ] = "needs_review"
    admission_reason: str = ""
    inclusion_reason: str = ""
    exclusion_reasons: list[str] = Field(default_factory=list)
    age_months: float | None = None


class SourcePassageDispositionOut(BaseModel):
    source_id: str
    # The first three are the model's verdict on the source. `not_assessed` is
    # this pipeline reporting that no verdict was obtained, and carries the
    # machine-readable `failure_code`.
    status: Literal[
        "measurements_found",
        "no_relevant_measurement",
        "uncertain",
        "not_assessed",
    ]
    reason: str
    url: str = ""
    insight_id: str = ""
    failure_code: str = ""


class ConformityOut(BaseModel):
    attribute_refs: list[str]
    target_id: str
    target_role: Literal["threshold", "optimal", "other"]
    target_value: float
    comparator: Literal["=", ">", ">=", "<", "<="]
    unit: str = ""
    target_label: str = ""
    target_quote: str = ""
    target_meeting_count: int
    target_meeting_rate: float
    verdict: str
    benchmark_count: int = 0
    benchmark_minimum: float | None = None
    benchmark_maximum: float | None = None
    benchmark_mean: float | None = None
    benchmark_median: float | None = None
    benchmark_lower_quartile: float | None = None
    benchmark_upper_quartile: float | None = None
    benchmark_standard_deviation: float | None = None
    target_percentile: float | None = None
    ambition_percentile: float | None = None
    calibration_status: Literal["insufficient", "limited", "sufficient"] = "insufficient"
    doc_block_ids: list[str] = Field(default_factory=list)
    measurements: list[MeasurementOut] = Field(default_factory=list)
    excluded_measurements: list[MeasurementOut] = Field(default_factory=list)
    source_dispositions: list[SourcePassageDispositionOut] = Field(default_factory=list)


class PrecedentOut(BaseModel):
    attribute_ref: str
    precedent: Literal["direct", "adjacent", "none", "unknown"]
    outcome: Literal["favorable", "mixed", "unfavorable", "unknown"] = "unknown"
    reason: str = ""
    doc_block_ids: list[str] = Field(default_factory=list)
    coverage_insight_ids: list[str] = Field(default_factory=list)
    outcome_insight_ids: list[str] = Field(default_factory=list)
    supporting_insight_ids: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class DevelopmentProgramOut(BaseModel):
    projection_id: str
    name: str
    source_role: Literal[
        "experimental", "comparator", "control", "co_intervention", "unknown"
    ]
    target_relationship: Literal[
        "direct", "analogous", "adjacent", "unrelated", "unknown"
    ]
    target_relationship_reason: str = ""
    sponsors: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    record_types: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    attribute_refs: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class SafetyObservationOut(BaseModel):
    projection_id: str
    product_name: str
    record_type: Literal["label_warning", "reported_event", "device_event", "recall"]
    source_system: Literal["fda_label", "faers", "maude", "fda_recall"]
    label: str
    detail: str = ""
    report_count: int | None = None
    qualification: str = ""
    source_role: Literal[
        "experimental", "comparator", "control", "co_intervention", "unknown"
    ]
    target_relationship: Literal[
        "direct", "analogous", "adjacent", "unrelated", "unknown"
    ]
    target_relationship_reason: str = ""
    attribute_refs: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class IndicatorReadingOut(BaseModel):
    place: str
    spatial_type: str
    year: int
    value: float | None = None
    value_text: str = ""
    parent_place: str = ""


class BurdenIndicatorOut(BaseModel):
    projection_id: str
    indicator_code: str
    indicator_name: str
    readings: list[IndicatorReadingOut] = Field(default_factory=list)
    attribute_refs: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class DocumentContextValidationOut(BaseModel):
    status: Literal["match", "mismatch", "uncertain"]
    configured_indication: str
    document_indication: str = ""
    reason: str = ""
    doc_block_ids: list[str] = Field(default_factory=list)


class ScoutRunResponse(BaseModel):
    phase: Literal["target_review", "evidence_review", "final"] = "final"
    org: str
    source_type: str
    intervention_class: str
    indication: str
    # The retrieval window this run was scoped to, or "" for none. Published on
    # the result because every statistic below describes the cohort it admitted.
    published_since: str = ""
    context_validation: DocumentContextValidationOut
    quantitative_ledger: QuantitativeLedgerOut
    variables: list[VariableOut]
    search_plan: list[SearchTraceOut] = Field(default_factory=list)
    matches: list[MatchOut]
    conformity: list[ConformityOut] = Field(default_factory=list)
    precedents: list[PrecedentOut] = Field(default_factory=list)
    development_landscape: list[DevelopmentProgramOut] = Field(default_factory=list)
    safety_observations: list[SafetyObservationOut] = Field(default_factory=list)
    burden_indicators: list[BurdenIndicatorOut] = Field(default_factory=list)
    assessments: list[EvidenceAssessmentOut]
    stats: FunnelStatsOut
    # The parsed source document. Read by the Ask assistant and by the Scout UI's
    # document-trace view, which renders results against their source blocks.
    blocks: list[ContentBlockOut] = Field(default_factory=list)


class ScoutContinueRequest(BaseModel):
    draft: ScoutRunResponse


class RubricFindingOut(BaseModel):
    """One thing to fix. One statement, one recommendation, one reason."""

    id: str
    reason: Literal[
        "missing", "placeholder", "unmet", "off_template", "unclear", "conflicting"
    ]
    statement: str
    recommendation: str = ""
    # Which unit this is about is read from the names: both set is a variable,
    # section alone is a whole section, neither is the document.
    section_name: str | None = None
    variable_name: str | None = None
    # Where this was read from. Empty exactly when nothing is there.
    cited_block_ids: list[str] = []
    # Worklist position, assigned server-side so every view orders identically.
    rank: int = 0
    # Derived from the reason. Required, not defaulted: a missing derivation must
    # fail here rather than publish a plausible wrong level.
    level: Literal["not_met", "could_be_stronger"]


class UnitAssessmentOut(BaseModel):
    """One rubric unit. `status` is derived from the findings beneath it."""

    variable_name: str | None = None
    optional: bool = False
    findings: list[RubricFindingOut] = []
    # Derived from this unit's findings. Required for the same reason: defaulting it
    # to "met" would report a unit with findings as satisfied.
    status: Literal["met", "could_be_stronger", "not_met", "not_applicable"]


class SectionAssessmentOut(BaseModel):
    """One rubric section, its parse lineage, and the units beneath it."""

    section_name: str
    # A deterministic section assignment, not a citation.
    mapped_block_ids: list[str] = []
    # Derived from that mapping: a section is present exactly when the mapper gave it
    # blocks. Required, so a missed derivation cannot pass for a present section.
    is_present: bool
    units: list[UnitAssessmentOut] = []
    # This section's units counted by status. Bounded by the rubric, and required
    # rather than defaulted so an empty count cannot pass for a clean section.
    status_counts: dict[str, int]


class InspectionResultOut(BaseModel):
    doc_id: str
    # Every rubric section in rubric order, each holding every unit the rubric
    # asks about, so the denominator is identical for every document.
    sections: list[SectionAssessmentOut] = []
    # Conflicts spanning sections, which no single unit can own.
    document_findings: list[RubricFindingOut] = []
    consistency_status: Literal[
        "complete", "partial", "failed", "not_applicable", "unknown"
    ] = "unknown"
    # Whether the run completed. A process fact, kept out of the assessment so
    # "not checked" cannot read as "nothing found".
    assessment_status: Literal["complete", "unknown"] = "unknown"
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    # The parsed source document. Read by the Ask assistant and by the Inspector
    # UI's document view, which renders findings against their source blocks.
    blocks: list[ContentBlockOut] = []


class InspectorRunResponse(BaseModel):
    inspection: InspectionResultOut


class AlignmentDocumentOut(BaseModel):
    doc_id: str
    source_type: str
    display_name: str


class AlignmentEdgeOut(BaseModel):
    """One comparison the run makes, and what it asks.

    Direction lives here rather than on the document because a document can sit
    on either side: in a three-document run the cTPP is compared against the
    iTPP and is the reference for the IPDP.
    """

    edge_id: str
    reference_doc_id: str
    comparison_doc_id: str
    question: str


class AlignmentEdgeSpecOut(BaseModel):
    """One declared comparison, by source type, for the picker to preview."""

    reference: str
    comparison: str
    question: str


class AlignerEdgesResponse(BaseModel):
    edges: list[AlignmentEdgeSpecOut]


class AlignmentFindingOut(BaseModel):
    """What became of one requirement in the document measured against it.

    Two citation lists, and they are not interchangeable: `reference_block_ids` is
    where the bar is stated, `comparison_block_ids` is what was read to judge it. The
    service contract checks each against its own document, so a reader resolving either
    one lands in the file that actually says it.

    `verdict` is asymmetric by design. The vocabulary this replaced described how two
    documents differ, which gave a candidate that beat its target and one that missed it
    by years the same label.
    """

    requirement_id: str
    edge_id: str
    requirement: str
    reference_block_ids: list[str] = Field(default_factory=list)
    verdict: str
    statement: str = ""
    #: What the measured document would have to close. Present only where the verdict
    #: is `falls_short` or `not_comparable`.
    gap: str = ""
    comparison_block_ids: list[str] = Field(default_factory=list)


class AlignmentResultOut(BaseModel):
    """Identified documents, the comparisons they resolve, their source, and findings.

    `findings` is the denominator as well as the content: every requirement read out of
    a reference document appears exactly once whatever its verdict, so two runs of one
    pair compare line by line and no count is stored beside the list it summarises.
    """

    documents: list[AlignmentDocumentOut]
    edges: list[AlignmentEdgeOut]
    org: str
    intervention_class: str
    indication: str
    blocks: list[ContentBlockOut] = Field(default_factory=list)
    findings: list[AlignmentFindingOut] = Field(default_factory=list)


class AlignerRunResponse(BaseModel):
    alignment: AlignmentResultOut


class GateSpecOut(BaseModel):
    """One declared stage gate, for a selector that has not chosen one yet."""

    id: str
    label: str
    ordinal: int


class ExpertGatesResponse(BaseModel):
    gates: list[GateSpecOut]


class QuestionAssessmentOut(BaseModel):
    """One gate question and what became of it.

    Four states, each traceable. `not_applicable` means the question text states a class
    this run is not, so no model read it and it is not a shortfall of any kind. The other
    three are what a model concluded from the supplied material, ordered by how much of
    the question is closed: `answered`, `partly_answered`, `not_found`.

    `partly_answered` exists because the bank's questions are compound. A binary made a
    thorough plan and a blank page produce the same count, and `missing` is the sentence
    that says what a partial still leaves open.

    `source` separates an answer that can be checked from one that cannot.
    `document` carries `cited_block_ids`; `context` carries the label of a
    transient item the user supplied for that run, whose text is deliberately not
    retained anywhere.
    """

    id: str
    text: str
    state: Literal["not_applicable", "answered", "partly_answered", "not_found"]
    #: Whether the gate requires this answered now or expects it to be forming. From the
    #: bank, on every question.
    requirement: str = "required"
    # Where the answer would usually live: a hint for a reader, carried from the bank.
    # It decided nothing about this question's state.
    statement: str = ""
    # What a partial answer still leaves open, and empty on every other state.
    missing: str = ""
    source: Literal["document", "context"] | None = None
    cited_block_ids: list[str] = Field(default_factory=list)
    context_label: str = ""


class DisciplineReviewOut(BaseModel):
    id: str
    label: str
    questions: list[QuestionAssessmentOut] = Field(default_factory=list)


class ReviewDocumentOut(BaseModel):
    doc_id: str
    source_type: str


class GateReviewOut(BaseModel):
    """One gate's triage, with every question the gate asks.

    The denominator never shrinks: a question the run could not assess is present
    with the state that says so, rather than absent from the list. Counts are
    derived by readers and never carried, so nothing can disagree with the list it
    would be summarizing.
    """

    gate_id: str
    gate_label: str
    # The authored document the bank transcribes, with its version. Carried so a
    # saved review states its own authority rather than depending on a config that
    # will move.
    bank_source: str = ""
    documents: list[ReviewDocumentOut]
    disciplines: list[DisciplineReviewOut]
    # Labels of the transient context items supplied, never their text.
    context_labels: list[str] = Field(default_factory=list)
    org: str
    intervention_class: str
    indication: str
    blocks: list[ContentBlockOut] = Field(default_factory=list)


class ExpertRunResponse(BaseModel):
    review: GateReviewOut


class AskMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AskRequest(BaseModel):
    result_type: str  # "scout" | "inspector" | ...
    result: dict[str, Any]
    messages: list[AskMessage]
    # The source document behind the result (parsed blocks), if available. Lets
    # the assistant cross-compare the distilled result against the full document.
    document: list[ContentBlockOut] | None = None


class AssistantContextResponse(BaseModel):
    filename: str
    doc_id: str
    blocks: list[ContentBlockOut]


class PriorityItemIn(BaseModel):
    """One priority exactly as the panel rendered it.

    The panel's own shape, so a tool sends what a reader is looking at rather than a
    second projection of its result that could describe a different list.
    """

    id: str
    label: str
    qualifier: str = ""
    statement: str = ""
    recommendation: str = ""


class PriorityDigestRequest(BaseModel):
    """What a digest reads: the list on screen, and the analysis behind it.

    `authority` is the tool's own catalog sentence — what it reads and what it judges
    against — passed in rather than looked up, so neither this route nor the service
    holds a table of tools. A tool added later is served without either changing.
    """

    authority: str
    order_note: str = ""
    items: list[PriorityItemIn]
    #: The result's analysis without its blocks, as the assistant already receives it.
    analysis: Any
    #: Every block ID the result carries, so a nomination's citation can be checked.
    block_ids: list[str] = Field(default_factory=list)
    org: str = ""
    intervention_class: str = ""
    indication: str = ""


class PriorityNominationOut(BaseModel):
    label: str
    statement: str
    cited_block_ids: list[str] = Field(default_factory=list)


class PriorityDigestResponse(BaseModel):
    """One passage about the list, and what the list leaves out.

    Never part of a result: it describes a list that is itself derived when a result is
    opened, so storing it would let a paragraph outlive the list it summarises.
    """

    digest: str
    nominations: list[PriorityNominationOut] = Field(default_factory=list)


# --- Archivist ---------------------------------------------------------------
#
# Archivist publishes what the archive says, so its wire shape carries no verdict, no
# score and no comparison - there is nothing here for a client to render as a judgment.
# What it does carry, deliberately, is the same nesting the service uses: a column, then
# the document types under it, then three disjoint states. A flat list of rows would let a
# client merge an iTPP's class-level ambition with a cTPP's candidate commitment, and the
# nesting is what makes that unrepresentable rather than merely discouraged.


class ArchivistColumnOut(BaseModel):
    """One indexed attribute, and how a client may use it."""

    attribute: str
    #: Non-empty exactly when the column is filterable. A client reads the presence of a
    #: vocabulary as permission to offer a picker, rather than keeping its own list of
    #: which columns are filterable.
    tags: list[str] = Field(default_factory=list)
    #: The unit family a value may carry, empty when the column is not a quantity. Tells a
    #: client whether sorting by `magnitude` means anything for this column.
    quantity: str = ""
    #: Sibling attributes this column must not absorb. Published because it is what the
    #: extraction was fenced by, and a reader judging a value needs to know what was
    #: deliberately kept out of it.
    not_confused_with: list[str] = Field(default_factory=list)


class ArchivistDocumentOut(BaseModel):
    id: str
    title: str
    org: str
    intervention_class: str
    indication: str
    source_type: str


class ArchivistRecordOut(BaseModel):
    """One thing one document said.

    `document_id` rather than an inlined title: the document appears once in
    `documents`, and a title repeated on eight rows is eight chances to disagree with
    itself.
    """

    document_id: str
    attribute: str
    status: str
    bound: str
    stated: str = ""
    magnitude: float | None = None
    unit: str = ""
    tags: list[str] = Field(default_factory=list)
    condition_attribute: str = ""
    condition_stated: str = ""
    #: The verbatim span, the block it came from, and that block's whole text. All three
    #: travel together because a quote alone misleads: "24 months" reads differently when
    #: the same block says "for the lyophilized presentation only".
    quote: str = ""
    block_id: str = ""
    block_text: str = ""
    section_label: str = ""
    #: Why the document was read as silent, or why the reading is uncertain. Never set on
    #: a stated value, where the quote is the justification.
    reason: str = ""


class ArchivistSourceTypeGroupOut(BaseModel):
    """One document type's answers for one column, in three disjoint states.

    `silent` holds document ids rather than records: a document that said nothing has no
    value, no quote and no bound, so a record shape would be almost entirely empty. What a
    reader needs is which documents they were, and the count follows from the list.
    """

    source_type: str
    values: list[ArchivistRecordOut] = Field(default_factory=list)
    uncertain: list[ArchivistRecordOut] = Field(default_factory=list)
    silent: list[str] = Field(default_factory=list)


class ArchivistAttributeGroupOut(BaseModel):
    attribute: str
    quantity: str = ""
    tag_vocabulary: list[str] = Field(default_factory=list)
    groups: list[ArchivistSourceTypeGroupOut] = Field(default_factory=list)


class ArchivistCorpusResponse(BaseModel):
    """What the archive holds, for building the query.

    `built_at` empty and `documents` zero is a real state, not an error: the tool is
    registered before any archive is built, and the interface has to be able to say
    "nothing has been indexed yet" rather than fail.
    """

    built_at: str = ""
    documents: list[ArchivistDocumentOut] = Field(default_factory=list)
    columns: list[ArchivistColumnOut] = Field(default_factory=list)
    intervention_class: str = ""
    #: Every intervention class with columns declared. A client offering a class the
    #: corpus cannot answer would produce an empty result with no explanation.
    intervention_classes: list[str] = Field(default_factory=list)
    #: What the corpus actually contains, not what the vocabulary declares. Offering
    #: thirteen indications when the archive holds three produces a filter that returns
    #: nothing and says nothing about why.
    indications: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)


class ArchivistTagFilterIn(BaseModel):
    attribute: str
    values: list[str] = Field(default_factory=list)


class ArchivistQueryRequest(BaseModel):
    """Which rows to read.

    `intervention_class` is required and is not a filter like the others: the columns are
    declared per class, so it decides what the answer can be about at all.
    """

    intervention_class: str
    attributes: list[str] = Field(default_factory=list)
    indications: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    tags: list[ArchivistTagFilterIn] = Field(default_factory=list)


class ArchivistQueryResponse(BaseModel):
    intervention_class: str
    built_at: str = ""
    documents: list[ArchivistDocumentOut] = Field(default_factory=list)
    attributes: list[ArchivistAttributeGroupOut] = Field(default_factory=list)
