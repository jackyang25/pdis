"""Pydantic response models for the API.

These mirror the dataclasses in services/, but expose only what the
frontend needs. Keep them lean and explicit — Pydantic schemas are the
wire contract.
"""

from __future__ import annotations

from pydantic import BaseModel


class DocumentType(BaseModel):
    key: str  # "{org}_{source_type}_{intervention}"
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    supports: dict[str, bool]  # {"chunker": true, "reviewer": ..., "monitor": ...}


class DocumentTypesResponse(BaseModel):
    document_types: list[DocumentType]


class IndicationsResponse(BaseModel):
    indications: list[str]


class ContentBlockOut(BaseModel):
    id: str
    doc_id: str
    ordinal: int
    block_type: str
    content: str
    heading_stack: list[str]
    section_label: str | None = None


class ChunkerRunResponse(BaseModel):
    doc_id: str
    blocks: list[ContentBlockOut]


class FindingOut(BaseModel):
    url: str
    title: str
    query: str
    retrieved_at: str
    excerpt: str | None = None
    published_at: str | None = None
    source: str = "web"


class SearcherRunResponse(BaseModel):
    query: str
    findings: list[FindingOut]


class InsightOut(BaseModel):
    statement: str
    query: str
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


class EvidenceAssessmentOut(BaseModel):
    attribute_ref: str
    strength: str
    basis: list[str]
    reason: str
    doc_target: str = ""
    supporting_findings: list[FindingOut]


class FunnelStatsOut(BaseModel):
    queries: int
    findings: int
    unique_findings: int
    insights: int
    matches: int
    assessments: int


class VariableOut(BaseModel):
    name: str
    description: str


class MeasurementOut(BaseModel):
    value: float
    source_type: str
    url: str = ""
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
    measurements: list[MeasurementOut] = []


class PrecedentOut(BaseModel):
    attribute_ref: str
    precedent: str  # established | emerging | novel | disconfirmed | unknown
    reason: str = ""
    supporting_findings: list[FindingOut] = []


class MonitorRunResponse(BaseModel):
    org: str
    source_type: str
    intervention_class: str
    indication: str
    variables: list[VariableOut]
    matches: list[MatchOut]
    conformity: list[ConformityOut] = []
    precedents: list[PrecedentOut] = []
    assessments: list[EvidenceAssessmentOut]
    stats: FunnelStatsOut


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


class ReviewResultOut(BaseModel):
    doc_id: str
    dimensions: dict[str, DimensionGradeOut]
    top_issues: list[str]
    section_grades: list[SectionGradeOut]
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None


class ReviewerRunResponse(BaseModel):
    review: ReviewResultOut
