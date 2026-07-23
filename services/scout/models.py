"""Scout data shapes, config, and the LLM client contracts it requires.

Public types live here - re-exported by __init__.py. Consumers import
from `services.scout`, never from this module directly.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from services.searcher import EVIDENCE_DOMAINS, ENTITY_TYPES, Finding, source_keys

if TYPE_CHECKING:
    from services.chunker import ContentBlock


CONFIGS_DIR = Path(__file__).resolve().parent / "configs"
ATTRIBUTES_FILE = Path(__file__).resolve().parents[2] / "shared" / "attributes.yaml"
VALID_RELATIONS = {"contradicts", "extends", "confirms", "unrelated"}
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
    """Contract for scout's text-LLM stages (query + insight + drift).

    Capability-named, not provider-named: any client exposing `call(...)`
    satisfies it. The concrete client (OpenAIClient today) is injected.
    """

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        images: list[dict[str, str]] | None = None,
    ) -> str:
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
    # The only intentional TPP/IPDP distinction: how the definition was
    # supplied. All downstream stages consume the same bound shape.
    definition_mode: str = "fixed"  # fixed | dynamic
    # Distinguishes an intentionally absent target from a unit not yet bound to
    # its document. Runtime pipeline units are always resolved before search.
    target_resolved: bool = False
    evidence_domain: str = "general"
    entities: list[EvidenceEntity] = field(default_factory=list)
    # Independently qualified numeric claims extracted once before retrieval.
    # Qualitative stages continue to use the canonical document_target binding.
    quantitative_targets: list["QuantitativeTarget"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.definition_mode not in {"fixed", "dynamic"}:
            raise ValueError("definition_mode must be 'fixed' or 'dynamic'")
        if self.evidence_domain not in EVIDENCE_DOMAINS:
            raise ValueError(f"unknown evidence domain: {self.evidence_domain}")
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.document_target = self.document_target.strip()
        self.block_ids = list(dict.fromkeys(self.block_ids))
        self.entities = list(dict.fromkeys(self.entities))
        self.quantitative_targets = list(
            {target.id: target for target in self.quantitative_targets}.values()
        )


@dataclass
class QueryIntent:
    """One search intent and the orthogonal coverage tracks that produced it."""

    text: str
    tracks: list[str] = field(default_factory=list)
    doc_block_ids: list[str] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)


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
class QuantitativeTarget:
    """One exact, independently calibratable numeric statement from a document."""

    attribute_ref: str
    value: float
    comparator: str
    unit: str
    label: str
    role: str
    quote: str
    doc_block_ids: list[str]
    id: str = ""

    def __post_init__(self) -> None:
        # JSON, Pydantic, and Python callers may represent the same number as
        # either ``80`` or ``80.0``. Normalize before deriving identity so a
        # portable round trip cannot change the target ID.
        self.value = float(self.value)
        if not self.id:
            material = "\n".join(
                (
                    self.attribute_ref,
                    self.role,
                    self.comparator,
                    str(self.value),
                    self.unit,
                    " ".join(self.quote.split()),
                    *self.doc_block_ids,
                )
            )
            self.id = "qt-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


@dataclass
class AxisEvidence:
    """Closed comparability label with validated target/source span references."""

    relation: str = "unknown"
    reason: str = ""
    target_span_ids: list[str] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    target_quotes: list[str] = field(default_factory=list)
    source_quotes: list[str] = field(default_factory=list)


@dataclass
class Measurement:
    """One source's reported numeric value for a quantitative document unit.

    Feeds the quantitative cohort builder. Evidence form, development phase,
    and source-record type remain separate descriptive axes; they do not alter
    the observed cohort statistics.
    """

    value: float
    candidate_id: str = ""
    # Explicitly carried so the calculator never silently combines values with
    # incompatible units. `value` is in this unit and must match the target unit.
    unit: str = ""
    evidence_form: str = "other"
    development_phase: str = "unknown"
    source_record_type: str = "unknown"
    url: str = ""
    insight_id: str = ""
    source_quote: str = ""
    source_record_id: str = ""
    source_identity_status: str = "url_fallback"
    # Closed claim-comparability axes. Values are same | compatible |
    # not_applicable | different | unknown. Reasons retain the model's narrow
    # explanation, while deterministic code owns cohort inclusion.
    comparability: dict[str, str] = field(default_factory=dict)
    comparability_reasons: dict[str, str] = field(default_factory=dict)
    axis_evidence: dict[str, AxisEvidence] = field(default_factory=dict)
    inclusion_reason: str = ""
    exclusion_reasons: list[str] = field(default_factory=list)
    age_months: float | None = None


@dataclass
class ConformityScore:
    """Traceable descriptive calibration of one quantitative target.

    Produced only for variables where sources report comparable numbers
    against a doc-stated target (e.g. efficacy >= 80%). AI proposes exact
    source spans and closed comparability labels; deterministic validation owns
    cohort inclusion, study-level deduplication, and all calculations.
    """

    attribute_ref: str
    target_id: str
    target_role: str
    target_value: float
    comparator: str  # ">", ">=", "<", or "<="
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


@dataclass
class FunnelStats:
    queries: int
    findings: int
    unique_findings: int
    insights: int
    matches: int
    assessments: int


@dataclass
class DevelopmentProgram:
    """Deterministic grouping of source-normalized development records."""

    name: str
    sponsors: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    record_types: list[str] = field(default_factory=list)
    record_ids: list[str] = field(default_factory=list)
    attribute_refs: list[str] = field(default_factory=list)
    supporting_findings: list[Finding] = field(default_factory=list)


@dataclass
class SafetySignal:
    """Deterministic grouping of one product safety observation."""

    product_name: str
    signal_type: str
    signal: str
    detail: str = ""
    count: int | None = None
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
    conformity: list[ConformityScore] = field(default_factory=list)
    precedents: list[PrecedentSignal] = field(default_factory=list)
    search_plan: list[SearchTrace] = field(default_factory=list)
    development_landscape: list[DevelopmentProgram] = field(default_factory=list)
    safety_signals: list[SafetySignal] = field(default_factory=list)
    # Canonical, document-bound units actually investigated this run. Consumers
    # read this rather than re-deriving provider-specific definitions.
    variables: list[Attribute] = field(default_factory=list)
    # The parsed source document (ordered, citable blocks). Carried so downstream
    # consumers (e.g. the Ask assistant) can read the full document behind the
    # distilled analysis. Not used by the analysis itself.
    blocks: list["ContentBlock"] = field(default_factory=list)


@dataclass
class ScoutTypeConfig:
    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    query_extraction_guidance: str
    sources: list[str]
    queries_per_variable: int = 1
    priority_institutions: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    geographic_emphasis: list[str] = field(default_factory=list)
    geographic_queries_per_variable: int = 0
    counterfactual_queries_per_variable: int = 0
    precedent_queries_per_variable: int = 0
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
    conformity_framing: str = ""
    precedent_framing: str = ""


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


def safety_signals_to_dicts(signals: list[SafetySignal]) -> list[dict]:
    """Convert safety projections to plain dictionaries."""
    return [_serialize_finding_datetimes(asdict(signal)) for signal in signals]


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
    geographic_queries_per_variable = int(data.get("geographic_queries_per_variable", 0))
    if geographic_queries_per_variable < 0:
        raise ValueError("geographic_queries_per_variable must be >= 0")
    counterfactual_queries_per_variable = int(data.get("counterfactual_queries_per_variable", 0))
    if counterfactual_queries_per_variable < 0:
        raise ValueError("counterfactual_queries_per_variable must be >= 0")
    precedent_queries_per_variable = int(data.get("precedent_queries_per_variable", 0))
    if precedent_queries_per_variable < 0:
        raise ValueError("precedent_queries_per_variable must be >= 0")
    unit_provider = str(data.get("unit_provider", "vocabulary")).strip().lower()
    if unit_provider not in {"vocabulary", "extract"}:
        raise ValueError("unit_provider must be 'vocabulary' or 'extract'")
    queries_per_variable = int(data.get("queries_per_variable", 1))
    if queries_per_variable < 0:
        raise ValueError("queries_per_variable must be >= 0")
    framing_fields = ("drift_framing", "evidence_framing", "conformity_framing", "precedent_framing")
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
        conformity_framing=framings["conformity_framing"].strip(),
        precedent_framing=framings["precedent_framing"].strip(),
    )
