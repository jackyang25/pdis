"""Controlled vocabularies shared by more than one service.

``shared/attributes.yaml`` already declares itself "NOT owned by any service"
while tagging every attribute with an ``evidence_domain``. These sets are the
code half of that statement: searcher declares which domains and entity types a
source adapter can serve, and scout validates document-derived fields against the
same vocabulary. Neither owns it, so it lives here rather than one importing the
other for a definition.

The intervention-class readers below are the same idea for
``shared/indications.yaml``: its top-level keys have always been the intervention
vocabulary, and two callers now need them — the config route to list indications,
and Expert to validate that a question bank names classes that exist. Reading the
file in both places would be two answers that could disagree.
"""

from __future__ import annotations

from pathlib import Path

import yaml

INDICATIONS_VOCAB = Path(__file__).resolve().parent / "indications.yaml"

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


def _indications_document() -> dict[str, object]:
    if not INDICATIONS_VOCAB.exists():
        return {}
    with INDICATIONS_VOCAB.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def intervention_classes() -> frozenset[str]:
    """Every intervention class the shared indication vocabulary declares."""
    return frozenset(str(key) for key in _indications_document())


def indications_for(intervention_class: str) -> list[str]:
    """The indications declared for one intervention class, in file order."""
    values = _indications_document().get(intervention_class) or []
    return [str(value) for value in values] if isinstance(values, list) else []


def search_term(tag: str) -> str:
    """One config tag as it should read inside a query or a prompt sentence.

    Both context tags that name subject matter need this — the indication and the
    intervention class. A class is interpolated into eight prompt sentences and joined
    into the fallback query beside the indication, so `monoclonal_antibody` has exactly
    the same two jobs, and exactly the same conflict, as `group_b_streptococcus`.

    A tag is stored as a stable lowercase key and travels into retrieval
    text, so the two needs collide the moment a name has more than one word:
    `group_b_streptococcus` is a fine key and a useless search term. Attribute names
    were already de-underscored at the point they were joined into a query while the
    indication beside them was not, which is why the vocabulary was confined to
    single words — and why the two multi-word names it needed became `tb` and `gbs`.

    Here rather than at each call site because it has two consumers that must not
    diverge: the query fallback that joins the tag into text, and the configuration
    framing that substitutes it into a prompt sentence. A tag rendered one way in a
    query and another in the instructions about that query is the drift this prevents.
    """
    return tag.replace("_", " ").strip()
