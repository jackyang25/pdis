"""Pydantic response models for the API.

These mirror the dataclasses in services/, but expose only what the
frontend needs. Keep them lean and explicit — Pydantic schemas are the
wire contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentType(BaseModel):
    key: str  # "{org}_{source_type}_{intervention}"
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    supports: dict[str, bool]  # {"chunker": true, "reviewer": ..., "scout": ...}


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


class FindingOut(BaseModel):
    url: str
    title: str
    query: str
    retrieved_at: str
    excerpt: str | None = None
    published_at: str | None = None
    source: str = "unknown"
    queries: list[str] = Field(default_factory=list)
    source_lanes: list[str] = Field(default_factory=list)
    source_labels: dict[str, str] = Field(default_factory=dict)
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
    tracks: list[str] = Field(default_factory=list)
    doc_block_ids: list[str] = Field(default_factory=list)
    status: str = "complete"
    error: str = ""
    finding_count: int = 0
    source_urls: list[str] = Field(default_factory=list)


class VariableOut(BaseModel):
    name: str
    description: str
    block_ids: list[str] = Field(default_factory=list)


class MeasurementOut(BaseModel):
    value: float
    unit: str = ""
    evidence_form: str = "other"
    development_phase: str = "unknown"
    source_record_type: str = "unknown"
    url: str = ""
    insight_id: str = ""
    age_months: float | None = None
    weight: float = 0.0


class ConformityOut(BaseModel):
    attribute_ref: str
    target_value: float
    comparator: str
    unit: str = ""
    target_label: str = ""
    conformity: float
    lower: float
    upper: float
    verdict: str
    doc_block_ids: list[str] = Field(default_factory=list)
    measurements: list[MeasurementOut] = Field(default_factory=list)


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


class ScoutRunResponse(BaseModel):
    org: str
    source_type: str
    intervention_class: str
    indication: str
    variables: list[VariableOut]
    search_plan: list[SearchTraceOut] = Field(default_factory=list)
    matches: list[MatchOut]
    conformity: list[ConformityOut] = Field(default_factory=list)
    precedents: list[PrecedentOut] = Field(default_factory=list)
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


class ReviewResultOut(BaseModel):
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
    # document behind the grades. Not used by the Reviewer UI itself.
    blocks: list[ContentBlockOut] = []


class ReviewerRunResponse(BaseModel):
    review: ReviewResultOut


class AskMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AskRequest(BaseModel):
    result_type: str  # "scout" | "reviewer" | ...
    result: dict[str, Any]
    messages: list[AskMessage]
    # The source document behind the result (parsed blocks), if available. Lets
    # the assistant cross-compare the distilled result against the full document.
    document: list[ContentBlockOut] | None = None


class AskResponse(BaseModel):
    answer: str
