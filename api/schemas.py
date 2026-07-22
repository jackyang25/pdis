"""Pydantic response models for the API.

These mirror the dataclasses in services/, but expose only what the
frontend needs. Keep them lean and explicit — Pydantic schemas are the
wire contract.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class SafetyRecordOut(BaseModel):
    product_name: str
    signal_type: Literal["label_warning", "reported_event", "device_event", "recall"]
    signal: str
    detail: str = ""
    count: int | None = None
    qualification: str = ""


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
    safety_records: list[SafetyRecordOut] = Field(default_factory=list)
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
    supporting_findings: list[FindingOut]
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    attribute_ref: str | None = None


class MatchOut(BaseModel):
    insight: InsightOut
    relation: str
    reason: str
    doc_block_ids: list[str] = Field(default_factory=list)


class EvidenceAssessmentOut(BaseModel):
    attribute_ref: str
    strength: str
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
    intent_ids: list[str] = Field(default_factory=list)
    input_queries: list[str] = Field(default_factory=list)
    applicability: str = "applicable"
    applicability_reason: str = ""
    status: str = "complete"
    error: str = ""
    finding_count: int = 0
    source_urls: list[str] = Field(default_factory=list)


class EvidenceEntityOut(BaseModel):
    name: str
    entity_type: str
    identifier: str = ""


class VariableOut(BaseModel):
    name: str
    description: str
    block_ids: list[str] = Field(default_factory=list)
    document_target: str = ""
    definition_mode: Literal["fixed", "dynamic"] = "fixed"
    target_resolved: bool = False
    evidence_domain: str = "general"
    entities: list[EvidenceEntityOut] = Field(default_factory=list)


class MeasurementOut(BaseModel):
    value: float
    unit: str = ""
    evidence_form: str = "other"
    development_phase: str = "unknown"
    source_record_type: str = "unknown"
    url: str = ""
    insight_id: str = ""
    source_quote: str = ""
    source_record_id: str = ""
    source_identity_status: Literal["canonical", "title_fallback", "url_fallback"] = "url_fallback"
    comparability: dict[
        str, Literal["same", "compatible", "not_applicable", "different", "unknown"]
    ] = Field(default_factory=dict)
    comparability_reasons: dict[str, str] = Field(default_factory=dict)
    inclusion_reason: str = ""
    exclusion_reasons: list[str] = Field(default_factory=list)
    age_months: float | None = None


class ConformityOut(BaseModel):
    attribute_ref: str
    target_value: float
    comparator: Literal[">=", "<="]
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
    calibration_status: Literal[
        "insufficient", "limited", "sufficient", "legacy_unverified"
    ] = "insufficient"
    doc_block_ids: list[str] = Field(default_factory=list)
    measurements: list[MeasurementOut] = Field(default_factory=list)
    excluded_measurements: list[MeasurementOut] = Field(default_factory=list)


class PrecedentOut(BaseModel):
    attribute_ref: str
    precedent: str  # direct | adjacent | none | unknown
    outcome: str = "unknown"  # favorable | mixed | unfavorable | unknown
    reason: str = ""
    doc_block_ids: list[str] = Field(default_factory=list)
    coverage_insight_ids: list[str] = Field(default_factory=list)
    outcome_insight_ids: list[str] = Field(default_factory=list)
    supporting_insight_ids: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class DevelopmentProgramOut(BaseModel):
    name: str
    sponsors: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    record_types: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    attribute_refs: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class SafetySignalOut(BaseModel):
    product_name: str
    signal_type: Literal["label_warning", "reported_event", "device_event", "recall"]
    signal: str
    detail: str = ""
    count: int | None = None
    qualification: str = ""
    attribute_refs: list[str] = Field(default_factory=list)
    supporting_findings: list[FindingOut] = Field(default_factory=list)


class DocumentContextValidationOut(BaseModel):
    status: Literal["match", "mismatch", "uncertain"]
    configured_indication: str
    document_indication: str = ""
    reason: str = ""
    doc_block_ids: list[str] = Field(default_factory=list)


class ScoutRunResponse(BaseModel):
    org: str
    source_type: str
    intervention_class: str
    indication: str
    context_validation: DocumentContextValidationOut
    variables: list[VariableOut]
    search_plan: list[SearchTraceOut] = Field(default_factory=list)
    matches: list[MatchOut]
    conformity: list[ConformityOut] = Field(default_factory=list)
    precedents: list[PrecedentOut] = Field(default_factory=list)
    development_landscape: list[DevelopmentProgramOut] = Field(default_factory=list)
    safety_signals: list[SafetySignalOut] = Field(default_factory=list)
    assessments: list[EvidenceAssessmentOut]
    stats: FunnelStatsOut
    # The parsed source document, carried so the Ask assistant can read the full
    # document behind the distilled analysis. Not used by the Scout UI itself.
    blocks: list[ContentBlockOut] = Field(default_factory=list)


class DimensionGradeOut(BaseModel):
    grade: str
    issues: list[str] = []
    recommendation: str = ""


class VariableGradeOut(BaseModel):
    variable_name: str
    dimensions: dict[str, DimensionGradeOut]
    block_ids: list[str] = []


class SectionGradeOut(BaseModel):
    section_name: str
    is_present: bool
    dimensions: dict[str, DimensionGradeOut]
    missing_variables: list[str] = []
    variable_grades: list[VariableGradeOut] = []


class CrossSectionFindingOut(BaseModel):
    description: str
    sections: list[str] = []
    recommendation: str = ""


class InspectionResultOut(BaseModel):
    doc_id: str
    dimensions: dict[str, DimensionGradeOut]
    top_issues: list[str]
    section_grades: list[SectionGradeOut]
    cross_section_findings: list[CrossSectionFindingOut] = []
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    # The parsed source document, carried so the Ask assistant can read the full
    # document behind the grades. Not used by the Inspector UI itself.
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


class AskResponse(BaseModel):
    answer: str
