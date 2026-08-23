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

from dataclasses import dataclass
from pathlib import Path

import yaml

INDICATIONS_VOCAB = Path(__file__).resolve().parent / "indications.yaml"
ATTRIBUTES_VOCAB = Path(__file__).resolve().parent / "attributes.yaml"

#: What kind of evidence a retrieval source owns.
#:
#: One class per source, and the class is the source's responsibility rather than a
#: description of it: two sources in one class are alternatives, and a class with no
#: source is a hole a reader cannot see. Declared here because coverage is judged
#: across sources and no single source can state it.
#:
#: `epidemiology` is how much of the problem there is, and where. It answers a different
#: question from every other class: the rest report what someone did, claimed or
#: recommended, while this reports a measured quantity in a place. A target profile saying
#: "reduce cases by thirty per cent in sub-Saharan Africa" states a claim about that
#: quantity, and nothing else here supplies the number it is measured against.
#:
#: `guidance` is an authority's normative position - what should be done - as distinct
#: from `regulatory`, which is what has been permitted. The test that separates them: a
#: reader asking what a label allows would not accept what WHO recommends, and vice
#: versa. Two sources in one class have to be alternatives.
#:
#: `general` is the web, which is not a class so much as the absence of one - it is
#: whatever the classes below do not reach, which is exactly why a gap in them shows
#: up as web prose rather than as an absence.
EVIDENCE_CLASSES = frozenset(
    {
        "general",
        "literature",
        "registry",
        "regulatory",
        "access",
        "molecular",
        "news",
        "guidance",
        "epidemiology",
    }
)

#: Whose evidence a source holds.
#:
#: Not a country list: the question a reader asks is whether a finding describes the
#: setting they are deciding for, and "US" and "LMIC" answer that where "openFDA"
#: does not. `multi` is a source spanning several jurisdictions without aggregating
#: them into one; `global` is a source with no jurisdiction of its own.
JURISDICTIONS = frozenset({"global", "multi", "us", "eu", "uk", "lmic"})

#: What a request can state about the search, beyond its text.
#:
#: The other half of the wire. `DOWNSTREAM_OUTPUTS` says where a lane's findings go;
#: this says what a lane can be told. Both are declared on the same spec so a lane's
#: place in the pipeline is one thing to read rather than two to infer.
#:
#: Named as one vocabulary because the alternative is what it replaced: `condition`
#: lived on the intent, `population` on a query facet, subjects in `entities`, and the
#: region a document states lived nowhere. Four mechanisms for one idea, and the one
#: that was missing was invisible because nothing enumerated the set.
#:
#:     text          the query prose itself; every lane reads this
#:     condition     the disease or health problem, the anchor of a field-addressed request
#:     intervention  the class of intervention - drug, vaccine, monoclonal antibody
#:     product       one named product, narrowing the class rather than replacing it
#:     population    who a result must describe
#:     outcome        the property or endpoint measured
#:     subject       a named gene, protein, compound or drug a lane addresses its API by
#:     region        the countries or WHO regions a programme targets
#:
#: A dimension earns a place here once some lane can act on it. The document also states
#: an epidemiological setting - endemic or epidemic, high or low transmission - and it is
#: deliberately absent: no source has such a field, so naming it here would add a
#: dimension nothing supplies and nothing consumes, kept alive by two entries in two gap
#: lists. Add it when a lane can use it.
SCOPE_DIMENSIONS = frozenset(
    {
        "text",
        "condition",
        "intervention",
        "product",
        "population",
        "outcome",
        "subject",
        "region",
    }
)

#: Where a scope value came from.
#:
#: Recorded per dimension because the alternative is a bag of strings nobody can audit.
#: A blank condition chosen by a reader and a blank condition nothing ever supplied look
#: identical in the value and mean opposite things: one is a deliberate widening, the
#: other is a wire that was never connected.
#:
#:     header          a field the reader set for the run
#:     document        derived from the uploaded document, and traceable to its blocks
#:     config_default  supplied by the document type's configuration
#:     unset           no supplier. The dimension widens the search rather than narrowing it
SCOPE_PROVENANCE = frozenset({"header", "document", "config_default", "unset"})

#: What a source's output reaches downstream.
#:
#: The wire, stated by the source that carries it. A source declaring nothing here
#: produces findings that no consumer reads, which is not a small inefficiency: it is
#: a lane a reader can enable, wait for, and be told nothing by.
#:
#:     insights   passages enter semantic reasoning (requires evidence_role "evidence")
#:     landscape  structured development records enter the development landscape
#:     safety     structured safety observations enter the safety projection
#:     burden     structured indicator readings enter the disease-burden projection
DOWNSTREAM_OUTPUTS = frozenset({"insights", "landscape", "safety", "burden"})

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


@dataclass(frozen=True)
class AttributeDefinition:
    """One attribute exactly as ``shared/attributes.yaml`` declares it.

    The file's own record and nothing more. Services wrap it in whatever shape they
    need - scout binds a document target and a resolution state onto it, archivist reads
    only the name and the description - and the fields a service adds stay in that
    service. Both `evidence_domain` and `supplies_scope` are already shared vocabularies
    (`EVIDENCE_DOMAINS`, `SCOPE_DIMENSIONS`), so they belong to the record rather than to
    whoever reads it first.
    """

    name: str
    description: str
    evidence_domain: str = "general"
    supplies_scope: str = ""


def attribute_definitions(intervention_class: str) -> tuple[AttributeDefinition, ...]:
    """Every attribute declared for one intervention class, in file order.

    Here rather than in scout, which read it first, because a second service now needs
    the same rows: archivist quotes an attribute's description into an extraction prompt
    and names sibling attributes it must not be confused with. Two readers of one file
    are two answers that can disagree about what the vocabulary says.
    """
    if not ATTRIBUTES_VOCAB.exists():
        raise LookupError(f"Shared attribute vocabulary missing: {ATTRIBUTES_VOCAB}")
    with ATTRIBUTES_VOCAB.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    items = data.get(intervention_class) or []
    return tuple(
        AttributeDefinition(
            name=item["name"],
            description=item["description"],
            evidence_domain=item.get("evidence_domain", "general"),
            supplies_scope=item.get("supplies_scope", ""),
        )
        for item in items
    )


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
