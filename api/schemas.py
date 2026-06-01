"""Pydantic response models for the API.

These mirror the dataclasses in services/, but expose only what the
frontend needs. Keep them lean and explicit — Pydantic schemas are the
wire contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DocumentType(BaseModel):
    key: str  # "{org}_{source_type}_{intervention}"
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    supports: dict[str, bool]  # {"chunker": true, "claims": ..., "reviewer": ...}


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
    section_label: str | None = None


class MatchOut(BaseModel):
    insight: InsightOut
    relation: str
    reason: str


class MonitorRunResponse(BaseModel):
    org: str
    source_type: str
    intervention_class: str
    indication: str
    matches: list[MatchOut]


class ClaimOut(BaseModel):
    """Mirrors the Claim dataclass — downloads must roundtrip back into FileClaimsStore."""

    id: str
    ordinal: int
    statement: str
    claim_type: str
    polarity: str
    source_id: str
    source_kind: str
    source_locator: dict[str, Any]
    extracted_at: str
    valid_as_of: str | None = None
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    attribute_ref: str | None = None
    claim_schema_version: str = "v1"
    source_url: str | None = None
    extractor_version: str | None = None
    model_id: str | None = None
    prompt_hash: str | None = None


class BenchmarkerRunResponse(BaseModel):
    doc_id: str
    source_id: str
    claims: list[ClaimOut]


class DimensionGradeOut(BaseModel):
    grade: str
    issues: list[str] = []
    recommendation: str = ""
    cited_claim_ids: list[str] = []


class VariableGradeOut(BaseModel):
    variable_name: str
    dimensions: dict[str, DimensionGradeOut]
    block_ids: list[str] = []
    attribute_ref: str | None = None


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


class PeerClaimOut(BaseModel):
    source_id: str
    statement: str
    claim_type: str | None = None
    attribute_ref: str | None = None
    valid_as_of: str | None = None
    extracted_at: str | None = None
    org: str | None = None
    source_type: str | None = None
    indication: str | None = None


class ReviewerRunResponse(BaseModel):
    review: ReviewResultOut
    peer_claims: list[PeerClaimOut]
