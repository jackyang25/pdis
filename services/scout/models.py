"""Scout data shapes, config, and the LLM client contracts it requires.

Public types live here - re-exported by __init__.py. Consumers import
from `services.scout`, never from this module directly.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from services.searcher import Finding, source_keys

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


@dataclass
class Attribute:
    """One investigation unit, from a vocabulary or extracted document claim."""

    name: str
    description: str
    # Populated when the unit is extracted from a document; vocabulary units
    # intentionally have no document provenance until a target is located.
    block_ids: list[str] = field(default_factory=list)


@dataclass
class QueryIntent:
    """One search intent and the orthogonal coverage tracks that produced it."""

    text: str
    tracks: list[str] = field(default_factory=list)
    doc_block_ids: list[str] = field(default_factory=list)


@dataclass
class SearchTrace:
    """Deterministic record of one lane-native retrieval request."""

    attribute_ref: str
    lane: str
    query: str
    tracks: list[str] = field(default_factory=list)
    doc_block_ids: list[str] = field(default_factory=list)
    status: str = "complete"  # complete | failed
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
        Attribute(name=item["name"], description=item["description"])
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
    doc_target: str = ""  # what the uploaded document states for this field
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
class Measurement:
    """One source's reported numeric value for a quantitative document unit.

    Feeds the conformity combiner. Study design, development phase, and
    source-record type are separate AI-labeled axes; deterministic config
    converts them to a reliability weight. Publication date drives recency.
    """

    value: float
    # Explicitly carried so the calculator never silently combines values with
    # incompatible units. `value` is in this unit and must match the target unit.
    unit: str = ""
    evidence_form: str = "other"
    development_phase: str = "unknown"
    source_record_type: str = "unknown"
    url: str = ""
    insight_id: str = ""
    age_months: float | None = None
    weight: float = 0.0


@dataclass
class ConformityScore:
    """Combined weight-of-evidence that a quantitative target is met.

    Produced only for variables where sources report comparable numbers
    against a doc-stated target (e.g. efficacy >= 80%). A transparent,
    reproducible alternative to the LLM's qualitative verdict: each source's
    value is weighted by reliability + recency and combined.
    """

    attribute_ref: str
    target_value: float
    comparator: str  # ">=" or "<="
    unit: str
    conformity: float  # 0..1 weighted directional alignment score
    lower: float
    upper: float
    verdict: str
    target_label: str = ""  # which target was scored (e.g. "adult threshold <=1.0 mL")
    doc_block_ids: list[str] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)


@dataclass
class FunnelStats:
    queries: int
    findings: int
    unique_findings: int
    insights: int
    matches: int
    assessments: int


@dataclass
class ScoutResult:
    matches: list[Match]
    assessments: list[EvidenceAssessment]
    stats: FunnelStats
    conformity: list[ConformityScore] = field(default_factory=list)
    precedents: list[PrecedentSignal] = field(default_factory=list)
    search_plan: list[SearchTrace] = field(default_factory=list)
    # The units actually investigated this run - the fixed vocabulary (TPP) or
    # the doc-extracted units (IPDP). Consumers read this rather than re-deriving
    # from the shared vocabulary, which would be wrong for the extract provider.
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
    priority_sources: list[str] = field(default_factory=list)
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

    priority_sources = data.get("priority_sources", []) or []
    modalities = data.get("modalities", []) or []
    languages = data.get("languages", []) or []
    geographic_emphasis = data.get("geographic_emphasis", []) or []
    sources = data.get("sources", []) or []
    if not isinstance(priority_sources, list) or not all(
        isinstance(source, str) for source in priority_sources
    ):
        raise ValueError("priority_sources must be a list of strings")
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
        priority_sources=priority_sources,
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
