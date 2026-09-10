"""Strict Inspector profile and rubric catalog loading.

Profiles decide which independently-authored rubrics are candidates for a document
context. Rubrics decide assessment meaning. Keeping these separate lets Chunker's
document taxonomy remain the parse authority while guideline reviews use the whole
document as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

from .models import InspectionConfig, ProductFact, load_inspection_config

ResolutionStatus = Literal["included", "outside_review_scope", "needs_context"]
PRODUCT_FACT_KEYS = ("small_molecule", "systemic_exposure", "antiarrhythmic")
PRODUCT_FACT_VALUES = ("yes", "no", "unknown")

CONFIGS_DIR = Path(__file__).resolve().parent / "configs"
PROFILES_PATH = CONFIGS_DIR / "profiles" / "catalog.yaml"
RUBRICS_DIR = CONFIGS_DIR / "rubrics"


@dataclass(frozen=True)
class FactDefinition:
    key: str
    label: str
    description: str
    options: list[str] = field(default_factory=lambda: list(PRODUCT_FACT_VALUES))
    required: bool = False


@dataclass(frozen=True)
class RubricSource:
    id: str
    title: str
    revision: str
    url: str


@dataclass(frozen=True)
class RubricDefinition:
    id: str
    revision: str
    display_name: str
    authority: str
    scope: str
    evidence_scope: Literal["mapped_section", "whole_document"]
    sources: list[RubricSource]
    config: InspectionConfig
    reference_url: str | None = None


@dataclass(frozen=True)
class RubricReference:
    id: str
    revision: str
    definition: str
    applicability: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class InspectionProfile:
    org: str
    source_type: str
    intervention_class: str
    document_config: str
    rubrics: list[RubricReference]
    fact_definitions: list[FactDefinition] = field(default_factory=list)


@dataclass(frozen=True)
class RubricResolution:
    rubric_id: str
    display_name: str
    status: ResolutionStatus
    reason_code: str
    reason: str
    required_facts: list[str] = field(default_factory=list)
    rubric: RubricDefinition | None = field(default=None, repr=False, compare=False)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def _nonempty(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{key} must be non-empty text")
    return value.strip()


def load_rubric(path: str | Path, *, profile: InspectionProfile | None = None) -> RubricDefinition:
    path = Path(path)
    data = _load_yaml(path)
    where = f"rubric {path.name}"
    reference_url = data.get("reference_url")
    if reference_url is not None and (
        not isinstance(reference_url, str)
        or urlparse(reference_url).scheme not in {"https", "http"}
        or not urlparse(reference_url).netloc
    ):
        raise ValueError(f"{where}.reference_url must be an HTTP(S) URL")
    evidence_scope = _nonempty(data, "evidence_scope", where)
    if evidence_scope not in {"mapped_section", "whole_document"}:
        raise ValueError(f"{where}.evidence_scope is invalid")
    sources_data = data.get("sources")
    if not isinstance(sources_data, list):
        raise ValueError(f"{where}.sources must be a list")
    sources = [
        RubricSource(
            id=_nonempty(item, "id", f"{where}.sources[{index}]"),
            title=_nonempty(item, "title", f"{where}.sources[{index}]"),
            revision=_nonempty(item, "revision", f"{where}.sources[{index}]"),
            url=_nonempty(item, "url", f"{where}.sources[{index}]"),
        )
        for index, item in enumerate(sources_data)
        if isinstance(item, dict)
    ]
    if len(sources) != len(sources_data) or len({s.id for s in sources}) != len(sources):
        raise ValueError(f"{where}.sources must be mappings with unique IDs")
    if evidence_scope == "whole_document" and not sources:
        raise ValueError(f"{where} whole_document rubrics must declare sources")
    source_ids = {source.id for source in sources}
    config_file = data.get("config_file")
    if data.get("config_from_profile") is True:
        if profile is None:
            raise ValueError(f"{where} requires a profile document config")
        config = load_inspection_config(str(CONFIGS_DIR / profile.document_config))
    elif config_file is not None:
        if not isinstance(config_file, str) or not config_file.strip():
            raise ValueError(f"{where}.config_file must be non-empty text")
        config = load_inspection_config(str(CONFIGS_DIR / config_file))
    else:
        config_data = dict(data)
        config_data.setdefault("type_key", _nonempty(data, "id", where))
        config = _inspection_config_from_data(config_data, path)
    if profile is not None:
        config = replace(
            config, org=profile.org, source_type=profile.source_type,
            intervention_class=profile.intervention_class,
        )
    config = replace(config, evidence_scope=evidence_scope)
    for section in config.sections:
        units = section.variables or [section]
        for unit in units:
            refs = getattr(unit, "source_refs", [])
            if any(ref not in source_ids for ref in refs):
                raise ValueError(f"{where} requirement {unit.name!r} has invalid source_refs")
            if (sources or evidence_scope == "whole_document") and not refs:
                raise ValueError(f"{where} requirement {unit.name!r} has invalid source_refs")
    display_name = (
        config.display_name
        if data.get("display_name_from_config") is True
        else _nonempty(data, "display_name", where)
    )
    return RubricDefinition(
        id=_nonempty(data, "id", where),
        revision=_nonempty(data, "revision", where),
        display_name=display_name,
        authority=_nonempty(data, "authority", where),
        scope=_nonempty(data, "scope", where),
        evidence_scope=evidence_scope,  # type: ignore[arg-type]
        sources=sources,
        config=config,
        reference_url=reference_url,
    )


def _inspection_config_from_data(data: dict[str, Any], path: Path) -> InspectionConfig:
    """Use a temporary in-memory-equivalent parser via the model's strict helpers."""
    from .models import parse_inspection_config

    return parse_inspection_config(data, source=str(path))


def load_profiles() -> list[InspectionProfile]:
    data = _load_yaml(PROFILES_PATH)
    entries = data.get("profiles")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Inspector profile catalog must contain profiles")
    facts = [
        FactDefinition(
            key=_nonempty(item, "key", f"facts[{index}]"),
            label=_nonempty(item, "label", f"facts[{index}]"),
            description=_nonempty(item, "description", f"facts[{index}]"),
        )
        for index, item in enumerate(data.get("fact_definitions", []))
    ]
    if tuple(item.key for item in facts) != PRODUCT_FACT_KEYS:
        raise ValueError("Inspector fact definitions must declare the three product facts in order")
    profiles: list[InspectionProfile] = []
    identities: set[tuple[str, str, str]] = set()
    for index, item in enumerate(entries):
        where = f"profiles[{index}]"
        identity = tuple(_nonempty(item, key, where) for key in ("org", "source_type", "intervention_class"))
        if identity in identities:
            raise ValueError(f"duplicate Inspector profile {identity}")
        identities.add(identity)
        references = item.get("rubrics")
        if not isinstance(references, list) or not references:
            raise ValueError(f"{where}.rubrics must be non-empty")
        refs = []
        for ref_index, ref in enumerate(references):
            ref_where = f"{where}.rubrics[{ref_index}]"
            applicability = ref.get("applicability", {})
            if not isinstance(applicability, dict) or any(
                key not in PRODUCT_FACT_KEYS or not isinstance(values, list)
                or not values or any(value not in PRODUCT_FACT_VALUES for value in values)
                for key, values in applicability.items()
            ):
                raise ValueError(f"{ref_where}.applicability is invalid")
            refs.append(RubricReference(
                _nonempty(ref, "id", ref_where), _nonempty(ref, "revision", ref_where),
                _nonempty(ref, "definition", ref_where), applicability,
            ))
        used_facts = {key for ref in refs for key in ref.applicability}
        profile = InspectionProfile(*identity, _nonempty(item, "document_config", where), refs, [fact for fact in facts if fact.key in used_facts])
        document_config = load_inspection_config(str(CONFIGS_DIR / profile.document_config))
        if (document_config.org, document_config.source_type, document_config.intervention_class) != identity:
            raise ValueError(f"{where}.document_config identity does not match its profile")
        if document_config.type_key != "_".join(identity):
            raise ValueError(f"{where}.document_config type_key does not match its identity")
        if len({ref.id for ref in refs}) != len(refs):
            raise ValueError(f"{where}.rubrics contains duplicate IDs")
        # Load all pinned references now: a malformed catalog is never partial availability.
        for ref in refs:
            rubric = load_rubric(RUBRICS_DIR / ref.definition, profile=profile)
            if rubric.id != ref.id or rubric.revision != ref.revision:
                raise ValueError(f"profile pins {ref.id}@{ref.revision}, found {rubric.revision}")
        profiles.append(profile)
    return profiles


def find_profile(org: str, source_type: str, intervention_class: str) -> InspectionProfile:
    for profile in load_profiles():
        if (profile.org, profile.source_type, profile.intervention_class) == (org, source_type, intervention_class):
            return profile
    raise LookupError(f"No Inspector profile for ({org}, {source_type}, {intervention_class})")


def available_configs() -> list[InspectionConfig]:
    """Document-template configs referenced by profiles, in authored order."""
    return [
        load_inspection_config(str(CONFIGS_DIR / profile.document_config))
        for profile in load_profiles()
    ]


def has_config(org: str, source_type: str, intervention_class: str) -> bool:
    """Whether the catalog declares this input; malformed catalogs still raise."""
    return any(
        (profile.org, profile.source_type, profile.intervention_class)
        == (org, source_type, intervention_class)
        for profile in load_profiles()
    )


def find_config(org: str, source_type: str, intervention_class: str) -> InspectionConfig:
    """Load the profile's template rubric without deriving a path from input keys."""
    profile = find_profile(org, source_type, intervention_class)
    return load_inspection_config(str(CONFIGS_DIR / profile.document_config))


def available_rubric_configs() -> list[InspectionConfig]:
    """Effective non-document-mapped rubric configs for prompt documentation.

    Profiles are the enumeration authority; the metadata-only BMGF definition is
    therefore never mistaken for a standalone document configuration.
    """
    configs: list[InspectionConfig] = []
    for profile in load_profiles():
        for ref in profile.rubrics:
            rubric = _rubric_for(profile, ref)
            if rubric.evidence_scope == "whole_document":
                configs.append(rubric.config)
    return configs


def _rubric_for(profile: InspectionProfile, ref: RubricReference) -> RubricDefinition:
    return load_rubric(RUBRICS_DIR / ref.definition, profile=profile)


def validate_product_facts(facts: dict[str, Any] | None) -> dict[str, ProductFact]:
    facts = facts or {}
    unexpected = set(facts) - set(PRODUCT_FACT_KEYS)
    if unexpected:
        raise ValueError(f"unexpected Inspector applicability facts: {', '.join(sorted(unexpected))}")
    validated: dict[str, ProductFact] = {}
    for key, value in facts.items():
        if value not in PRODUCT_FACT_VALUES:
            raise ValueError(f"{key} must be yes, no, or unknown")
        validated[key] = value
    return validated


def resolve_profile(profile: InspectionProfile, facts: dict[str, Any] | None) -> list[RubricResolution]:
    validated = validate_product_facts(facts)
    resolved: list[RubricResolution] = []
    for ref in profile.rubrics:
        rubric = _rubric_for(profile, ref)
        if not ref.applicability:
            status, code, reason, required = "included", "profile_match", "Included by the selected document profile.", []
        else:
            required = [key for key in ref.applicability if validated.get(key) in {None, "unknown"}]
            outside = [key for key, allowed in ref.applicability.items() if validated.get(key) not in {None, "unknown"} and validated[key] not in allowed]
            if outside:
                status, code, reason, required = "outside_review_scope", "facts_outside_implemented_scope", "The confirmed product facts fall outside this rubric's implemented review scope.", []
            elif required:
                status, code, reason = "needs_context", "applicability_facts_unresolved", "Explicit product facts are required before this review can be included."
            else:
                status, code, reason, required = "included", "applicability_confirmed", "The explicit product facts match this rubric's implemented review scope.", []
        resolved.append(RubricResolution(rubric.id, rubric.display_name, status, code, reason, required, rubric))
    return resolved


def profile_catalog(profile: InspectionProfile) -> dict[str, Any]:
    return {
        "org": profile.org,
        "source_type": profile.source_type,
        "intervention_class": profile.intervention_class,
        "applicability_facts": [
            {"key": item.key, "label": item.label, "description": item.description, "options": item.options, "required": item.required}
            for item in profile.fact_definitions
        ],
    }
