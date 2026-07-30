from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import yaml

from shared.openai_client import ModelTask

if TYPE_CHECKING:
    from services.chunker import ContentBlock


class LLMClientProtocol(Protocol):
    """Contract aligner requires from any injected LLM client.

    Identical to the chunker, inspector, and scout contract so one client
    satisfies every service in the suite.
    """

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


UnitType = Literal[
    "target",
    "activity",
    "milestone",
    "requirement",
    "dependency",
    "risk_response",
]
AlignmentRelation = Literal[
    "aligned",
    "modified",
    "conflict",
    "missing",
    "introduced",
]


@dataclass(frozen=True)
class LabelSpec:
    name: str
    description: str


@dataclass
class AlignmentConfig:
    unit_types: list[LabelSpec]
    relations: list[LabelSpec]
    document_roles: dict[str, str]
    extraction_batch_characters: int = 50000
    extraction_batch_blocks: int = 40
    # Per-item scope: one relation per reference unit. The comparison pool below
    # is genuinely set-level — a relation needs candidates to match against.
    alignment_batch_units: int = 1
    alignment_comparison_batch_units: int = 48
    max_parallel_calls: int = 6


@dataclass
class AlignmentDocument:
    role: Literal["reference", "comparison"]
    doc_id: str
    source_type: str
    display_name: str


@dataclass
class AlignmentUnit:
    id: str
    document_role: Literal["reference", "comparison"]
    document_id: str
    unit_type: UnitType
    statement: str
    block_ids: list[str] = field(default_factory=list)


@dataclass
class AlignmentLink:
    id: str
    relation: AlignmentRelation
    reference_unit_ids: list[str] = field(default_factory=list)
    comparison_unit_ids: list[str] = field(default_factory=list)
    reason: str = ""
    reference_block_ids: list[str] = field(default_factory=list)
    comparison_block_ids: list[str] = field(default_factory=list)


@dataclass
class AlignmentStats:
    reference_units: int = 0
    comparison_units: int = 0
    aligned: int = 0
    modified: int = 0
    conflict: int = 0
    missing: int = 0
    introduced: int = 0


@dataclass
class AlignmentResult:
    reference_document: AlignmentDocument
    comparison_document: AlignmentDocument
    units: list[AlignmentUnit]
    links: list[AlignmentLink]
    stats: AlignmentStats
    org: str
    intervention_class: str
    indication: str
    unit_types: list[LabelSpec] = field(default_factory=list)
    relations: list[LabelSpec] = field(default_factory=list)
    blocks: list["ContentBlock"] = field(default_factory=list)


CONFIG_PATH = Path(__file__).resolve().parent / "configs" / "alignment.yaml"


def load_config(path: str | None = None) -> AlignmentConfig:
    config_path = Path(path).expanduser().resolve() if path else CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}
    if not isinstance(data, dict):
        raise ValueError("Aligner config must contain a YAML mapping")
    unit_types = _label_specs(data.get("unit_types"), "unit_types")
    relations = _label_specs(data.get("relations"), "relations")
    expected_units = {
        "target",
        "activity",
        "milestone",
        "requirement",
        "dependency",
        "risk_response",
    }
    expected_relations = {"aligned", "modified", "conflict", "missing", "introduced"}
    if {item.name for item in unit_types} != expected_units:
        raise ValueError("Aligner unit_types must define the complete controlled vocabulary")
    if {item.name for item in relations} != expected_relations:
        raise ValueError("Aligner relations must define the complete controlled vocabulary")
    document_roles = data.get("document_roles", {})
    if not isinstance(document_roles, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in document_roles.items()
    ):
        raise ValueError("Aligner document_roles must be a string mapping")
    execution = data.get("execution", {}) or {}
    if not isinstance(execution, dict):
        raise ValueError("Aligner execution must be a mapping")
    return AlignmentConfig(
        unit_types=unit_types,
        relations=relations,
        document_roles={key: value.strip() for key, value in document_roles.items()},
        extraction_batch_characters=_positive_int(
            execution.get("extraction_batch_characters", 50000),
            "extraction_batch_characters",
        ),
        extraction_batch_blocks=_positive_int(
            execution.get("extraction_batch_blocks", 40),
            "extraction_batch_blocks",
        ),
        alignment_batch_units=_positive_int(
            execution.get("alignment_batch_units", 1),
            "alignment_batch_units",
        ),
        alignment_comparison_batch_units=_positive_int(
            execution.get("alignment_comparison_batch_units", 48),
            "alignment_comparison_batch_units",
        ),
        max_parallel_calls=_positive_int(
            execution.get("max_parallel_calls", 6),
            "max_parallel_calls",
        ),
    )


def alignment_result_to_dict(result: AlignmentResult) -> dict[str, Any]:
    return asdict(result)


def _label_specs(value: Any, field_name: str) -> list[LabelSpec]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Aligner {field_name} must be a non-empty list")
    specs: list[LabelSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"Aligner {field_name}[{index}] must be a mapping")
        name = item.get("name")
        description = item.get("description")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Aligner {field_name}[{index}].name must be a string")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Aligner {field_name}[{index}].description must be a string")
        if name in seen:
            raise ValueError(f"Duplicate Aligner {field_name} name: {name}")
        seen.add(name)
        specs.append(LabelSpec(name=name, description=description.strip()))
    return specs


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Aligner {field_name} must be a positive integer")
    return value
