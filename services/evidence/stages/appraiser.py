"""Appraiser: labels each claim with reliability signals.

Two fields, both heuristic at MVP:
  - evidence_strength: defaults by source_type.
  - recency_tier: computed from extracted_at / valid_as_of vs a configured policy.

Shared across all extractors. No LLM. Pure function over a Claim list.
"""

from __future__ import annotations

import datetime as _dt

from ..models import Claim


STRENGTH_BY_SOURCE_TYPE: dict[str, str] = {
    "product_profile": "strong",
    "trial": "strong",
    "regulatory_doc": "strong",
    "real_world_data": "moderate",
    "paper": "moderate",
    "model_run": "moderate",
    "market_report": "moderate",
    "knowledge_graph": "weak",
    "interview": "anecdotal",
    "expert_note": "anecdotal",
}

# Recency policy (years).
_CURRENT_MAX_YEARS = 2
_AGING_MAX_YEARS = 5


def appraise_claims(claims: list[Claim]) -> list[Claim]:
    """Fill evidence_strength + recency_tier on every claim. Mutates in place."""
    today = _dt.date.today()
    for claim in claims:
        if claim.evidence_strength is None:
            claim.evidence_strength = _strength_for(claim.source_kind)
        if claim.recency_tier is None:
            claim.recency_tier = _recency_for(today, claim.valid_as_of, claim.extracted_at)
    return claims


def _strength_for(source_type: str) -> str:
    return STRENGTH_BY_SOURCE_TYPE.get(source_type, "moderate")


def _recency_for(today: _dt.date, valid_as_of: str | None, extracted_at: str) -> str:
    reference = valid_as_of or extracted_at
    if not reference:
        return "current"
    try:
        reference_date = _dt.date.fromisoformat(reference[:10])
    except ValueError:
        return "current"
    age_years = (today - reference_date).days / 365.0
    if age_years < _CURRENT_MAX_YEARS:
        return "current"
    if age_years < _AGING_MAX_YEARS:
        return "aging"
    return "stale"
