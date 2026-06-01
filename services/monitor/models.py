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
VALID_RELATIONS = {"contradicts", "extends", "confirms", "unrelated"}


def find_config(org: str, source_type: str, intervention_class: str) -> "MonitorTypeConfig":
    """Load the monitor config for the given (org, source_type, intervention)."""
    path = CONFIGS_DIR / f"{org}_{source_type}_{intervention_class}.yaml"
    if not path.exists():
        raise LookupError(
            f"No monitor config for ({org}, {source_type}, {intervention_class}). "
            f"Expected: {path}"
        )
    return load_config(str(path))


class OpenAIClientProtocol(Protocol):
    """Contract for monitor's text-LLM stages (query + insight extraction)."""

    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        ...


class SearchClientProtocol(Protocol):
    """Contract for monitor's web-search calls (delegated to searcher)."""

    def search_web(self, query: str, *, max_tokens: int, max_uses: int) -> Any:
        ...


@dataclass
class Insight:
    """One atomic factual observation from the web, source-attributed.

    Symmetric in spirit to `Claim` (which benchmarker extracts from docs):
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
    section_label: str | None = None


@dataclass
class Match:
    """Pairs an Insight (pure web evidence) with its relation to the document.

    Match is the doc-aware primitive monitor emits. Insight stays
    doc-agnostic - anyone wanting pure web evidence can still consume
    list[Insight] directly. When benchmarker integration lands later,
    Match will optionally gain a claim_id pointing at the specific doc
    Claim involved in the comparison; nothing else changes.
    """

    insight: Insight
    relation: str
    reason: str


@dataclass
class MonitorTypeConfig:
    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    query_extraction_guidance: str
    queries_per_section: int = 1


def insights_to_dicts(insights: list[Insight]) -> list[dict]:
    """Convert Insight objects to plain dictionaries (Findings included nested)."""
    out: list[dict] = []
    for ins in insights:
        d = asdict(ins)
        # Datetimes in supporting_findings -> ISO strings
        for f in d["supporting_findings"]:
            if f.get("retrieved_at") is not None and not isinstance(f["retrieved_at"], str):
                f["retrieved_at"] = f["retrieved_at"].isoformat()
            if f.get("published_at") is not None and not isinstance(f["published_at"], str):
                f["published_at"] = f["published_at"].isoformat()
        out.append(d)
    return out


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

    return MonitorTypeConfig(
        type_key=data["type_key"],
        org=data["org"],
        source_type=data["source_type"],
        intervention_class=data["intervention_class"],
        display_name=data["display_name"],
        query_extraction_guidance=data["query_extraction_guidance"],
        queries_per_section=int(data.get("queries_per_section", 1)),
    )
