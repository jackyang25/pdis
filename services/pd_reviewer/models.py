from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml


class LLMClientProtocol(Protocol):
    """Contract pd_reviewer requires from any injected LLM client."""
    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        ...


Grade = Literal["A", "B", "C", "D", "F", "N/A"]


@dataclass
class VariableGrade:
    """Grade for a single variable inside Executive Summary or Additional Variables."""

    variable_name: str
    grade: Grade
    issues: list[str]
    recommendation: str
    block_ids: list[str]


@dataclass
class SectionGrade:
    """Grade for a top-level section."""

    section_name: str
    grade: Grade
    is_present: bool
    missing_variables: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    recommendation: str = ""
    variable_grades: list[VariableGrade] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Full report card."""

    doc_id: str
    overall_grade: Grade
    top_issues: list[str]
    section_grades: list[SectionGrade]

    # --- Header (document provenance, stamped by pipeline) ---
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    therapeutic_area: str | None = None


@dataclass
class BatchReviewResult:
    """Per-document result of review_blocks_batch."""

    doc_key: str
    review: ReviewResult | None = None
    error: str | None = None


@dataclass
class VariableSpec:
    """Rubric expectations for one variable within a section."""

    name: str
    description: str


@dataclass
class SectionSpec:
    """Rubric expectations for one section."""

    name: str
    description: str
    weight: float
    variables: list[VariableSpec] = field(default_factory=list)


@dataclass
class ReviewConfig:
    """All document-type-specific configuration for PD Reviewer."""

    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    sections: list[SectionSpec]


CONFIGS_DIR = Path(__file__).resolve().parent / "configs"


def find_config(org: str, source_type: str, intervention_class: str) -> "ReviewConfig | None":
    """Load the pd_reviewer config for the given triple. Returns None if not found
    (pd_reviewer rubrics are optional per triple)."""
    path = CONFIGS_DIR / f"{org}_{source_type}_{intervention_class}.yaml"
    if not path.exists():
        return None
    return load_review_config(str(path))


def load_review_config(path: str) -> ReviewConfig:
    """Load a ReviewConfig from YAML. Validates required fields."""
    config_path = Path(path).expanduser().resolve()
    with open(config_path, "r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)

    if not isinstance(data, dict):
        raise ValueError("PD Reviewer config file must contain a YAML mapping")

    required_fields = {
        "type_key",
        "org",
        "source_type",
        "intervention_class",
        "display_name",
        "sections",
    }
    missing_fields = required_fields - data.keys()
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"PD Reviewer config missing required fields: {missing}")

    _validate_string_field(data, "type_key")
    _validate_string_field(data, "org")
    _validate_string_field(data, "source_type")
    _validate_string_field(data, "intervention_class")
    _validate_string_field(data, "display_name")
    sections = _parse_sections(data["sections"])

    return ReviewConfig(
        type_key=data["type_key"],
        org=data["org"],
        source_type=data["source_type"],
        intervention_class=data["intervention_class"],
        display_name=data["display_name"],
        sections=sections,
    )


def review_result_to_dict(result: ReviewResult) -> dict[str, Any]:
    """Convert a ReviewResult to JSON-serializable dictionaries."""
    return asdict(result)


def _resolve_path(config_path: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path

    config_dir = config_path.parent
    package_root = config_dir.parent
    candidates = [
        config_dir / path,
        package_root / path,
        package_root.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[1].resolve()


def _validate_string_field(data: dict[str, Any], field_name: str) -> None:
    if not isinstance(data[field_name], str) or not data[field_name].strip():
        raise ValueError(f"PD Reviewer config field '{field_name}' must be a string")


def _parse_sections(value: Any) -> list[SectionSpec]:
    if not isinstance(value, list):
        raise ValueError("sections must be a list")

    sections: list[SectionSpec] = []
    seen_names: set[str] = set()
    for index, section_data in enumerate(value):
        if not isinstance(section_data, dict):
            raise ValueError(f"sections[{index}] must be a mapping")
        _validate_string_field(section_data, "name")
        _validate_string_field(section_data, "description")
        _validate_weight(section_data.get("weight"), f"sections[{index}].weight")

        section_name = section_data["name"]
        if section_name in seen_names:
            raise ValueError(f"Duplicate section name: {section_name}")
        seen_names.add(section_name)

        sections.append(
            SectionSpec(
                name=section_name,
                description=section_data["description"],
                weight=float(section_data["weight"]),
                variables=_parse_variables(section_data.get("variables", []), index),
            )
        )

    if not sections:
        raise ValueError("sections must contain at least one section")
    return sections


def _parse_variables(value: Any, section_index: int) -> list[VariableSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"sections[{section_index}].variables must be a list")

    variables: list[VariableSpec] = []
    seen_names: set[str] = set()
    for index, variable_data in enumerate(value):
        if not isinstance(variable_data, dict):
            raise ValueError(
                f"sections[{section_index}].variables[{index}] must be a mapping"
            )
        _validate_string_field(variable_data, "name")
        _validate_string_field(variable_data, "description")

        variable_name = variable_data["name"]
        if variable_name in seen_names:
            raise ValueError(
                f"Duplicate variable name in sections[{section_index}]: {variable_name}"
            )
        seen_names.add(variable_name)

        variables.append(
            VariableSpec(
                name=variable_name,
                description=variable_data["description"],
            )
        )
    return variables


def _validate_weight(value: Any, field_name: str) -> None:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
