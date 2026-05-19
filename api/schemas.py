"""Pydantic response models for the API.

These mirror the dataclasses in services/, but expose only what the
frontend needs. Keep them lean and explicit — Pydantic schemas are the
wire contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TriplesResponse(BaseModel):
    orgs: list[str]
    source_types_by_org: dict[str, list[str]]
    interventions_by_org_source: dict[str, list[str]]


class TherapeuticAreasResponse(BaseModel):
    therapeutic_areas: list[str]


class ContentBlockOut(BaseModel):
    id: str
    doc_id: str
    ordinal: int
    block_type: str
    content: str
    heading_stack: list[str]
    section_label: str | None = None
    label_confidence: str | None = None


class ChunkerRunResponse(BaseModel):
    doc_id: str
    blocks: list[ContentBlockOut]


class ClaimOut(BaseModel):
    id: str
    ordinal: int
    statement: str
    claim_type: str
    polarity: str
    source_id: str
    source_kind: str
    source_locator: dict[str, Any]
    attribute_ref: str | None = None
    binding_confidence: str | None = None
    evidence_strength: str | None = None
    recency_tier: str | None = None
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    therapeutic_area: str | None = None


class EvidenceRunResponse(BaseModel):
    doc_id: str
    source_id: str
    claims: list[ClaimOut]


class VariableGradeOut(BaseModel):
    variable_name: str
    grade: str
    issues: list[str]
    recommendation: str
    block_ids: list[str]


class SectionGradeOut(BaseModel):
    section_name: str
    grade: str
    is_present: bool
    missing_variables: list[str]
    issues: list[str]
    recommendation: str
    variable_grades: list[VariableGradeOut]


class ReviewResultOut(BaseModel):
    doc_id: str
    overall_grade: str
    top_issues: list[str]
    section_grades: list[SectionGradeOut]
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    therapeutic_area: str | None = None


class PeerClaimOut(BaseModel):
    source_id: str
    statement: str
    attribute_ref: str | None = None
    binding_confidence: str | None = None
    evidence_strength: str | None = None


class PDReviewerRunResponse(BaseModel):
    review: ReviewResultOut
    peer_claims: list[PeerClaimOut]
