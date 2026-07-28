from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import yaml

if TYPE_CHECKING:
    from services.chunker import ContentBlock


class LLMClientProtocol(Protocol):
    """Contract Inspector requires from any injected LLM client."""
    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: str = "reasoning",
    ) -> dict[str, Any] | None:
        ...


Grade = Literal["A", "B", "C", "D", "F", "N/A"]
Dimension = Literal["completeness", "adherence", "rigor"]
ConsistencyStatus = Literal["complete", "partial", "failed", "not_applicable", "unknown"]
GradingStatus = Literal["complete", "unknown"]
DIMENSIONS: tuple[Dimension, ...] = ("completeness", "adherence", "rigor")


@dataclass
class DimensionGrade:
    """A grade along one of three orthogonal axes.

    - completeness: are all required variables present/filled in?
    - adherence:    does the draft follow the rubric's structural expectations?
    - rigor:        is the content substantively sound - specific, measurable,
                    and meaningful (not just present and well-formatted)?

    Same shape at every level (variable, section, document). The LLM
    produces these at the variable level; section and document grades
    are mechanical roll-ups.
    """

    grade: Grade
    issues: list[str] = field(default_factory=list)
    recommendation: str = ""


def _empty_dimensions() -> dict[str, DimensionGrade]:
    return {d: DimensionGrade(grade="N/A") for d in DIMENSIONS}


@dataclass
class VariableGrade:
    """Atomic graded unit: one rubric variable, three dimension grades."""

    variable_name: str
    dimensions: dict[str, DimensionGrade] = field(default_factory=_empty_dimensions)
    block_ids: list[str] = field(default_factory=list)


@dataclass
class SectionGrade:
    """One rubric section. Dimension grades are rolled up from variables
    (variable-bearing sections) or graded directly by the LLM (prose sections)."""

    section_name: str
    is_present: bool = True
    dimensions: dict[str, DimensionGrade] = field(default_factory=_empty_dimensions)
    missing_variables: list[str] = field(default_factory=list)
    variable_grades: list[VariableGrade] = field(default_factory=list)


@dataclass
class CrossSectionFinding:
    """A consistency problem that spans MORE THAN ONE section.

    Produced by the whole-document consistency pass - the one place that sees
    all sections at once. Per-section grading cannot catch these by design
    (sections are graded in isolation), so this is doc-level, not attached to
    any single section's dimension grade.
    """

    description: str
    sections: list[str] = field(default_factory=list)
    recommendation: str = ""
    block_ids: list[str] = field(default_factory=list)


@dataclass
class InspectionResult:
    """Full report card. Document-level dimensions are rolled up from sections."""

    doc_id: str
    dimensions: dict[str, DimensionGrade] = field(default_factory=_empty_dimensions)
    top_issues: list[str] = field(default_factory=list)
    section_grades: list[SectionGrade] = field(default_factory=list)
    cross_section_findings: list[CrossSectionFinding] = field(default_factory=list)
    consistency_status: ConsistencyStatus = "unknown"
    grading_status: GradingStatus = "unknown"

    # --- Header (document provenance, stamped by pipeline) ---
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None

    # The parsed source document (ordered, citable blocks). Carried so downstream
    # consumers (e.g. the Ask assistant) can read the full document behind the
    # grades. Not used by the grading itself.
    blocks: list["ContentBlock"] = field(default_factory=list)


@dataclass
class BatchInspectionResult:
    """Per-document result of inspect_blocks_batch."""

    doc_key: str
    inspection: InspectionResult | None = None
    error: str | None = None


@dataclass
class VariableSpec:
    """Rubric expectations for one variable within a section.

    `completeness`, `adherence`, and `rigor` are optional per-dimension
    rule hints (free-form dicts). The grader uses each block only when
    grading that dimension — no cross-dimension leakage. The blocks are
    informational; the grader reads them into the dimension's prompt
    section verbatim.
    """

    name: str
    description: str
    completeness: dict[str, Any] = field(default_factory=dict)
    adherence: dict[str, Any] = field(default_factory=dict)
    rigor: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionSpec:
    """Rubric expectations for one section.

    For prose sections (no variables) the dimension blocks below carry
    the per-dimension rule hints. For variable-bearing sections, dimension
    grading happens at the variable level — the section blocks are
    typically empty and unused.
    """

    name: str
    description: str
    weight: float
    variables: list[VariableSpec] = field(default_factory=list)
    completeness: dict[str, Any] = field(default_factory=dict)
    adherence: dict[str, Any] = field(default_factory=dict)
    rigor: dict[str, Any] = field(default_factory=dict)


@dataclass
class InspectionConfig:
    """All document-type-specific configuration for Inspector."""

    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    sections: list[SectionSpec]
    # Document-wide grading guidance injected into every dimension prompt. Used
    # for stage calibration (e.g. ITPP grades leniently on numeric specificity,
    # CTPP strictly). Optional; empty means no extra framing.
    grading_guidance: str = ""


CONFIGS_DIR = Path(__file__).resolve().parent / "configs"


def find_config(org: str, source_type: str, intervention_class: str) -> "InspectionConfig | None":
    """Load the Inspector config for the given triple. Returns None if not found
    (Inspector rubrics are optional per triple)."""
    path = CONFIGS_DIR / f"{org}_{source_type}_{intervention_class}.yaml"
    if not path.exists():
        return None
    config = load_inspection_config(str(path))
    requested = (org, source_type, intervention_class)
    configured = (config.org, config.source_type, config.intervention_class)
    if configured != requested:
        raise ValueError(
            "Inspector config identity does not match its filename: "
            f"requested {requested}, configured {configured}"
        )
    return config


def load_inspection_config(path: str) -> InspectionConfig:
    """Load an InspectionConfig from YAML. Validates required fields."""
    config_path = Path(path).expanduser().resolve()
    with open(config_path, "r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)

    if not isinstance(data, dict):
        raise ValueError("Inspector config file must contain a YAML mapping")

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
        raise ValueError(f"Inspector config missing required fields: {missing}")

    _validate_string_field(data, "type_key")
    _validate_string_field(data, "org")
    _validate_string_field(data, "source_type")
    _validate_string_field(data, "intervention_class")
    _validate_string_field(data, "display_name")
    sections = _parse_sections(data["sections"])
    if sum(section.weight for section in sections) <= 0:
        raise ValueError("Inspector section weights must have a positive total")

    grading_guidance = data.get("grading_guidance", "") or ""
    if not isinstance(grading_guidance, str):
        raise ValueError("Inspector config field 'grading_guidance' must be a string")

    return InspectionConfig(
        type_key=data["type_key"],
        org=data["org"],
        source_type=data["source_type"],
        intervention_class=data["intervention_class"],
        display_name=data["display_name"],
        sections=sections,
        grading_guidance=grading_guidance.strip(),
    )


def inspection_result_to_dict(result: InspectionResult) -> dict[str, Any]:
    """Convert an InspectionResult to JSON-serializable dictionaries."""
    return asdict(result)


def _validate_string_field(data: dict[str, Any], field_name: str) -> None:
    if not isinstance(data[field_name], str) or not data[field_name].strip():
        raise ValueError(f"Inspector config field '{field_name}' must be a string")


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
                completeness=_parse_dimension_block(section_data.get("completeness"), f"sections[{index}].completeness"),
                adherence=_parse_dimension_block(section_data.get("adherence"), f"sections[{index}].adherence"),
                rigor=_parse_dimension_block(section_data.get("rigor"), f"sections[{index}].rigor"),
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
                completeness=_parse_dimension_block(
                    variable_data.get("completeness"),
                    f"sections[{section_index}].variables[{index}].completeness",
                ),
                adherence=_parse_dimension_block(
                    variable_data.get("adherence"),
                    f"sections[{section_index}].variables[{index}].adherence",
                ),
                rigor=_parse_dimension_block(
                    variable_data.get("rigor"),
                    f"sections[{section_index}].variables[{index}].rigor",
                ),
            )
        )
    return variables


def _parse_dimension_block(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _validate_weight(value: Any, field_name: str) -> None:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
