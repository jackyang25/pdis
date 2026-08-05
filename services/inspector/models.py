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


DimensionVerdict = Literal["critical", "for_consideration", "meets", "not_applicable"]
"""What one dimension concluded about one rubric variable.

This replaced a letter grade. A letter carried two claims Inspector cannot
support: that the step from A to B is the same size as the step from D to F, and
that a section's quality is the mean of its variables. Both were arithmetic on a
subjective label. A verdict states only what the model can defend — whether there
is a gap, and whether the content is unusable as written or merely improvable.
Neither verdict directs the author; both describe the document.
"""

Dimension = Literal["completeness", "adherence", "rigor"]
ConsistencyStatus = Literal["complete", "partial", "failed", "not_applicable", "unknown"]
GradingStatus = Literal["complete", "unknown"]
DIMENSIONS: tuple[Dimension, ...] = ("completeness", "adherence", "rigor")

# --- Closed vocabularies -----------------------------------------------------
# Declared once. The grading schema offered to the model, the parser that
# validates its reply, and every downstream consumer read these same names; a
# second copy is a second thing to keep in step.

ContentStatus = Literal[
    "substantive", "partial", "placeholder", "missing", "not_applicable"
]
CONTENT_STATUSES: frozenset[str] = frozenset(
    ("substantive", "partial", "placeholder", "missing", "not_applicable")
)
"""How much of a rubric variable the document actually supplies."""

ABSENT_CONTENT_STATUS = "missing"
"""Content the document does not contain. It can cite no block, by definition."""

PRESENT_CONTENT_STATUSES: frozenset[str] = frozenset(
    ("substantive", "partial", "placeholder")
)
"""Content the document does contain, so it must carry exact block lineage."""

DIMENSION_VERDICTS: frozenset[str] = frozenset(
    ("critical", "for_consideration", "meets", "not_applicable")
)

GAP_VERDICTS: frozenset[str] = frozenset(("critical", "for_consideration"))
"""The verdicts that assert a gap, so a roll-up can count them.

`critical` is defensible from the record rather than felt: the rubric requires
the content and the document does not usably supply it. `for_consideration` is
present and usable but could be stronger. There is no third severity, because a
reader who must rank five levels is being asked to do the judging.
"""

NON_GAP_VERDICT = "meets"
"""No gap on this dimension."""

INAPPLICABLE_VERDICT = "not_applicable"
"""The rubric does not ask this dimension of this variable."""


@dataclass
class DimensionAssessment:
    """One of three orthogonal axes, assessed for one rubric variable.

    - completeness: are all required variables present/filled in?
    - adherence:    does the draft follow the rubric's structural expectations?
    - rigor:        is the content substantively sound - specific, measurable,
                    and meaningful (not just present and well-formatted)?

    Produced by the model at the variable level, and directly for a section that
    has no variables. A section or document does not carry an assessment of its
    own: it carries the count of the gaps beneath it, because averaging verdicts
    would invent a middle value no dimension ever returned.
    """

    verdict: DimensionVerdict
    issues: list[str] = field(default_factory=list)
    recommendation: str = ""
    cited_block_ids: list[str] = field(default_factory=list)
    """Blocks *this* judgment cited.

    Each dimension is assessed independently and cites independently, so the
    lineage belongs to the dimension. Merging the three into one list per
    variable made the verdicts orthogonal and their provenance shared, which let
    a consumer attribute a completeness verdict to a block only rigor had read.
    """

    def __post_init__(self) -> None:
        if self.verdict not in DIMENSION_VERDICTS:
            raise ValueError(f"invalid dimension verdict: {self.verdict!r}")

    @property
    def is_gap(self) -> bool:
        return self.verdict in GAP_VERDICTS


def _empty_dimensions() -> dict[str, DimensionAssessment]:
    return {d: DimensionAssessment(verdict=INAPPLICABLE_VERDICT) for d in DIMENSIONS}


def _empty_gap_counts() -> dict[str, int]:
    return {verdict: 0 for verdict in sorted(GAP_VERDICTS)}


@dataclass
class VariableGrade:
    """Atomic assessed unit: one rubric variable, three dimension verdicts."""

    variable_name: str
    dimensions: dict[str, DimensionAssessment] = field(
        default_factory=_empty_dimensions
    )
    content_status: ContentStatus = "not_applicable"
    """How much of this variable the document supplies.

    The completeness judgment owns presence, and this is the answer it gave.
    Consumers read it instead of inferring absence from a grade or from prose:
    `placeholder` and `missing` are different problems with different fixes, and
    only this field distinguishes them.
    """

    @property
    def cited_block_ids(self) -> list[str]:
        """Every block any dimension cited, in first-seen dimension order.

        Derived rather than stored, so it cannot disagree with the per-dimension
        lineage it summarizes. Use a dimension's own list when the question is
        about that dimension.
        """
        seen: list[str] = []
        for dimension in DIMENSIONS:
            assessment = self.dimensions.get(dimension)
            if assessment is None:
                continue
            for block_id in assessment.cited_block_ids:
                if block_id not in seen:
                    seen.append(block_id)
        return seen


@dataclass
class SectionGrade:
    """One rubric section.

    Variables carry the verdicts when the section has them; a prose section is
    assessed directly. Either way the section itself publishes gap counts rather
    than a verdict of its own.
    """

    section_name: str
    is_present: bool = True
    dimensions: dict[str, DimensionAssessment] = field(
        default_factory=_empty_dimensions
    )
    variable_grades: list[VariableGrade] = field(default_factory=list)
    mapped_block_ids: list[str] = field(default_factory=list)
    """Blocks the section mapper assigned to this section, in document order.

    A deterministic assignment, not a citation - named apart from
    `cited_block_ids` so a consumer cannot mistake one for the other. Published
    because the grader, the contract check, and the document view each used to
    rebuild it from `section_label`, three times, from the same input.
    """

    @property
    def missing_variables(self) -> list[str]:
        """Rubric variables the document does not contain, in rubric order.

        Derived from each variable's `content_status`, which is the single
        authority for presence. It was previously stored alongside that status,
        so the two could disagree.
        """
        return [
            variable.variable_name
            for variable in self.variable_grades
            if variable.content_status == ABSENT_CONTENT_STATUS
        ]

    @property
    def gap_counts(self) -> dict[str, int]:
        """Gaps found in this section, counted by severity.

        A count replaced an averaged letter. Averaging assumed the steps between
        letters were equal and that a section's quality was the mean of its
        parts; a count asserts only what was actually found, and a reader can
        verify it by counting the same rows.

        A section the document never wrote is one critical gap. Its dimensions
        assessed nothing, so counting them would report zero problems for the
        most serious problem there is.
        """
        counts = _empty_gap_counts()
        if not self.is_present:
            counts["critical"] = 1
            return counts
        assessed = (
            [
                assessment
                for variable in self.variable_grades
                for assessment in variable.dimensions.values()
            ]
            if self.variable_grades
            else list(self.dimensions.values())
        )
        for assessment in assessed:
            if assessment.is_gap:
                counts[assessment.verdict] += 1
        return counts


@dataclass
class TopIssue:
    """One ranked document-level issue, kept as parts rather than a sentence.

    This used to be a formatted string like
    ``"Dose volume · rigor (D) — Only a placeholder token is present."``.
    Every consumer that wanted to link an issue to its block, filter by
    dimension, or re-sort by severity had to take that sentence back apart, so
    the parts are published and the sentence is the reader's to compose.

    Severity is the dimension's own verdict. It used to be a letter that a
    lookup table then converted into a rank, so the ordering a reader saw was
    one step removed from anything the model said.
    """

    section_name: str
    issue: str
    dimension: Dimension | None = None
    """Absent only for a whole section that is not present at all."""
    variable_name: str | None = None
    severity: DimensionVerdict = INAPPLICABLE_VERDICT
    content_status: ContentStatus | None = None
    recommendation: str = ""
    cited_block_ids: list[str] = field(default_factory=list)


@dataclass
class CrossSectionFinding:
    """A consistency problem that spans MORE THAN ONE section.

    Produced by the whole-document consistency pass - the one place that sees
    all sections at once. Per-section assessment cannot catch these by design
    (sections are assessed in isolation), so this is doc-level, not attached to
    any single section's dimension verdict.
    """

    description: str
    sections: list[str] = field(default_factory=list)
    recommendation: str = ""
    block_ids: list[str] = field(default_factory=list)


@dataclass
class InspectionResult:
    """Full report. Document level counts the gaps its sections found."""

    doc_id: str
    top_issues: list[TopIssue] = field(default_factory=list)
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
    # findings. Not used by the assessment itself.
    blocks: list["ContentBlock"] = field(default_factory=list)

    @property
    def gap_counts(self) -> dict[str, int]:
        """Every section's gaps, summed by severity."""
        totals = _empty_gap_counts()
        for section in self.section_grades:
            for verdict, count in section.gap_counts.items():
                totals[verdict] += count
        return totals


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


def available_configs() -> list["InspectionConfig"]:
    """Every rubric this service can grade against, in stable order.

    Which files are rubrics and which are scaffolds is Inspector's fact, decided
    by whether a file loads as one rather than by the shape of its name.
    Mirrors `chunker.available_configs` so a caller can enumerate any service the
    same way.
    """
    configs: list[InspectionConfig] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            config = load_inspection_config(str(path))
        except (ValueError, KeyError, TypeError):
            # A malformed file is not an available config. Asking for it by
            # identity still raises, so nothing is hidden.
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
    """Convert an InspectionResult to JSON-serializable dictionaries.

    Gap counts are derived, so `asdict` cannot see them. They are published
    anyway: a client that counted for itself could disagree with the report, and
    the count is the only summary the document now has.
    """
    payload = asdict(result)
    payload["gap_counts"] = result.gap_counts
    for section, section_payload in zip(result.section_grades, payload["section_grades"]):
        section_payload["gap_counts"] = section.gap_counts
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
