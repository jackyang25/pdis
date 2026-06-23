"""Monitor data shapes, config, and the LLM client contracts it requires.

Public types live here - re-exported by __init__.py. Consumers import
from `services.monitor`, never from this module directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from services.searcher import Finding


CONFIGS_DIR = Path(__file__).resolve().parent / "configs"
ATTRIBUTES_FILE = Path(__file__).resolve().parents[2] / "shared" / "attributes.yaml"
VALID_RELATIONS = {"contradicts", "extends", "confirms", "unrelated"}
VALID_EVIDENCE_STRENGTHS = {
    "well_grounded",
    "partial",
    "thin",
    "unsupported",
    "unknown",
}
VALID_EVIDENCE_BASIS = {
    "standard_of_care",
    "modeling",
    "study_strength",
    "regulatory_precedent",
}


def find_config(org: str, source_type: str, intervention_class: str) -> "MonitorTypeConfig":
    """Load the monitor config for the given (org, source_type, intervention)."""
    path = CONFIGS_DIR / f"{org}_{source_type}_{intervention_class}.yaml"
    if not path.exists():
        raise LookupError(
            f"No monitor config for ({org}, {source_type}, {intervention_class}). "
            f"Expected: {path}"
        )
    return load_config(str(path))


class LLMClientProtocol(Protocol):
    """Contract for monitor's text-LLM stages (query + insight + drift).

    Capability-named, not provider-named: any client exposing `call(...)`
    satisfies it. The concrete client (OpenAIClient today) is injected.
    """

    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        ...


class SearchClientProtocol(Protocol):
    """Contract for monitor's web-search calls (delegated to searcher)."""

    def search_web(self, query: str, *, max_tokens: int, max_uses: int) -> Any:
        ...


@dataclass
class Attribute:
    """One TPP attribute variable from the shared vocabulary."""

    name: str
    description: str


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
    """One atomic factual observation from the web, source-attributed.

    Insight is what monitor extracts from web Findings. Each Insight is
    a single statement backed by one or more supporting Findings.
    """

    statement: str
    supporting_findings: list[Finding] = field(default_factory=list)
    query: str = ""
    # Header (document provenance, stamped by pipeline) ---
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None
    attribute_ref: str | None = None


@dataclass
class Match:
    """Pairs an Insight (pure web evidence) with its relation to the document.

    Match is the doc-aware primitive monitor emits. Insight stays
    doc-agnostic - anyone wanting pure web evidence can still consume
    list[Insight] directly.
    """

    insight: Insight
    relation: str
    reason: str


@dataclass
class EvidenceAssessment:
    """Weight-of-evidence assessment for one TPP attribute variable."""

    attribute_ref: str
    strength: str
    basis: list[str] = field(default_factory=list)
    reason: str = ""
    supporting_findings: list[Finding] = field(default_factory=list)


@dataclass
class Measurement:
    """One source's reported numeric value for a quantitative TPP variable.

    Feeds the conformity combiner. `source_type` selects the reliability
    weight; `age_months` (from the finding's publish date) drives recency.
    """

    value: float
    source_type: str
    url: str = ""
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
    conformity: float  # 0..1 combined probability the target is met
    lower: float
    upper: float
    verdict: str
    target_label: str = ""  # which target was scored (e.g. "adult threshold <=1.0 mL")
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
class MonitorResult:
    matches: list[Match]
    assessments: list[EvidenceAssessment]
    stats: FunnelStats
    conformity: list[ConformityScore] = field(default_factory=list)


@dataclass
class MonitorTypeConfig:
    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    query_extraction_guidance: str
    queries_per_variable: int = 1
    priority_sources: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    geographic_emphasis: list[str] = field(default_factory=list)
    geographic_queries_per_variable: int = 0


def matches_to_dicts(matches: list[Match]) -> list[dict]:
    """Convert Match objects to plain dictionaries (Insight nested, datetimes ISO)."""
    out: list[dict] = []
    for match in matches:
        d = {
            "insight": asdict(match.insight),
            "relation": match.relation,
            "reason": match.reason,
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


def load_config(config_path: str) -> MonitorTypeConfig:
    """Load a MonitorTypeConfig from YAML."""
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
    }
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Config missing required fields: {', '.join(sorted(missing))}")

    priority_sources = data.get("priority_sources", []) or []
    modalities = data.get("modalities", []) or []
    languages = data.get("languages", []) or []
    geographic_emphasis = data.get("geographic_emphasis", []) or []
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
    geographic_queries_per_variable = int(data.get("geographic_queries_per_variable", 0))
    if geographic_queries_per_variable < 0:
        raise ValueError("geographic_queries_per_variable must be >= 0")

    return MonitorTypeConfig(
        type_key=data["type_key"],
        org=data["org"],
        source_type=data["source_type"],
        intervention_class=data["intervention_class"],
        display_name=data["display_name"],
        query_extraction_guidance=data["query_extraction_guidance"],
        queries_per_variable=int(data.get("queries_per_variable", 1)),
        priority_sources=priority_sources,
        modalities=modalities,
        languages=languages,
        geographic_emphasis=geographic_emphasis,
        geographic_queries_per_variable=geographic_queries_per_variable,
    )
