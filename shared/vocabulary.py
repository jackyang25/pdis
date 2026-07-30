"""Controlled vocabularies shared by more than one service.

``shared/attributes.yaml`` already declares itself "NOT owned by any service"
while tagging every attribute with an ``evidence_domain``. These sets are the
code half of that statement: searcher declares which domains and entity types a
source adapter can serve, and scout validates document-derived fields against the
same vocabulary. Neither owns it, so it lives here rather than one importing the
other for a definition.
"""

from __future__ import annotations

EVIDENCE_DOMAINS = frozenset(
    {
        "general",
        "biological",
        "clinical",
        "safety",
        "regulatory",
        "product",
        "manufacturing",
        "delivery",
        "commercial_access",
    }
)

ENTITY_TYPES = frozenset(
    {
        "disease",
        "pathogen",
        "protein",
        "gene",
        "antigen",
        "vaccine",
        "drug",
        "compound",
        "biomarker",
        "device",
        "other",
    }
)
