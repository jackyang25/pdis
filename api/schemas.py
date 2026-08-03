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
    record_type: Literal[
        "clinical_trial",
        "compound_catalog",
        "regulatory_label",
        "regulatory_clearance",
    ]
    record_id: str = ""
    sponsor: str = ""
    phase: str = ""
    status: str = ""
    source_role: Literal[
        "experimental", "comparator", "control", "co_intervention", "unknown"
    ] = "unknown"


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
    queries: list[str] = Field(default_factory=list)
    source_lanes: list[str] = Field(default_factory=list)
    source_labels: dict[str, str] = Field(default_factory=dict)
    source_attributions: dict[str, SourceAttributionOut] = Field(default_factory=dict)
    retrieval_paths: list[RetrievalPathOut] = Field(default_factory=list)
    title_source_lane: str = ""
    excerpt_source_lane: str = ""
    published_source_lane: str = ""


class SearcherRunResponse(BaseModel):
    query: str
    findings: list[FindingOut]


class SearchSourceOut(BaseModel):
    key: str
    label: str
    default_enabled: bool
    configured: bool = True
    attribution: SourceAttributionOut | None = None
    evidence_domains: list[str] = Field(default_factory=list)
    required_entity_types: list[str] = Field(default_factory=list)


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
    context_validation: DocumentContextValidationOut
    quantitative_ledger: QuantitativeLedgerOut
    variables: list[VariableOut]
    search_plan: list[SearchTraceOut] = Field(default_factory=list)
    matches: list[MatchOut]
    conformity: list[ConformityOut] = Field(default_factory=list)
    precedents: list[PrecedentOut] = Field(default_factory=list)
    development_landscape: list[DevelopmentProgramOut] = Field(default_factory=list)
    safety_observations: list[SafetyObservationOut] = Field(default_factory=list)
    assessments: list[EvidenceAssessmentOut]
    stats: FunnelStatsOut
    # The parsed source document. Read by the Ask assistant and by the Scout UI's
    # document-trace view, which renders results against their source blocks.
    blocks: list[ContentBlockOut] = Field(default_factory=list)


class ScoutContinueRequest(BaseModel):
    draft: ScoutRunResponse


class DimensionGradeOut(BaseModel):
    grade: Literal["A", "B", "C", "D", "F", "N/A"]
    issues: list[str] = []
    recommendation: str = ""
    # Lineage belongs to the dimension that cited it, not to the variable.
    cited_block_ids: list[str] = []


class VariableGradeOut(BaseModel):
    variable_name: str
    dimensions: dict[str, DimensionGradeOut]
    # The completeness judgment's presence answer. `missing_variables` is derived
    # from this on the client rather than shipped alongside it.
    content_status: Literal[
        "substantive", "partial", "placeholder", "missing", "not_applicable"
    ] = "not_applicable"


class SectionGradeOut(BaseModel):
    section_name: str
    is_present: bool
    dimensions: dict[str, DimensionGradeOut]
    variable_grades: list[VariableGradeOut] = []
    # Deterministic section assignment, not a citation.
    mapped_block_ids: list[str] = []


class TopIssueOut(BaseModel):
    section_name: str
    issue: str
    dimension: Literal["completeness", "adherence", "rigor"] | None = None
    variable_name: str | None = None
    grade: Literal["A", "B", "C", "D", "F", "N/A"] = "N/A"
    content_status: Literal[
        "substantive", "partial", "placeholder", "missing", "not_applicable"
    ] | None = None
    recommendation: str = ""
    cited_block_ids: list[str] = []


class CrossSectionFindingOut(BaseModel):
    description: str
    sections: list[str] = []
    recommendation: str = ""
    block_ids: list[str] = []


class InspectionResultOut(BaseModel):
    doc_id: str
    dimensions: dict[str, DimensionGradeOut]
    top_issues: list[TopIssueOut]
    section_grades: list[SectionGradeOut]
    cross_section_findings: list[CrossSectionFindingOut] = []
    consistency_status: Literal[
        "complete", "partial", "failed", "not_applicable", "unknown"
    ] = "unknown"
    grading_status: Literal["complete", "unknown"] = "unknown"
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    # The parsed source document. Read by the Ask assistant and by the Inspector
    # UI's document-trace view, which renders grades against their source blocks.
    blocks: list[ContentBlockOut] = []


class InspectorRunResponse(BaseModel):
    inspection: InspectionResultOut


class AlignmentLabelOut(BaseModel):
    name: str
    description: str


class AlignmentDocumentOut(BaseModel):
    role: Literal["reference", "comparison"]
    doc_id: str
    source_type: str
    display_name: str


class AlignmentUnitOut(BaseModel):
    id: str
    document_role: Literal["reference", "comparison"]
    document_id: str
    unit_type: Literal[
        "target", "activity", "milestone", "requirement", "dependency", "risk_response"
    ]
    statement: str
    block_ids: list[str] = Field(default_factory=list)


class AlignmentLinkOut(BaseModel):
    id: str
    relation: Literal["aligned", "modified", "conflict", "missing", "introduced"]
    reference_unit_ids: list[str] = Field(default_factory=list)
    comparison_unit_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    reference_block_ids: list[str] = Field(default_factory=list)
    comparison_block_ids: list[str] = Field(default_factory=list)


class AlignmentStatsOut(BaseModel):
    reference_units: int
    comparison_units: int
    aligned: int
    modified: int
    conflict: int
    missing: int
    introduced: int


class AlignmentResultOut(BaseModel):
    reference_document: AlignmentDocumentOut
    comparison_document: AlignmentDocumentOut
    units: list[AlignmentUnitOut]
    links: list[AlignmentLinkOut]
    stats: AlignmentStatsOut
    org: str
    intervention_class: str
    indication: str
    unit_types: list[AlignmentLabelOut]
    relations: list[AlignmentLabelOut]
    blocks: list[ContentBlockOut] = Field(default_factory=list)


class AlignerRunResponse(BaseModel):
    alignment: AlignmentResultOut


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
