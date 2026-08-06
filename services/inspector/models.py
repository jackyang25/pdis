"""Inspector's shapes and its one published vocabulary.

This module declares what things are. How they combine is `assembly.py`, and what
the model is asked is `stages/assessor.py`; keeping those apart is what lets a reader
answer "where did this value come from" by looking in one place.

Every published value is authored in the rubric, observed by the model, or derived
by a property here. Nothing is stored twice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import yaml

from shared.openai_client import ModelTask

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
        task: ModelTask = "reasoning",
    ) -> dict[str, Any] | None:
        ...


ConsistencyStatus = Literal["complete", "partial", "failed", "not_applicable", "unknown"]
AssessmentStatus = Literal["complete", "unknown"]

# --- The one published vocabulary --------------------------------------------
# Declared here, mirrored in `web/lib/api.ts`, and bound by
# `inspector-vocabulary.test.ts`. Every layer reads these names; none invents a
# synonym for one, because a second name for the same thing is a second thing to
# keep in step and a reader cannot tell which is authoritative.

FindingReason = Literal[
    "missing", "placeholder", "unmet", "off_template", "unclear", "conflicting"
]
FINDING_REASONS: tuple[FindingReason, ...] = (
    "missing",
    "placeholder",
    "unmet",
    "off_template",
    "unclear",
    "conflicting",
)
"""Why one finding exists. Declared worst-first, which is also display order.

- `missing`      nothing is there
- `placeholder`  a token such as <<TBD>> sits where the value belongs
- `unmet`        content is present and does not satisfy the requirement
- `off_template` the structure or naming deviates from the rubric
- `unclear`      the requirement is satisfied but the content is vague
- `conflicting`  two sections state claims that cannot both hold

This replaced three separate dimension verdicts plus a five-value content status.
One defect belonged to up to three of those at once, so it was counted up to three
times, and absence was recorded in three places that could disagree.
"""

UNIT_REASONS: tuple[FindingReason, ...] = tuple(
    reason for reason in FINDING_REASONS if reason != "conflicting"
)
"""The reasons one rubric unit can raise, and the enum offered to the model.

A conflict spans sections, so no single unit can own it; it comes from the
whole-document pass instead.
"""

FindingLevel = Literal["not_met", "could_be_stronger"]
FINDING_LEVELS: tuple[FindingLevel, ...] = ("not_met", "could_be_stronger")
"""How far short a finding falls.

Conformance language, deliberately not severity language. Inspector knows what the
rubric asked and what the document supplies; it does not know what a shortfall
costs a given programme, so it does not claim one.
"""

LEVEL_BY_REASON: dict[FindingReason, FindingLevel] = {
    "missing": "not_met",
    "placeholder": "not_met",
    "unmet": "not_met",
    "off_template": "could_be_stronger",
    "unclear": "could_be_stronger",
    "conflicting": "not_met",
}
"""The level is derived from the reason, never stored beside it.

A reason already carries the distinction the two levels express, so storing a
severity as well would create two fields that can disagree about one fact.
"""

UNCITED_REASON: FindingReason = "missing"
"""The one reason that cites no block, because there is nothing to cite.

It is also the only reason exempt from citing: every other finding was read from
somewhere, so a reader can check it against the document.
"""

UnitStatus = Literal["met", "could_be_stronger", "not_met", "not_applicable"]
UNIT_STATUSES: tuple[UnitStatus, ...] = (
    "met",
    "could_be_stronger",
    "not_met",
    "not_applicable",
)
"""How one rubric unit stands. Derived from the findings on that unit alone."""


@dataclass
class Finding:
    """One thing to fix: a defect, its remedy, and the blocks it was read from.

    The atom. Three shapes used to carry this - a dimension assessment holding a
    list of issues against a single recommendation, a separately ranked copy of the
    worst of them, and a cross-section conflict with its own field names for the
    same concepts. A reader could not act on the second of three issues, because
    only the list had three entries and the fix had one.

    Which unit a finding is about is read from its names rather than a separate
    scope field: both names set is a variable, section alone is a whole section,
    neither is the document.
    """

    id: str
    reason: FindingReason
    statement: str
    """What is wrong, in one sentence. One defect per finding, never a list."""
    recommendation: str = ""
    section_name: str | None = None
    variable_name: str | None = None
    cited_block_ids: list[str] = field(default_factory=list)
    """The blocks this finding was read from. Empty exactly when nothing is there.

    For a conflict these are the passages that disagree, so the sections involved
    are resolved from them rather than stored a second time.
    """
    rank: int = 0
    """Position in the worklist, assigned once during assembly.

    Stored so every consumer orders identically without holding the rubric. This
    replaced a separately computed list of top issues that duplicated the rows it
    ranked and could fall out of step with them.
    """

    def __post_init__(self) -> None:
        if self.reason not in FINDING_REASONS:
            raise ValueError(f"invalid finding reason: {self.reason!r}")
        if not self.statement:
            raise ValueError("a finding must state what is wrong")
        if self.variable_name and not self.section_name:
            raise ValueError("a variable finding must name its section")
        if self.reason == UNCITED_REASON and self.cited_block_ids:
            raise ValueError("an absent unit cannot cite blocks")
        if self.reason != UNCITED_REASON and not self.cited_block_ids:
            raise ValueError("a finding must cite the block it was read from")

    @property
    def level(self) -> FindingLevel:
        return LEVEL_BY_REASON[self.reason]


@dataclass
class UnitAssessment:
    """One rubric unit: a variable, or a section that declares none.

    The unit owns its findings rather than referring to them by id, so a finding
    cannot belong to two units or to none, and the status is a property of data the
    unit already holds.
    """

    variable_name: str | None = None
    """None when the section itself is the unit, as a prose section is."""
    optional: bool = False
    """The rubric author's decision that absence here is acceptable."""
    findings: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> UnitStatus:
        """What this unit reports, derived from its own findings.

        The only place a status is decided. `met` therefore means exactly zero
        findings, and no consumer can arrive at a different answer.
        """
        if self.optional and any(f.reason == UNCITED_REASON for f in self.findings):
            return "not_applicable"
        if not self.findings:
            return "met"
        if any(f.level == "not_met" for f in self.findings):
            return "not_met"
        return "could_be_stronger"


@dataclass
class SectionAssessment:
    """One rubric section: where it was found, and the units beneath it.

    Every section has at least one unit, so there is no prose-versus-table branch
    for a consumer to get wrong. IPDP rubrics declare no prose sections at all and
    every TPP declares three or four, so a shape that split them was carrying a
    branch for one of them on every run.
    """

    section_name: str
    mapped_block_ids: list[str] = field(default_factory=list)
    """Blocks the section mapper assigned here, in document order.

    A deterministic assignment, not a citation. Published because the assessor, the
    contract check, and the document view each used to rebuild it from
    `section_label`, three times, from the same input.
    """
    units: list[UnitAssessment] = field(default_factory=list)

    @property
    def is_present(self) -> bool:
        """Whether the document contains this section.

        Derived, because it was never anything else: the assessor marked a section
        present exactly when the mapper gave it blocks. Storing it made one fact
        carried three ways - this flag, `mapped_block_ids`, and a list of present
        section names threaded through two layers - so the contract had to police an
        agreement that is now definitional.
        """
        return bool(self.mapped_block_ids)

    @property
    def status_counts(self) -> dict[str, int]:
        """This section's units, counted by status.

        Bounded by the rubric, so "3 not met" always means three of a known number
        of units. The count it replaced counted judgments, which was unbounded and
        comparable to nothing.
        """
        counts = {status: 0 for status in UNIT_STATUSES}
        for unit in self.units:
            counts[unit.status] += 1
        return counts


@dataclass
class InspectionResult:
    """One document against one rubric."""

    doc_id: str
    sections: list[SectionAssessment] = field(default_factory=list)
    document_findings: list[Finding] = field(default_factory=list)
    """Conflicts spanning sections, which no single unit can own."""
    consistency_status: ConsistencyStatus = "unknown"
    assessment_status: AssessmentStatus = "unknown"
    """Whether this run completed.

    A process fact, deliberately outside the assessment: "not checked" must never
    read as "nothing found".
    """

    # --- Header (document provenance, stamped by the pipeline) ---
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None

    # The parsed source document (ordered, citable blocks). Carried so downstream
    # consumers (e.g. the Ask assistant) can read the full document behind the
    # findings. Not used by the assessment itself.
    blocks: list["ContentBlock"] = field(default_factory=list)


@dataclass
class BatchInspectionResult:
    """Per-document result of inspect_blocks_batch."""

    doc_key: str
    inspection: InspectionResult | None = None
    error: str | None = None


# --- Rubric configuration ----------------------------------------------------
# One shape at both levels: a section and a variable declare the same things, so a
# reader learns the schema once. A section adds only its variables.


@dataclass
class VariableSpec:
    """Rubric expectations for one variable within a section."""

    name: str
    description: str
    optional: bool = False
    """Whether the rubric accepts this being absent.

    An optional variable that is present is assessed like any other; absent, it is
    `not_applicable` rather than a shortfall. Without this the tool asserted
    something the rubric author explicitly had not: every "Additional Variables of
    Interest" section says its variables are not relevant to every document, and on
    the device profiles that section holds 25 of 48 units.
    """
    expectations: str = ""
    """What good looks like here, read into the prompt verbatim.

    One block, not one per question. This is where an external standard belongs
    when one applies - as the expectation a unit is held to, never as a second
    rubric.
    """


@dataclass
class SectionSpec:
    """Rubric expectations for one section.

    A section with no variables is itself one unit and carries the expectations
    below. A section with variables contributes one unit per variable.
    """

    name: str
    description: str
    optional: bool = False
    """Applied to every unit in the section, so a whole optional section need not
    repeat the flag on each variable."""
    expectations: str = ""
    variables: list[VariableSpec] = field(default_factory=list)


@dataclass
class InspectionConfig:
    """All document-type-specific configuration for Inspector."""

    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    sections: list[SectionSpec]
    # Document-wide stage calibration injected into the assessment prompt (e.g.
    # ITPP expects less numeric specificity than CTPP). Empty means no extra
    # framing.
    stage_guidance: str = ""
    mirrors: str = ""
    """The authored source this rubric's structure comes from.

    Free text, because the sources do not share a shape: naming a library, a
    document, and a revision separately would bake in the conventions of one of
    them. Published so the question "is this the official template" is answerable
    from the file rather than from memory.

    This is the one boundary that leaves the codebase, so nothing here can verify
    it. It names which source to re-check when that source moves; it is not a
    drift check. Everything the source does not contain - each unit's
    `description`, `stage_guidance`, `optional`, `expectations` - is maintained
    here, and `README.md` states that split once rather than repeating it per
    config.
    """


CONFIGS_DIR = Path(__file__).resolve().parent / "configs"


def available_configs() -> list["InspectionConfig"]:
    """Every rubric this service can assess against, in stable order.

    Which files are rubrics and which are scaffolds is Inspector's fact, decided by
    whether a file loads as one rather than by the shape of its name. Mirrors
    `chunker.available_configs` so a caller can enumerate any service the same way.
    """
    configs: list[InspectionConfig] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            config = load_inspection_config(str(path))
        except (ValueError, KeyError, TypeError):
            continue
        # A config is named for its identity; a scaffold is not.
        if config.type_key != path.stem:
            continue
        configs.append(config)
    return configs


def has_config(org: str, source_type: str, intervention_class: str) -> bool:
    """Report whether this triple has a rubric.

    Inspector rubrics are optional per triple, unlike chunker and scout configs.
    That optionality is asked about here rather than expressed as a different
    return contract from :func:`find_config`, so one caller can treat every
    service's lookup identically.
    """
    return _config_path(org, source_type, intervention_class).exists()


def _config_path(org: str, source_type: str, intervention_class: str) -> Path:
    return CONFIGS_DIR / f"{org}_{source_type}_{intervention_class}.yaml"


def find_config(org: str, source_type: str, intervention_class: str) -> "InspectionConfig":
    """Load the Inspector config for the given triple.

    Raises ``LookupError`` when absent, matching chunker and scout. Use
    :func:`has_config` when absence is an expected, non-exceptional answer.
    """
    path = _config_path(org, source_type, intervention_class)
    if not path.exists():
        raise LookupError(
            f"No Inspector config for ({org}, {source_type}, {intervention_class}). "
            f"Expected: {path}"
        )
    config = load_inspection_config(str(path))
    requested = (org, source_type, intervention_class)
    configured = (config.org, config.source_type, config.intervention_class)
    if configured != requested:
        raise ValueError(
            "Inspector config identity does not match its filename: "
            f"requested {requested}, configured {configured}"
        )
    expected_type_key = "_".join(requested)
    if config.type_key != expected_type_key:
        raise ValueError(
            "Inspector config type_key does not match its identity: "
            f"expected {expected_type_key!r}, configured {config.type_key!r}"
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

    for field_name in ("type_key", "org", "source_type", "intervention_class", "display_name"):
        _validate_string_field(data, field_name)

    stage_guidance = data.get("stage_guidance", "") or ""
    if not isinstance(stage_guidance, str):
        raise ValueError("Inspector config field 'stage_guidance' must be a string")
    mirrors = data.get("mirrors", "") or ""
    if not isinstance(mirrors, str):
        raise ValueError("Inspector config field 'mirrors' must be a string")

    return InspectionConfig(
        type_key=data["type_key"],
        org=data["org"],
        source_type=data["source_type"],
        intervention_class=data["intervention_class"],
        display_name=data["display_name"],
        sections=_parse_sections(data["sections"]),
        stage_guidance=stage_guidance.strip(),
        mirrors=mirrors.strip(),
    )


def inspection_result_to_dict(result: InspectionResult) -> dict[str, Any]:
    """Convert an InspectionResult to JSON-serializable dictionaries.

    Derived values `asdict` cannot see are added here: each unit's status, each
    finding's level, and each section's status counts. They are published rather
    than left to the client because a client deriving them independently could
    disagree with the assessment it is displaying.

    No flattened copy of the findings is published. A worklist is those same
    findings ordered by `rank`, which the presentation layer composes - a second
    array here would be a shape that can drift from the units it came from.
    """
    payload = asdict(result)
    # `zip` truncates silently, so a shape that stopped lining up would leave later
    # units without their derived status - and the API refuses that rather than
    # defaulting it, so this assert names the cause instead of the symptom.
    if len(result.sections) != len(payload["sections"]):
        raise ValueError("Inspector payload lost sections during serialization")
    for section, section_payload in zip(result.sections, payload["sections"]):
        section_payload["is_present"] = section.is_present
        section_payload["status_counts"] = section.status_counts
        for unit, unit_payload in zip(section.units, section_payload["units"]):
            unit_payload["status"] = unit.status
            for finding, finding_payload in zip(unit.findings, unit_payload["findings"]):
                finding_payload["level"] = finding.level
    for finding, finding_payload in zip(result.document_findings, payload["document_findings"]):
        finding_payload["level"] = finding.level
    return payload


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

        section_name = section_data["name"]
        if section_name in seen_names:
            raise ValueError(f"Duplicate section name: {section_name}")
        seen_names.add(section_name)

        sections.append(
            SectionSpec(
                name=section_name,
                description=section_data["description"],
                optional=_parse_flag(section_data.get("optional"), f"sections[{index}].optional"),
                expectations=_parse_expectations(
                    section_data.get("expectations"), f"sections[{index}].expectations"
                ),
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
        where = f"sections[{section_index}].variables[{index}]"
        if not isinstance(variable_data, dict):
            raise ValueError(f"{where} must be a mapping")
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
                optional=_parse_flag(variable_data.get("optional"), f"{where}.optional"),
                expectations=_parse_expectations(
                    variable_data.get("expectations"), f"{where}.expectations"
                ),
            )
        )
    return variables


def _parse_flag(value: Any, field_name: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be true or false")
    return value


def _parse_expectations(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()
