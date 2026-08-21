"""Scout data shapes, config, and the LLM client contracts it requires.

Public types live here - re-exported by __init__.py. Consumers import
from `services.scout`, never from this module directly.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from shared.openai_client import ModelTask

from services.searcher import Finding, QueryFacets, source_keys
from shared.vocabulary import (
    ENTITY_TYPES,
    EVIDENCE_DOMAINS,
    SCOPE_PROVENANCE,
    search_term,
)

if TYPE_CHECKING:
    from services.chunker import ContentBlock


CONFIGS_DIR = Path(__file__).resolve().parent / "configs"
ATTRIBUTES_FILE = Path(__file__).resolve().parents[2] / "shared" / "attributes.yaml"
VALID_RELATIONS = {"contradicts", "extends", "confirms", "unrelated"}
"""How one insight stands against the document's claim.

Assigned by answering four questions in order, not by weighing four labels: is it
off-topic (`unrelated`), does it show the target cannot be achieved or a stated fact
is wrong (`contradicts`), does it show the target holds (`confirms`), otherwise it
bears on the claim without settling it (`extends`).

`unrelated` here means "does not bear on this claim". `TARGET_RELATIONSHIPS` also has
an `unrelated`, and it means something else - see there.
"""
VALID_QUERY_TRACKS = {"general", "geographic", "counterfactual", "precedent"}
VALID_EVIDENCE_STRENGTHS = {
    "well_grounded",
    "partial",
    "thin",
    "unsupported",
    "unknown",
}
VALID_PRECEDENT = {"direct", "adjacent", "none", "unknown"}
VALID_PRECEDENT_OUTCOMES = {"favorable", "mixed", "unfavorable", "unknown"}
VALID_CONTEXT_STATUSES = {"match", "mismatch", "uncertain"}
TARGET_RELATIONSHIPS = frozenset(
    {"direct", "analogous", "adjacent", "unrelated", "unknown"}
)
"""How close a retrieved record's subject is to the uploaded product.

A different axis from `VALID_RELATIONS`: this asks what the record is ABOUT, that one
asks what the evidence DOES to a claim. They share the token `unrelated` and mean
different things by it - here, the record concerns no comparable product; there, the
insight does not bear on the claim. A record can be `analogous` on this axis while
its insight is `unrelated` on that one.

Kept as-is rather than renamed: the field name carries the axis, and changing a
published member would invalidate every saved Scout result for a wording gain.
"""
QUANTITATIVE_SEMANTIC_FIELDS = (
    "measure",
    "endpoint",
    "intervention",
    "population",
    "regimen",
    "time_horizon",
    "statistic",
    "conditions",
)
COMPARISON_MATCH_MODES = frozenset(
    {"exact", "compatible", "unconstrained", "unknown"}
)
SEMANTIC_SLOT_STATES = frozenset(
    {"specified", "not_specified", "unknown", "other"}
)
MEASUREMENT_KINDS = frozenset(
    {
        "point_estimate",
        "range",
        "bound",
        "confidence_interval",
        "count",
        "rate",
        "other",
        "unknown",
    }
)
MEASUREMENT_STATUSES = frozenset(
    {"comparable", "contextual", "incompatible", "unknown"}
)
MEASUREMENT_ADMISSION_STATUSES = frozenset(
    {"needs_review", "approved", "rejected", "not_eligible", "auto_admitted"}
)
MEASUREMENT_AI_RECOMMENDATIONS = frozenset({"admit", "reject", "flag"})
MEASUREMENT_EVIDENCE_MODES = frozenset({"prose", "structured_fact"})
EVIDENCE_UNIT_STATUSES = frozenset({"resolved", "record_level", "uncertain"})
TERNARY_DECISION_STATES = frozenset({"yes", "no", "unknown"})
QUANTITATIVE_TARGET_STATUSES = frozenset(
    {"not_evaluated", "present", "not_applicable", "uncertain"}
)
QUANTITATIVE_LEDGER_STATUSES = frozenset(
    {"complete", "not_applicable", "uncertain"}
)
QUANTITATIVE_REVIEW_CLASSIFICATIONS = frozenset(
    {
        "target",
        "partial_target",
        "context_only",
        "non_scalar",
        "range_or_set",
        "non_numeric",
        "uncertain",
    }
)
QUANTITATIVE_TARGET_REVIEW_STATUSES = frozenset(
    {"needs_review", "approved", "rejected"}
)
QUANTITATIVE_TARGET_AI_RECOMMENDATIONS = frozenset(
    {"confirm", "exclude", "flag"}
)
QUANTITATIVE_STATEMENT_REVIEW_STATUSES = frozenset(
    {"resolved", "needs_review", "accepted_exclusion"}
)
QUANTITATIVE_FIELD_LINK_RELATIONS = frozenset(
    {"defines", "constrains", "context_for"}
)


def available_configs() -> list["ScoutTypeConfig"]:
    """Every document type Scout can retrieve evidence for, in stable order.

    Decided by whether a file loads as a config, not by the shape of its name.
    Mirrors `chunker.available_configs` and `inspector.available_configs`.
    """
    configs: list[ScoutTypeConfig] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            config = load_config(str(path))
        except (ValueError, KeyError, TypeError):
            continue
        # A config is named for its identity; a scaffold is not.
        if config.type_key != path.stem:
            continue
        configs.append(config)
    return configs


def find_config(org: str, source_type: str, intervention_class: str) -> "ScoutTypeConfig":
    """Load the scout config for the given (org, source_type, intervention)."""
    path = CONFIGS_DIR / f"{org}_{source_type}_{intervention_class}.yaml"
    if not path.exists():
        raise LookupError(
            f"No scout config for ({org}, {source_type}, {intervention_class}). "
            f"Expected: {path}"
        )
    config = load_config(str(path))
    actual = (config.org, config.source_type, config.intervention_class)
    expected = (org, source_type, intervention_class)
    if actual != expected:
        raise LookupError(
            f"Scout config identity mismatch: requested {expected}, file declares {actual}"
        )
    expected_type_key = "_".join(expected)
    if config.type_key != expected_type_key:
        raise LookupError(
            "Scout config type_key mismatch: "
            f"expected {expected_type_key!r}, file declares {config.type_key!r}"
        )
    return config


class LLMClientProtocol(Protocol):
    """Schema-bound model capability required by Scout."""

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: ModelTask = "reasoning",
    ) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True)
class EvidenceEntity:
    """One document-stated entity usable by structured evidence sources."""

    name: str
    entity_type: str
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unknown evidence entity type: {self.entity_type}")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "identifier", self.identifier.strip())
        if not self.name:
            raise ValueError("evidence entity name cannot be empty")


def parse_evidence_entities(raw: object) -> list[EvidenceEntity]:
    """Validate model-produced entities against the one closed vocabulary."""
    if not isinstance(raw, list):
        return []
    entities: list[EvidenceEntity] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        entity_type = str(item.get("entity_type", "")).strip().lower()
        if not name or entity_type not in ENTITY_TYPES:
            continue
        entity = EvidenceEntity(
            name=name,
            entity_type=entity_type,
            identifier=str(item.get("identifier", "")).strip(),
        )
        if entity not in entities:
            entities.append(entity)
    return entities


@dataclass
class DocumentSpan:
    """One exact document quotation supporting a canonical document fact."""

    quote: str
    block_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.quote = " ".join(self.quote.split())
        self.block_ids = list(dict.fromkeys(self.block_ids))
        if not self.quote or not self.block_ids:
            raise ValueError("document span requires a quote and block IDs")


@dataclass
class Attribute:
    """One canonical document-bound investigation unit.

    Fixed vocabularies and dynamic extraction are interchangeable providers of
    this shape. ``description`` always defines what is being evaluated;
    ``document_target`` always contains the document's concrete target or
    commitment. Neither field changes meaning by document type.
    """

    name: str
    description: str
    # Exact document blocks supporting ``document_target``.
    block_ids: list[str] = field(default_factory=list)
    document_target: str = ""
    document_spans: list[DocumentSpan] = field(default_factory=list)
    # The only intentional TPP/IPDP distinction: how the definition was
    # supplied. All downstream stages consume the same bound shape.
    definition_mode: str = "fixed"  # fixed | dynamic
    # Distinguishes an intentionally absent target from a unit not yet bound to
    # its document. Runtime pipeline units are always resolved before search.
    target_resolved: bool = False
    target_resolution_reason: str = ""
    evidence_domain: str = "general"
    #: The run-scope dimension this attribute's document target supplies, if any.
    #:
    #: Declared on the attribute rather than matched by name in a stage, so the vocabulary
    #: stays the one place that knows which variable states the run's geography. A stage
    #: looking for `*.target_countries` would work until an intervention class named it
    #: something else, and then fail silently by finding nothing.
    supplies_scope: str = ""
    entities: list[EvidenceEntity] = field(default_factory=list)
    # Independently qualified numeric claims extracted once before retrieval.
    # Qualitative stages continue to use the canonical document_target binding.
    # Read-only field projection of canonical ledger targets. IDs, rather than
    # copied target objects, keep the document ledger as the sole authority.
    quantitative_target_ids: list[str] = field(default_factory=list)
    quantitative_statement_dispositions: list["QuantitativeStatementDisposition"] = field(
        default_factory=list
    )
    quantitative_target_status: str = "not_evaluated"
    quantitative_target_status_reason: str = ""

    def __post_init__(self) -> None:
        if self.definition_mode not in {"fixed", "dynamic"}:
            raise ValueError("definition_mode must be 'fixed' or 'dynamic'")
        if self.evidence_domain not in EVIDENCE_DOMAINS:
            raise ValueError(f"unknown evidence domain: {self.evidence_domain}")
        self.supplies_scope = self.supplies_scope.strip().lower()
        if self.supplies_scope and self.supplies_scope not in RUN_SCOPE_DIMENSIONS:
            raise ValueError(
                f"{self.name}: supplies_scope must be a run scope dimension, "
                f"got {self.supplies_scope!r}"
            )
        if self.quantitative_target_status not in QUANTITATIVE_TARGET_STATUSES:
            raise ValueError("invalid quantitative target status")
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.document_target = self.document_target.strip()
        self.target_resolution_reason = " ".join(
            self.target_resolution_reason.split()
        )
        self.quantitative_target_status_reason = " ".join(
            self.quantitative_target_status_reason.split()
        )
        self.document_spans = [
            span if isinstance(span, DocumentSpan) else DocumentSpan(**span)
            for span in self.document_spans
        ]
        if self.document_spans:
            self.document_target = " ".join(
                dict.fromkeys(span.quote for span in self.document_spans)
            )
            self.block_ids = [
                block_id
                for span in self.document_spans
                for block_id in span.block_ids
            ]
        self.block_ids = list(dict.fromkeys(self.block_ids))
        self.entities = list(dict.fromkeys(self.entities))
        self.quantitative_target_ids = list(dict.fromkeys(self.quantitative_target_ids))
        self.quantitative_statement_dispositions = list(
            {
                (item.quote, tuple(item.block_ids), item.disposition): item
                for item in self.quantitative_statement_dispositions
            }.values()
        )


@dataclass
class QueryIntent:
    """One search intent and the orthogonal coverage tracks that produced it.

    ``facets`` records the parts of this query the authoring stage already knew.
    They travel beside the text so a field-addressed source selects them instead
    of recovering them from prose. Searcher owns the shape; Scout does not define
    a parallel one.
    """

    text: str
    tracks: list[str] = field(default_factory=list)
    doc_block_ids: list[str] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)
    facets: QueryFacets = field(default_factory=QueryFacets)


@dataclass
class SearchTrace:
    """Deterministic record of one lane-native retrieval request."""

    attribute_ref: str
    lane: str
    query: str
    connector: str = ""
    operation: str = ""
    request_options: dict[str, str] = field(default_factory=dict)
    tracks: list[str] = field(default_factory=list)
    doc_block_ids: list[str] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)
    intent_ids: list[str] = field(default_factory=list)
    input_queries: list[str] = field(default_factory=list)
    applicability: str = "applicable"
    applicability_reason: str = ""
    status: str = "complete"  # complete | failed | skipped
    error: str = ""
    finding_count: int = 0
    source_urls: list[str] = field(default_factory=list)
    # Retrieved, then held out of this run because the source dated them before
    # the requested window. `source_urls` stays the complete retrieval record, so
    # these are a subset of it: what the window cost, not a separate search.
    # A finding the source left undated is never listed here, because an absent
    # date is not evidence of age.
    excluded_before_window: list[str] = field(default_factory=list)


def load_attributes(intervention_class: str) -> list[Attribute]:
    """Load attribute variables for an intervention class from shared vocabulary."""
    import yaml

    if not ATTRIBUTES_FILE.exists():
        raise LookupError(f"Shared attribute vocabulary missing: {ATTRIBUTES_FILE}")
    with open(ATTRIBUTES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get(intervention_class) or []
    return [
        Attribute(
            name=item["name"],
            description=item["description"],
            definition_mode="fixed",
            evidence_domain=item.get("evidence_domain", "general"),
            supplies_scope=item.get("supplies_scope", ""),
        )
        for item in items
    ]


@dataclass
class Insight:
    """One atomic factual observation from external evidence, source-attributed.

    Insight is what scout extracts from external Findings. Each Insight is
    a single statement backed by one or more supporting Findings.
    """

    statement: str
    supporting_findings: list[Finding] = field(default_factory=list)
    query: str = ""
    query_tracks: list[str] = field(default_factory=list)
    # Quantitative targets covered by the retrieval request, not a claim that
    # this insight semantically supports those targets.
    retrieval_target_ids: list[str] = field(default_factory=list)
    # Stable lineage key used by aggregate assessments. Derived from the atomic
    # statement, variable, and cited URLs; never supplied by the model.
    id: str = ""
    # Header (document provenance, stamped by pipeline) ---
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    attribute_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.refresh_id()

    def refresh_id(self) -> None:
        material = "\n".join(
            [
                self.attribute_ref or "",
                " ".join(self.statement.split()).lower(),
                *sorted(finding.url for finding in self.supporting_findings if finding.url),
            ]
        )
        self.id = "i-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


@dataclass
class Match:
    """Pairs an external-evidence Insight with its relation to the document.

    Match is the doc-aware primitive scout emits. Insight stays
    doc-agnostic - anyone wanting pure external evidence can still consume
    list[Insight] directly.
    """

    insight: Insight
    relation: str
    reason: str
    doc_block_ids: list[str] = field(default_factory=list)


@dataclass
class EvidenceAssessment:
    """Weight-of-evidence assessment for one investigation unit."""

    attribute_ref: str
    strength: str
    reason: str = ""
    # Read-only projection of the canonical Attribute binding for result/UI
    # locality; the evidence model cannot redefine it.
    doc_target: str = ""
    doc_block_ids: list[str] = field(default_factory=list)
    supporting_insight_ids: list[str] = field(default_factory=list)
    supporting_findings: list[Finding] = field(default_factory=list)


@dataclass
class PrecedentSignal:
    """Coverage and outcome of prior work for one document unit.

    These axes remain independent so direct precedent is not incorrectly read as
    favorable, and unfavorable history is not conflated with absence of precedent.
    """

    attribute_ref: str
    # Coverage and outcome are separate axes: a direct precedent can have a
    # favorable, mixed, or unfavorable history.
    precedent: str  # direct | adjacent | none | unknown
    outcome: str = "unknown"  # favorable | mixed | unfavorable | unknown
    reason: str = ""
    doc_block_ids: list[str] = field(default_factory=list)
    coverage_insight_ids: list[str] = field(default_factory=list)
    outcome_insight_ids: list[str] = field(default_factory=list)
    supporting_insight_ids: list[str] = field(default_factory=list)
    supporting_findings: list[Finding] = field(default_factory=list)


@dataclass
class SemanticSlot:
    """One explicit semantic value, including honest absence and catch-all states."""

    state: str = "unknown"
    value: str = ""
    other: str = ""

    def __post_init__(self) -> None:
        self.state = self.state.strip().lower()
        self.value = " ".join(self.value.split())
        self.other = " ".join(self.other.split())
        if self.state not in SEMANTIC_SLOT_STATES:
            raise ValueError(f"invalid semantic slot state: {self.state}")
        if self.state == "specified" and not self.value:
            raise ValueError("specified semantic slot requires a value")
        if self.state == "specified" and self.other:
            raise ValueError("specified semantic slot cannot carry other text")
        if self.state == "other" and not self.other:
            raise ValueError("other semantic slot requires an explanation")
        if self.state == "other" and self.value:
            raise ValueError("other semantic slot cannot carry a specified value")
        if self.state not in {"specified", "other"}:
            self.value = ""
            self.other = ""


@dataclass
class ComparisonRule:
    """One explicit admission rule for a quantitative semantic dimension.

    The semantic profile records what the document says. This rule separately
    records how broadly external evidence may vary and still be a direct
    comparator. Keeping those responsibilities distinct prevents a document's
    candidate name from silently becoming an exact-identity requirement.
    """

    mode: str
    scope: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        self.mode = self.mode.strip().lower()
        self.scope = " ".join(self.scope.split())
        self.reason = " ".join(self.reason.split())
        if self.mode not in COMPARISON_MATCH_MODES:
            raise ValueError(f"invalid comparison match mode: {self.mode}")
        if self.mode in {"exact", "compatible"} and not self.scope:
            raise ValueError(f"{self.mode} comparison rule requires a scope")
        if self.mode == "unconstrained" and self.scope:
            raise ValueError("unconstrained comparison rule cannot carry a scope")
        if self.mode == "unknown" and not self.reason:
            raise ValueError("unknown comparison rule requires a reason")


@dataclass
class TernaryDecision:
    """One auditable yes/no/unknown semantic decision made by the model."""

    state: str
    reason: str = ""

    def __post_init__(self) -> None:
        self.state = self.state.strip().lower()
        self.reason = " ".join(self.reason.split())
        if self.state not in TERNARY_DECISION_STATES:
            raise ValueError(f"invalid ternary decision state: {self.state}")
        if self.state != "yes" and not self.reason:
            raise ValueError("no and unknown decisions require a reason")


@dataclass
class SemanticDimensionAssessment:
    """Source meaning and its compatibility with one target dimension."""

    source: SemanticSlot
    compatibility: TernaryDecision

    def __post_init__(self) -> None:
        if not isinstance(self.source, SemanticSlot):
            self.source = SemanticSlot(**self.source)
        if not isinstance(self.compatibility, TernaryDecision):
            self.compatibility = TernaryDecision(**self.compatibility)


@dataclass
class MeasurementSemanticAssessment:
    """The complete semantic admission input for one source measurement."""

    source_ownership: TernaryDecision
    dimensions: dict[str, SemanticDimensionAssessment]

    def __post_init__(self) -> None:
        if not isinstance(self.source_ownership, TernaryDecision):
            self.source_ownership = TernaryDecision(**self.source_ownership)
        if set(self.dimensions) != set(QUANTITATIVE_SEMANTIC_FIELDS):
            raise ValueError(
                "semantic assessment requires every quantitative dimension"
            )
        self.dimensions = {
            field_name: (
                value
                if isinstance(value, SemanticDimensionAssessment)
                else SemanticDimensionAssessment(**value)
            )
            for field_name, value in self.dimensions.items()
        }


@dataclass
class EvidenceUnitIdentity:
    """Within-record identity used only to distinguish source comparison units."""

    status: str = "record_level"
    group: SemanticSlot = field(default_factory=SemanticSlot)
    cohort: SemanticSlot = field(default_factory=SemanticSlot)
    reason: str = "No finer source-supported evidence unit was identified."

    def __post_init__(self) -> None:
        self.status = self.status.strip().lower()
        if not isinstance(self.group, SemanticSlot):
            self.group = SemanticSlot(**self.group)
        if not isinstance(self.cohort, SemanticSlot):
            self.cohort = SemanticSlot(**self.cohort)
        self.reason = " ".join(self.reason.split())
        if self.status not in EVIDENCE_UNIT_STATUSES:
            raise ValueError("invalid evidence unit status")
        asserted = any(
            slot.state in {"specified", "other"}
            for slot in (self.group, self.cohort)
        )
        if self.status == "resolved" and not asserted:
            raise ValueError("resolved evidence unit requires a group or cohort")
        if self.status != "resolved" and asserted:
            raise ValueError("unresolved evidence unit cannot assert group or cohort")
        if not self.reason:
            raise ValueError("evidence unit requires a reason")


@dataclass
class NumericExpression:
    """One numeric statement, without any clinical interpretation.

    The same model-normalized shape represents document targets and external
    measurements. ``QuantitativeTarget`` and ``Measurement`` own the surrounding
    semantic meaning and provenance.
    """

    kind: str
    unit: str
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    comparator: str = ""

    def __post_init__(self) -> None:
        self.kind = self.kind.strip().lower()
        self.unit = self.unit.strip()
        self.comparator = self.comparator.strip()
        if self.kind not in MEASUREMENT_KINDS:
            raise ValueError(f"invalid numeric expression kind: {self.kind}")
        if self.kind not in {"other", "unknown"} and not self.unit:
            raise ValueError("numeric expression requires a unit")
        for field_name in ("value", "lower", "upper"):
            raw = getattr(self, field_name)
            if raw is not None:
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("numeric expression values must be finite")
                setattr(self, field_name, value)
        if self.kind in {"point_estimate", "count", "rate"}:
            if self.value is None or self.comparator:
                raise ValueError(f"{self.kind} requires value and no comparator")
        elif self.kind == "bound":
            if self.value is None or self.comparator not in {"=", ">", ">=", "<", "<="}:
                raise ValueError("bound requires value and a comparison operator")
        elif self.kind in {"range", "confidence_interval"}:
            if self.lower is None or self.upper is None or self.lower > self.upper:
                raise ValueError(f"{self.kind} requires ordered lower and upper values")
            if self.value is not None or self.comparator:
                raise ValueError(f"{self.kind} cannot carry value or comparator")
        elif self.comparator not in {"", "=", ">", ">=", "<", "<="}:
            raise ValueError("invalid numeric expression comparator")


def _default_semantic_profile() -> dict[str, SemanticSlot]:
    return {field_name: SemanticSlot() for field_name in QUANTITATIVE_SEMANTIC_FIELDS}


@dataclass(frozen=True)
class QuantitativeFieldLink:
    """One typed projection from a canonical target into a product field.

    The target itself has no field owner. A field may define the target,
    receive a constraint from it, or expose it as context without creating a
    second claim or calculation.
    """

    attribute_ref: str
    relation: str
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "attribute_ref", self.attribute_ref.strip())
        object.__setattr__(self, "relation", self.relation.strip().lower())
        object.__setattr__(self, "reason", " ".join(self.reason.split()))
        if not self.attribute_ref:
            raise ValueError("quantitative field link requires a field reference")
        if self.relation not in QUANTITATIVE_FIELD_LINK_RELATIONS:
            raise ValueError("invalid quantitative field-link relation")


@dataclass
class QuantitativeTarget:
    """One field-independent atomic document target with exact provenance."""

    expression: NumericExpression
    role: str
    quote: str
    doc_block_ids: list[str]
    field_links: list[QuantitativeFieldLink] = field(default_factory=list)
    semantic_profile: dict[str, SemanticSlot] = field(
        default_factory=_default_semantic_profile
    )
    comparison_contract: dict[str, ComparisonRule] = field(default_factory=dict)
    semantic_provenance: dict[str, list[DocumentSpan]] = field(default_factory=dict)
    provenance_spans: list[DocumentSpan] = field(default_factory=list)
    ai_recommendation: str = "flag"
    ai_review_reason: str = ""
    review_status: str = "approved"
    id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.expression, NumericExpression):
            self.expression = NumericExpression(**self.expression)
        self.role = self.role.strip().lower()
        if self.role not in {"threshold", "optimal", "other"}:
            raise ValueError("invalid quantitative target role")
        self.review_status = self.review_status.strip().lower()
        if self.review_status not in QUANTITATIVE_TARGET_REVIEW_STATUSES:
            raise ValueError("invalid quantitative target review status")
        self.ai_recommendation = self.ai_recommendation.strip().lower()
        if self.ai_recommendation not in QUANTITATIVE_TARGET_AI_RECOMMENDATIONS:
            raise ValueError("invalid quantitative target AI recommendation")
        self.ai_review_reason = " ".join(self.ai_review_reason.split())
        self.field_links = [
            value if isinstance(value, QuantitativeFieldLink) else QuantitativeFieldLink(**value)
            for value in self.field_links
        ]
        links_by_key = {
            (link.attribute_ref, link.relation): link for link in self.field_links
        }
        self.field_links = list(links_by_key.values())
        if not self.field_links or not any(
            link.relation in {"defines", "constrains"} for link in self.field_links
        ):
            raise ValueError(
                "quantitative target requires a defining or constraining field link"
            )
        if self.expression.kind != "bound":
            raise ValueError("quantitative target expression must be a bound")
        unknown_fields = set(self.semantic_profile) - set(
            QUANTITATIVE_SEMANTIC_FIELDS
        )
        if unknown_fields:
            raise ValueError("invalid quantitative semantic profile fields")
        self.semantic_profile = {
            field_name: (
                value
                if isinstance(value, SemanticSlot)
                else SemanticSlot(**value)
            )
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
            for value in [self.semantic_profile.get(field_name, SemanticSlot())]
        }
        if self.semantic_profile["measure"].state != "specified":
            raise ValueError("quantitative target requires a specified measure")
        if set(self.comparison_contract) != set(QUANTITATIVE_SEMANTIC_FIELDS):
            raise ValueError(
                "quantitative target requires one comparison rule per semantic dimension"
            )
        self.comparison_contract = {
            field_name: (
                value
                if isinstance(value, ComparisonRule)
                else ComparisonRule(**value)
            )
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
            for value in [self.comparison_contract[field_name]]
        }
        if self.comparison_contract["measure"].mode != "exact":
            raise ValueError("quantitative target measure comparison must be exact")
        self.semantic_provenance = {
            field_name: [
                span if isinstance(span, DocumentSpan) else DocumentSpan(**span)
                for span in self.semantic_provenance.get(field_name, [])
            ]
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
        if not self.provenance_spans:
            self.provenance_spans = [
                DocumentSpan(quote=self.quote, block_ids=self.doc_block_ids)
            ]
        else:
            self.provenance_spans = [
                span if isinstance(span, DocumentSpan) else DocumentSpan(**span)
                for span in self.provenance_spans
            ]
        self.doc_block_ids = list(
            dict.fromkeys(
                block_id
                for span in self.provenance_spans
                for block_id in span.block_ids
            )
        )
        self.quote = self.provenance_spans[0].quote
        if not self.id:
            semantic_material = [
                f"{field_name}:{slot.state}:{slot.value.casefold()}:{slot.other.casefold()}"
                for field_name, slot in self.semantic_profile.items()
            ]
            material = "\n".join(
                (
                    self.role,
                    self.expression.comparator,
                    str(self.expression.value),
                    self.expression.unit.casefold(),
                    *(
                        f"{field_name}:{rule.mode}:{rule.scope.casefold()}"
                        for field_name, rule in self.comparison_contract.items()
                    ),
                    *semantic_material,
                )
            )
            self.id = "qt-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    @property
    def value(self) -> float:
        assert self.expression.value is not None
        return self.expression.value

    @property
    def comparator(self) -> str:
        return self.expression.comparator

    @property
    def unit(self) -> str:
        return self.expression.unit

    @property
    def comparison_dimensions(self) -> list[str]:
        """Dimensions that constrain direct comparator admission."""
        return [
            field_name
            for field_name, rule in self.comparison_contract.items()
            if rule.mode != "unconstrained"
        ]

    @property
    def label(self) -> str:
        """Stable display/query summary derived from the canonical contract."""
        qualifiers = []
        for field_name in (
            "endpoint", "intervention", "population", "regimen", "time_horizon"
        ):
            slot = self.semantic_profile[field_name]
            if slot.state == "specified":
                qualifiers.append(slot.value)
            elif slot.state == "other":
                qualifiers.append(slot.other)
        measure = self.semantic_profile["measure"].value
        number = f"{self.value:g}{self.unit}"
        core = f"{measure} {self.comparator}{number}".strip()
        return " · ".join((core, *qualifiers))

    @property
    def attribute_refs(self) -> list[str]:
        """All fields linked to this claim, including contextual views."""
        return list(dict.fromkeys(link.attribute_ref for link in self.field_links))

    @property
    def analysis_attribute_refs(self) -> list[str]:
        """Fields this claim defines or constrains for retrieval and calibration."""
        return list(
            dict.fromkeys(
                link.attribute_ref
                for link in self.field_links
                if link.relation in {"defines", "constrains"}
            )
        )

@dataclass
class QuantitativeStatementDisposition:
    """A cited numeric-looking document statement intentionally not calibrated."""

    quote: str
    block_ids: list[str]
    disposition: str
    reason: str
    attribute_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.quote = " ".join(self.quote.split())
        self.block_ids = list(dict.fromkeys(self.block_ids))
        self.disposition = self.disposition.strip().lower()
        self.reason = " ".join(self.reason.split())
        self.attribute_refs = list(
            dict.fromkeys(value.strip() for value in self.attribute_refs if value.strip())
        )
        if self.disposition not in {
            "context_only",
            "non_scalar",
            "range_or_set",
            "uncertain",
        }:
            raise ValueError("invalid quantitative statement disposition")
        if not self.quote or not self.block_ids or not self.reason:
            raise ValueError("quantitative statement disposition requires cited reasoning")


#: Scope dimensions a run supplies once, for every intent it builds.
#:
#: A subset of `SCOPE_DIMENSIONS`, and the subset is the point. `text` is an intent's
#: own subject, `population` and `outcome` vary between the queries of one intent, and
#: `product` narrows a single request - none of them is a property of the run. These
#: four are, so a run states them once and every intent inherits them.
RUN_SCOPE_DIMENSIONS = ("condition", "intervention", "region")


#: The scope_ref for intents that belong to the run rather than to one variable.
#:
#: `findings_by_attribute` is keyed by `scope_ref`, and an insight naming a scope that is
#: not a real attribute already raises, so this key cannot leak into per-variable
#: reasoning by accident. It reaches the development landscape instead, which groups by
#: program name and ignores attributes entirely.
PROGRAM_SCOPE_KEY = "program"


@dataclass(frozen=True)
class ProgramQuerySet:
    """One question about the run rather than about any one variable."""

    #: Event subjects, as things to search for rather than as recency words. The query
    #: extractor is forbidden from writing "recent" or a year because an index reads
    #: those as terms to match; the same rule holds here, so an announcement is reached
    #: by naming the kind of event, not by asking for newness.
    subjects: tuple[str, ...]
    #: Lanes this set is planned against, and why only these.
    lanes: tuple[str, ...]
    reason: str


#: Query sets that belong to the run, with the test each one had to pass.
#:
#: The test: **does the answer change if you ask it about a different variable?** If yes,
#: the question is per-variable and belongs to an attribute's tracks. If no, it belongs
#: here. That test is what keeps this from becoming a bucket for anything that feels
#: broad.
#:
#: Deliberately rejected, each for the same reason - the answer does change per variable:
#:
#:     competitor sweep    ClinicalTrials receives an identical request for every
#:                         attribute, so it looks run-level. But the provider is hit once
#:                         and each attribute ranks the same candidates against its own
#:                         queries, so the twenty it keeps differ. Per-variable.
#:     regulatory approvals Same shape, same reason.
#:     precedent           It is the precedent for one variable, not for the program.
#:     safety signals      Driven by each attribute's own stated entities.
PROGRAM_QUERY_SETS = {
    "burden": ProgramQuerySet(
        # No subject to name. The lane's request is built from the run's condition alone,
        # so the set exists to say which lane runs and at what scope rather than to
        # supply query text.
        subjects=(),
        lanes=("who_gho",),
        reason=(
            "How much of the disease there is does not change with the variable being "
            "read, so it is asked once for the run. The lane is reached only from here: "
            "planned per attribute it would repeat one answer for every variable, and "
            "each repetition costs two provider calls."
        ),
    ),
    "events": ProgramQuerySet(
        subjects=(
            "phase 3 trial results",
            "regulatory approval decision",
            "clinical trial readout",
            "licensing or development partnership",
        ),
        lanes=("web",),
        reason=(
            "Only the web lane can reach an announcement. The registries already receive "
            "this program's sweep once per attribute, and a literature index does not "
            "hold press releases, so planning this set against them would repeat one "
            "request and add nothing."
        ),
    ),
}


#: How many queries each coverage track gets per variable, and why that many.
#:
#: One table rather than four numbers repeated in every config. All eleven configs held
#: the identical split with nothing stating it, so the balance was a coincidence eleven
#: files agreed on rather than a decision anyone could review or change once.
#:
#: The tracks are additive, never substituted, so these are shares of attention rather
#: than a budget being divided. The shape follows what the tool is for: find what is
#: known, then whether it holds where the programme is aimed, then whether it holds at
#: all, then whether it has been tried before.
#:
#:     general        8  The baseline, and the only track that must cover the variable's
#:                       core question across content, source and language at once. Half
#:                       again the next largest, because every other track qualifies what
#:                       this one establishes.
#:     geographic     6  The stated mission. Raised above a token share because it is now
#:                       informed by the document's own region rather than a fixed list,
#:                       so its queries are about where this programme actually is.
#:     counterfactual 4  The check that stops an optimistic reading. A competitive
#:                       assessment that only finds supporting evidence reads as a strong
#:                       position, and it is the one failure the reader cannot see.
#:     precedent      3  Prior attempts. Real value and the least time-sensitive of the
#:                       four, so it takes the smallest share.
#:
#: A config may override any of these; nothing does today. Overriding one is a statement
#: that a document type needs a different balance, which is exactly when a number should
#: live in a config rather than here.
QUERY_TRACK_BUDGET = {
    "general": 8,
    "geographic": 6,
    "counterfactual": 4,
    "precedent": 3,
}


@dataclass(frozen=True)
class ScopeEntry:
    """One scope dimension's value for a run, and where the value came from."""

    dimension: str
    value: str = ""
    provenance: str = "unset"
    #: Blocks a document-derived value is traceable to. Required for `document`, for the
    #: same reason `QuantitativeLedgerReview` requires a quote: a value read out of a
    #: document that cannot be pointed at is indistinguishable from one invented.
    block_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", self.dimension.strip())
        object.__setattr__(self, "value", " ".join(self.value.split()))
        object.__setattr__(self, "provenance", self.provenance.strip().lower())
        if self.dimension not in RUN_SCOPE_DIMENSIONS:
            raise ValueError(f"not a run scope dimension: {self.dimension!r}")
        if self.provenance not in SCOPE_PROVENANCE:
            raise ValueError(f"unknown scope provenance: {self.provenance!r}")
        if self.provenance == "unset" and self.value:
            raise ValueError(
                f"{self.dimension}: a value with no supplier cannot be recorded as unset"
            )
        if self.provenance != "unset" and not self.value:
            raise ValueError(
                f"{self.dimension}: {self.provenance} supplied no value; record it unset"
            )
        if self.provenance == "document" and not self.block_ids:
            raise ValueError(
                f"{self.dimension}: a document-derived value must cite its blocks"
            )
        if self.provenance != "document" and self.block_ids:
            raise ValueError(
                f"{self.dimension}: only a document-derived value cites blocks"
            )


@dataclass(frozen=True)
class RetrievalScopeLedger:
    """The one authoritative statement of what a run is about.

    The sibling of `QuantitativeLedger`, and deliberately separate from it. That one
    holds what the document claims numerically and is read by the stages that judge;
    this one holds what the run is searching for and is read by the stage that builds
    intents. Getting a number wrong produces a wrong verdict on the right evidence.
    Getting the scope wrong produces a confident verdict on the wrong evidence.

    Every dimension in `RUN_SCOPE_DIMENSIONS` has an entry, including the ones nothing
    supplies. An absent entry and an unset one are the same value and opposite facts:
    one is a dimension nobody has wired, the other is a reader deliberately widening the
    search. Requiring the entry is what makes the first case visible.
    """

    entries: tuple[ScopeEntry, ...] = ()

    def __post_init__(self) -> None:
        by_dimension = {entry.dimension: entry for entry in self.entries}
        if len(by_dimension) != len(self.entries):
            raise ValueError("retrieval scope ledger states a dimension twice")
        missing = [d for d in RUN_SCOPE_DIMENSIONS if d not in by_dimension]
        if missing:
            raise ValueError(
                f"retrieval scope ledger omits: {', '.join(missing)}. Record an unset "
                "entry rather than leaving the dimension out."
            )

    @classmethod
    def of(
        cls,
        **supplied: tuple[str, str] | tuple[str, str, tuple[str, ...]],
    ) -> "RetrievalScopeLedger":
        """Build a complete ledger from the dimensions a caller can supply.

        Each value is `(value, provenance)`, or `(value, provenance, block_ids)` when a
        document supplied it. Anything not named is recorded `unset`, so a caller cannot
        half-fill a ledger and a new dimension shows up as unsupplied rather than absent.
        """
        entries = []
        for dimension in RUN_SCOPE_DIMENSIONS:
            stated = supplied.get(dimension, ("", "unset"))
            value, provenance = stated[0], stated[1]
            block_ids = stated[2] if len(stated) > 2 else ()
            entries.append(
                ScopeEntry(
                    dimension=dimension,
                    value=value,
                    provenance=provenance,
                    block_ids=tuple(block_ids),
                )
            )
        return cls(entries=tuple(entries))

    def entry(self, dimension: str) -> ScopeEntry:
        for entry in self.entries:
            if entry.dimension == dimension:
                return entry
        raise KeyError(f"not a run scope dimension: {dimension!r}")

    def value(self, dimension: str) -> str:
        return self.entry(dimension).value

    def supplied(self) -> tuple[str, ...]:
        """Dimensions with a supplier, in declared order."""
        return tuple(
            entry.dimension for entry in self.entries if entry.provenance != "unset"
        )


@dataclass
class QuantitativeLedgerReview:
    """One non-overlapping document statement reviewed by the numeric ledger."""

    unit_id: str
    block_id: str
    quote: str
    classification: str
    reason: str
    attribute_refs: list[str] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)
    review_status: str = "resolved"

    def __post_init__(self) -> None:
        self.unit_id = self.unit_id.strip()
        self.block_id = self.block_id.strip()
        self.quote = " ".join(self.quote.split())
        self.classification = self.classification.strip().lower()
        self.reason = " ".join(self.reason.split())
        self.attribute_refs = list(
            dict.fromkeys(value.strip() for value in self.attribute_refs if value.strip())
        )
        self.target_ids = list(dict.fromkeys(self.target_ids))
        self.review_status = self.review_status.strip().lower()
        if self.review_status not in QUANTITATIVE_STATEMENT_REVIEW_STATUSES:
            raise ValueError("invalid quantitative statement review status")
        if self.classification not in QUANTITATIVE_REVIEW_CLASSIFICATIONS:
            raise ValueError("invalid quantitative ledger classification")
        if not self.unit_id or not self.block_id or not self.quote or not self.reason:
            raise ValueError("quantitative ledger review requires traced reasoning")
        if (
            self.classification in {"target", "partial_target"}
            and not self.target_ids
        ):
            raise ValueError("target ledger review requires at least one target")
        if self.classification not in {"target", "partial_target"} and self.target_ids:
            raise ValueError("non-target ledger review cannot reference targets")
        if self.classification == "partial_target" and self.review_status == "resolved":
            raise ValueError("partial target review requires an explicit decision")


@dataclass
class QuantitativeLedger:
    """The one authoritative document-first numeric interpretation for a run."""

    status: str = "not_applicable"
    reason: str = ""
    block_ids: list[str] = field(default_factory=list)
    reviews: list[QuantitativeLedgerReview] = field(default_factory=list)
    targets: list[QuantitativeTarget] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = self.status.strip().lower()
        self.reason = " ".join(self.reason.split())
        self.block_ids = list(dict.fromkeys(self.block_ids))
        if self.status not in QUANTITATIVE_LEDGER_STATUSES:
            raise ValueError("invalid quantitative ledger status")
        review_ids = [review.unit_id for review in self.reviews]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("quantitative ledger contains duplicate statement units")
        target_ids = [target.id for target in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("quantitative ledger contains duplicate targets")


@dataclass
class IndicatorReading:
    """One place's reading of one indicator, as the provider stated it."""

    place: str
    spatial_type: str
    year: int
    value: float | None = None
    value_text: str = ""
    parent_place: str = ""


@dataclass
class BurdenIndicator:
    """One health indicator and every reading retrieved for it.

    The third projection, beside `DevelopmentProgram` and `SafetyObservation`, and grouped
    the same way: by the thing itself rather than by the variable that happened to
    retrieve it. A reader asking how much malaria there is wants one row per indicator
    with its places beneath, not the same indicator repeated under every attribute.

    Deliberately not summarised. No total across countries, no average, no most-recent
    single number - each of those is an answer to a question the reader did not ask, and
    a total over an incomplete set of countries is worse than the set.
    """

    indicator_code: str
    indicator_name: str
    projection_id: str = ""
    readings: list[IndicatorReading] = field(default_factory=list)
    attribute_refs: list[str] = field(default_factory=list)
    supporting_findings: list[Finding] = field(default_factory=list)

    @property
    def latest_year(self) -> int | None:
        """The most recent year any place reported, for ordering and for a heading."""
        years = [reading.year for reading in self.readings]
        return max(years) if years else None

    @property
    def place_count(self) -> int:
        return len({reading.place for reading in self.readings})


@dataclass
class Measurement:
    """One source's reported numeric value for a quantitative document unit.

    The exact expression, semantic mapping, and source quote are the complete
    cohort input. Presentation-only source labels are intentionally not copied
    into this calculation contract.
    """

    expression: NumericExpression
    semantic_assessment: MeasurementSemanticAssessment
    candidate_id: str = ""
    url: str = ""
    insight_id: str = ""
    source_quote: str = ""
    source_record_id: str = ""
    source_identity_status: str = "url_fallback"
    evidence_unit_id: str = ""
    evidence_unit: EvidenceUnitIdentity = field(default_factory=EvidenceUnitIdentity)
    semantic_status: str = "unknown"
    semantic_reason: str = ""
    evidence_mode: str = "prose"
    ai_recommendation: str = "flag"
    ai_review_reason: str = ""
    admission_status: str = "needs_review"
    admission_reason: str = ""
    inclusion_reason: str = ""
    exclusion_reasons: list[str] = field(default_factory=list)
    age_months: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.expression, NumericExpression):
            self.expression = NumericExpression(**self.expression)
        if not isinstance(self.semantic_assessment, MeasurementSemanticAssessment):
            self.semantic_assessment = MeasurementSemanticAssessment(
                **self.semantic_assessment
            )
        if not isinstance(self.evidence_unit, EvidenceUnitIdentity):
            self.evidence_unit = EvidenceUnitIdentity(**self.evidence_unit)
        if not self.evidence_unit_id:
            self.evidence_unit_id = self.source_record_id
        if self.semantic_status not in MEASUREMENT_STATUSES:
            raise ValueError("invalid measurement semantic status")
        if self.evidence_mode not in MEASUREMENT_EVIDENCE_MODES:
            raise ValueError("invalid measurement evidence mode")
        if self.ai_recommendation not in MEASUREMENT_AI_RECOMMENDATIONS:
            raise ValueError("invalid measurement AI recommendation")
        if self.admission_status not in MEASUREMENT_ADMISSION_STATUSES:
            raise ValueError("invalid measurement admission status")
        self.ai_review_reason = " ".join(self.ai_review_reason.split())
        self.admission_reason = " ".join(self.admission_reason.split())

    @property
    def value(self) -> float | None:
        return self.expression.value

    @property
    def unit(self) -> str:
        return self.expression.unit

    @property
    def expression_kind(self) -> str:
        return self.expression.kind


SOURCE_VERDICTS = frozenset({
    "measurements_found",
    "no_relevant_measurement",
    "uncertain",
})


@dataclass
class SourcePassageDisposition:
    """Auditable outcome for one source-owned passage considered for a target.

    ``status`` carries one of two different kinds of claim. The three members of
    ``SOURCE_VERDICTS`` are what the model concluded about the source and are the
    only values its schema permits. ``not_assessed`` is owned by this pipeline and
    states that no usable conclusion was obtained, so a processing gap can never
    be read as evidentiary ambiguity. ``failure_code`` names that gap for
    machines and is present on exactly the ``not_assessed`` records.
    """

    source_id: str
    status: str
    reason: str
    url: str = ""
    insight_id: str = ""
    failure_code: str = ""

    def __post_init__(self) -> None:
        if self.status not in SOURCE_VERDICTS | {"not_assessed"}:
            raise ValueError("invalid source passage disposition")
        self.reason = " ".join(self.reason.split())
        if not self.source_id or not self.reason:
            raise ValueError("source disposition requires an ID and reason")
        if (self.status == "not_assessed") != bool(self.failure_code):
            raise ValueError(
                "a failure code belongs to exactly the not_assessed dispositions"
            )


@dataclass
class ConformityScore:
    """Traceable descriptive calibration of one quantitative target.

    Produced once per document-owned target when sources report comparable
    numbers (e.g. efficacy >= 80%). AI maps exact source spans into the shared
    semantic contract; deterministic validation owns cohort inclusion,
    study-level deduplication, and all calculations.
    """

    attribute_refs: list[str]
    target_id: str
    target_role: str
    target_value: float
    comparator: str  # "=", ">", ">=", "<", or "<="
    unit: str
    target_meeting_count: int
    target_meeting_rate: float  # 0..1 unweighted observed share
    verdict: str
    target_quote: str = ""
    # Descriptive calibration over validated, claim-compatible measurements.
    # These are observed cohort statistics, not inferential uncertainty or a
    # forecast probability.
    benchmark_count: int = 0
    benchmark_minimum: float | None = None
    benchmark_maximum: float | None = None
    benchmark_mean: float | None = None
    benchmark_median: float | None = None
    benchmark_lower_quartile: float | None = None
    benchmark_upper_quartile: float | None = None
    benchmark_standard_deviation: float | None = None
    target_percentile: float | None = None  # raw percentile among benchmarks
    ambition_percentile: float | None = None  # 1.0 = more demanding target
    calibration_status: str = "insufficient"
    target_label: str = ""  # which target was scored (e.g. "adult threshold <=1.0 mL")
    doc_block_ids: list[str] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    excluded_measurements: list[Measurement] = field(default_factory=list)
    source_dispositions: list[SourcePassageDisposition] = field(default_factory=list)


@dataclass
class FunnelStats:
    queries: int
    findings: int
    unique_findings: int
    insights: int
    matches: int
    assessments: int
    #: Announcements read for a program name, and how many named one.
    #:
    #: A pair, because the second number alone is unreadable. An announcement that names
    #: no program leaves no row in the landscape, so without the count of attempts a weak
    #: reading and a quiet week look identical. Defaulted so a saved result from before
    #: this existed still loads.
    announcements_read: int = 0
    announcements_named: int = 0


@dataclass
class DevelopmentProgram:
    """Deterministic grouping of source-normalized development records."""

    name: str
    projection_id: str = ""
    source_role: str = "unknown"
    target_relationship: str = "unknown"
    target_relationship_reason: str = ""
    sponsors: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    record_types: list[str] = field(default_factory=list)
    record_ids: list[str] = field(default_factory=list)
    attribute_refs: list[str] = field(default_factory=list)
    supporting_findings: list[Finding] = field(default_factory=list)


@dataclass
class SafetyObservation:
    """Deterministic grouping of one source-owned safety observation."""

    product_name: str
    record_type: str
    source_system: str
    label: str
    projection_id: str = ""
    source_role: str = "unknown"
    target_relationship: str = "unknown"
    target_relationship_reason: str = ""
    detail: str = ""
    report_count: int | None = None
    qualification: str = ""
    attribute_refs: list[str] = field(default_factory=list)
    supporting_findings: list[Finding] = field(default_factory=list)


@dataclass
class DocumentContextValidation:
    """Pre-retrieval check that configured indication matches the document."""

    status: str
    configured_indication: str
    document_indication: str = ""
    reason: str = ""
    doc_block_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in VALID_CONTEXT_STATUSES:
            raise ValueError(f"unknown document context status: {self.status}")
        self.configured_indication = self.configured_indication.strip()
        self.document_indication = self.document_indication.strip()
        self.reason = self.reason.strip()
        self.doc_block_ids = list(dict.fromkeys(self.doc_block_ids))


@dataclass
class ScoutResult:
    matches: list[Match]
    assessments: list[EvidenceAssessment]
    stats: FunnelStats
    context_validation: DocumentContextValidation
    quantitative_ledger: QuantitativeLedger = field(default_factory=QuantitativeLedger)
    conformity: list[ConformityScore] = field(default_factory=list)
    precedents: list[PrecedentSignal] = field(default_factory=list)
    search_plan: list[SearchTrace] = field(default_factory=list)
    development_landscape: list[DevelopmentProgram] = field(default_factory=list)
    safety_observations: list[SafetyObservation] = field(default_factory=list)
    #: Disease-burden readings retrieved for the run. Defaulted so a result saved before
    #: this projection existed still loads.
    burden_indicators: list[BurdenIndicator] = field(default_factory=list)
    # Canonical, document-bound units actually investigated this run. Consumers
    # read this rather than re-deriving provider-specific definitions.
    variables: list[Attribute] = field(default_factory=list)
    # The parsed source document (ordered, citable blocks). Carried so downstream
    # consumers (e.g. the Ask assistant) can read the full document behind the
    # distilled analysis. Not used by the analysis itself.
    blocks: list["ContentBlock"] = field(default_factory=list)
    phase: str = "final"  # target_review | evidence_review | final
    # ISO date the user scoped retrieval to, or "" for no window. Recorded on the
    # result because every statistic below describes the cohort this admitted:
    # a benchmark read without knowing its window answers a different question
    # than the one asked.
    published_since: str = ""

    def __post_init__(self) -> None:
        if self.phase not in {"target_review", "evidence_review", "final"}:
            raise ValueError("invalid Scout result phase")
        self.published_since = self.published_since.strip()
        if self.published_since:
            try:
                date.fromisoformat(self.published_since)
            except ValueError as exc:
                raise ValueError(
                    "published_since must be an ISO date (YYYY-MM-DD)"
                ) from exc


@dataclass
class ScoutTypeConfig:
    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    query_extraction_guidance: str
    sources: list[str]
    queries_per_variable: int = QUERY_TRACK_BUDGET["general"]
    priority_institutions: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    geographic_emphasis: list[str] = field(default_factory=list)
    geographic_queries_per_variable: int = QUERY_TRACK_BUDGET["geographic"]
    counterfactual_queries_per_variable: int = QUERY_TRACK_BUDGET["counterfactual"]
    precedent_queries_per_variable: int = QUERY_TRACK_BUDGET["precedent"]
    # Where the units to investigate come from:
    #   "vocabulary" - the fixed shared attribute list (TPP).
    #   "extract"    - an LLM pulls units (claims/targets) from the document (e.g. IPDP).
    # Engines downstream are unit-agnostic; only this switch differs per doc type.
    unit_provider: str = "vocabulary"
    # Doc-type interpretive stance injected into the reasoning prompts: how to
    # read this document's units (a TPP's aspirational targets vs an IPDP's plan
    # commitments). One per reasoning layer that needs it. Empty => the engine's
    # generic, doc-agnostic fallback. May use {intervention_class} / {indication}.
    drift_framing: str = ""
    evidence_framing: str = ""
    quantitative_target_framing: str = ""
    precedent_framing: str = ""

    @property
    def intervention_term(self) -> str:
        """The class as it reads inside a query or a prompt sentence.

        `intervention_class` itself is an identity, not prose: it selects this file,
        keys the attribute vocabulary, is checked against `type_key`, and is stamped on
        every block as provenance. So the text form is derived on read rather than
        stored beside it, for the same reason a count is — a second field could disagree
        with the one the configuration was selected by.

        Derived here as well as normalised in the pipeline because the value reaches
        text by two routes: stages that receive it as an argument get the pipeline's,
        and stages holding a config read it from here. Both call `search_term`, so the
        two routes cannot produce different words.
        """
        return search_term(self.intervention_class)


def matches_to_dicts(matches: list[Match]) -> list[dict]:
    """Convert Match objects to plain dictionaries (Insight nested, datetimes ISO)."""
    out: list[dict] = []
    for match in matches:
        d = {
            "insight": asdict(match.insight),
            "relation": match.relation,
            "reason": match.reason,
            "doc_block_ids": match.doc_block_ids,
        }
        for finding in d["insight"]["supporting_findings"]:
            if finding.get("retrieved_at") is not None and not isinstance(
                finding["retrieved_at"], str
            ):
                finding["retrieved_at"] = finding["retrieved_at"].isoformat()
            if finding.get("published_at") is not None and not isinstance(
                finding["published_at"], str
            ):
                finding["published_at"] = finding["published_at"].isoformat()
        out.append(d)
    return out


def assessments_to_dicts(assessments: list[EvidenceAssessment]) -> list[dict]:
    """Convert EvidenceAssessment objects to plain dictionaries."""
    out: list[dict] = []
    for assessment in assessments:
        d = asdict(assessment)
        for finding in d["supporting_findings"]:
            if finding.get("retrieved_at") is not None and not isinstance(
                finding["retrieved_at"], str
            ):
                finding["retrieved_at"] = finding["retrieved_at"].isoformat()
            if finding.get("published_at") is not None and not isinstance(
                finding["published_at"], str
            ):
                finding["published_at"] = finding["published_at"].isoformat()
        out.append(d)
    return out


def conformity_to_dicts(scores: list[ConformityScore]) -> list[dict]:
    """Convert ConformityScore objects to plain dictionaries."""
    return [asdict(score) for score in scores]


def precedents_to_dicts(signals: list[PrecedentSignal]) -> list[dict]:
    """Convert PrecedentSignal objects to plain dictionaries (datetimes ISO)."""
    out: list[dict] = []
    for signal in signals:
        d = asdict(signal)
        for finding in d["supporting_findings"]:
            if finding.get("retrieved_at") is not None and not isinstance(
                finding["retrieved_at"], str
            ):
                finding["retrieved_at"] = finding["retrieved_at"].isoformat()
            if finding.get("published_at") is not None and not isinstance(
                finding["published_at"], str
            ):
                finding["published_at"] = finding["published_at"].isoformat()
        out.append(d)
    return out


def development_programs_to_dicts(
    programs: list[DevelopmentProgram],
) -> list[dict]:
    """Convert development projections to plain dictionaries."""
    return [_serialize_finding_datetimes(asdict(program)) for program in programs]


def safety_observations_to_dicts(
    observations: list[SafetyObservation],
) -> list[dict]:
    """Convert safety projections to plain dictionaries."""
    return [
        _serialize_finding_datetimes(asdict(observation))
        for observation in observations
    ]


def burden_indicators_to_dicts(indicators: list[BurdenIndicator]) -> list[dict]:
    """Convert burden projections to plain dictionaries."""
    return [
        _serialize_finding_datetimes(asdict(indicator)) for indicator in indicators
    ]


def _serialize_finding_datetimes(value: dict) -> dict:
    for finding in value.get("supporting_findings", []):
        if finding.get("retrieved_at") is not None and not isinstance(
            finding["retrieved_at"], str
        ):
            finding["retrieved_at"] = finding["retrieved_at"].isoformat()
        if finding.get("published_at") is not None and not isinstance(
            finding["published_at"], str
        ):
            finding["published_at"] = finding["published_at"].isoformat()
    return value


def blocks_to_dicts(blocks: list["ContentBlock"]) -> list[dict]:
    """Convert the parsed source ContentBlocks to plain dictionaries."""
    return [asdict(block) for block in blocks]


def load_config(config_path: str) -> ScoutTypeConfig:
    """Load a ScoutTypeConfig from YAML."""
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping")

    required = {
        "type_key",
        "org",
        "source_type",
        "intervention_class",
        "display_name",
        "query_extraction_guidance",
        "sources",
    }
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Config missing required fields: {', '.join(sorted(missing))}")

    priority_institutions = data.get("priority_institutions", []) or []
    modalities = data.get("modalities", []) or []
    languages = data.get("languages", []) or []
    geographic_emphasis = data.get("geographic_emphasis", []) or []
    sources = data.get("sources", []) or []
    if not isinstance(priority_institutions, list) or not all(
        isinstance(institution, str) for institution in priority_institutions
    ):
        raise ValueError("priority_institutions must be a list of strings")
    if not isinstance(modalities, list) or not all(
        isinstance(modality, str) for modality in modalities
    ):
        raise ValueError("modalities must be a list of strings")
    if not isinstance(languages, list) or not all(
        isinstance(language, str) for language in languages
    ):
        raise ValueError("languages must be a list of strings")
    if not isinstance(geographic_emphasis, list) or not all(
        isinstance(emphasis, str) for emphasis in geographic_emphasis
    ):
        raise ValueError("geographic_emphasis must be a list of strings")
    if not isinstance(sources, list) or not sources or not all(
        isinstance(source, str) for source in sources
    ):
        raise ValueError("sources must be a non-empty list of registered source keys")
    unknown_sources = sorted(set(sources) - set(source_keys()))
    if unknown_sources:
        raise ValueError(f"Unknown Scout source(s): {', '.join(unknown_sources)}")
    geographic_queries_per_variable = int(
        data.get("geographic_queries_per_variable", QUERY_TRACK_BUDGET["geographic"])
    )
    if geographic_queries_per_variable < 0:
        raise ValueError("geographic_queries_per_variable must be >= 0")
    counterfactual_queries_per_variable = int(
        data.get("counterfactual_queries_per_variable", QUERY_TRACK_BUDGET["counterfactual"])
    )
    if counterfactual_queries_per_variable < 0:
        raise ValueError("counterfactual_queries_per_variable must be >= 0")
    precedent_queries_per_variable = int(
        data.get("precedent_queries_per_variable", QUERY_TRACK_BUDGET["precedent"])
    )
    if precedent_queries_per_variable < 0:
        raise ValueError("precedent_queries_per_variable must be >= 0")
    unit_provider = str(data.get("unit_provider", "vocabulary")).strip().lower()
    if unit_provider not in {"vocabulary", "extract"}:
        raise ValueError("unit_provider must be 'vocabulary' or 'extract'")
    queries_per_variable = int(
        data.get("queries_per_variable", QUERY_TRACK_BUDGET["general"])
    )
    if queries_per_variable < 0:
        raise ValueError("queries_per_variable must be >= 0")
    framing_fields = (
        "drift_framing",
        "evidence_framing",
        "quantitative_target_framing",
        "precedent_framing",
    )
    framings = {field_name: data.get(field_name, "") or "" for field_name in framing_fields}
    if not all(isinstance(value, str) for value in framings.values()):
        raise ValueError(f"{', '.join(framing_fields)} must be strings")

    return ScoutTypeConfig(
        type_key=data["type_key"],
        org=data["org"],
        source_type=data["source_type"],
        intervention_class=data["intervention_class"],
        display_name=data["display_name"],
        query_extraction_guidance=data["query_extraction_guidance"],
        sources=list(dict.fromkeys(sources)),
        queries_per_variable=queries_per_variable,
        priority_institutions=priority_institutions,
        modalities=modalities,
        languages=languages,
        geographic_emphasis=geographic_emphasis,
        geographic_queries_per_variable=geographic_queries_per_variable,
        counterfactual_queries_per_variable=counterfactual_queries_per_variable,
        precedent_queries_per_variable=precedent_queries_per_variable,
        unit_provider=unit_provider,
        drift_framing=framings["drift_framing"].strip(),
        evidence_framing=framings["evidence_framing"].strip(),
        quantitative_target_framing=framings["quantitative_target_framing"].strip(),
        precedent_framing=framings["precedent_framing"].strip(),
    )
