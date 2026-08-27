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
from shared.vocabulary import search_term

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

Verdict = Literal[
    "specified",
    "not_present",
    "placeholder",
    "insufficient",
    "vague",
    "section_conflict",
    "not_applicable",
]
VERDICTS: tuple[Verdict, ...] = (
    "specified",
    "not_present",
    "placeholder",
    "insufficient",
    "vague",
    "section_conflict",
    "not_applicable",
)
"""How one rubric unit stands. Declared worst-first after `specified`, which is also
display order.

- `specified`        the rubric asks for this and the document supplies it usably
- `not_present`      nothing is there, and the rubric asked for it
- `placeholder`      a token such as <<TBD>> sits where the value belongs
- `insufficient`     content is present and does not satisfy the requirement
- `vague`            the requirement is satisfied but the content is unusable as stated
- `section_conflict` two sections state claims that cannot both hold
- `not_applicable`   the rubric accepts absence here and the document omits it

One axis, and the only one, answering one question: does the document supply what
this unit asks for, usably? Every value is a position on that question - from
supplied, through supplied-but-not-enough, to nothing there.

It replaced three stacked vocabularies over the same fact: a `reason` the model
chose, a `level` that was a lookup on the reason, and a `status` that bucketed the
levels into three. The second added no information the first did not carry, and the
third re-expressed the second in different words - so a reader saw "Insufficient" on
a finding and "Not met" on the unit above it and had no way to know those were one
judgement said twice.

`off_template` is deliberately absent, and it was the last thing on this list that
did not belong. It named a deviation in structure or naming, which is a different
question from every other value here: the rest ask what the content says, that one
asked what shape it was in. Two questions in one field means a unit that is both
misnamed and unmeasurable has to be filed as one of them, and the other fact is
lost. A layout that costs the reader something shows up as `insufficient` or `vague`
on its own merits; a layout that costs them nothing is not Inspector's business.

Names match what a reader sees, which the old ones did not: the reason `unmet`
rendered as "Insufficient" while the status `not_met` rendered as "Not met", two
near-identical keys for two different axes.
"""

UNIT_VERDICTS: tuple[Verdict, ...] = tuple(
    verdict for verdict in VERDICTS if verdict != "section_conflict"
)
"""The verdicts one rubric unit can carry, and the enum offered to the model.

A conflict spans sections, so no single unit can own it; it comes from the
whole-document pass instead. Same vocabulary, wider scope - not a second one.
"""

ASSESSED_VERDICTS: tuple[Verdict, ...] = tuple(
    verdict for verdict in VERDICTS if verdict not in ("specified", "not_applicable")
)
"""The verdicts that name something to fix.

`specified` is the rubric satisfied and `not_applicable` is the rubric not asking, so
neither is a shortfall. Used for the worklist and for the priorities panel, both of
which answer "what needs work" rather than "what happened".
"""

UNCITED_VERDICTS: tuple[Verdict, ...] = ("not_present", "not_applicable")
"""The verdicts that cite no block, because there is nothing to cite.

Every other verdict was read from somewhere, so a reader can check it against the
document.
"""


@dataclass
class Assessment:
    """One rubric unit and how it stands: a verdict, a sentence, and its blocks.

    The atom, and the only one. It used to be a `Finding` nested inside a
    `UnitAssessment`, with the unit's verdict computed from the findings it held -
    which meant a unit could hold several and the display had to reconcile them.
    One rubric question now gets one answer.

    Which unit an assessment is about is read from its names rather than a separate
    scope field: both names set is a variable, section alone is a whole section,
    neither is the document.

    Dropped with the nesting: `recommendation`. It restated the statement as an
    imperative - "Vial size is not specified" beside "Specify vial size" - and the
    web layer had grown a `restatesItself()` guard to hide one of them. A reader who
    knows what is missing knows to add it.
    """

    id: str
    verdict: Verdict
    statement: str = ""
    """What is wrong, in one sentence. Empty exactly when nothing is wrong.

    A `specified` unit has no sentence because there is nothing to say: the rubric
    asked and the document answered. Anything else is a claim about the document
    that has to be checkable against it.
    """
    section_name: str | None = None
    variable_name: str | None = None
    optional: bool = False
    """The rubric author's decision that absence here is acceptable."""
    cited_block_ids: list[str] = field(default_factory=list)
    """The blocks this was read from. Empty exactly when nothing is there.

    For a conflict these are the passages that disagree, so the sections involved
    are resolved from them rather than stored a second time.
    """
    rank: int = 0
    """Position in the worklist, assigned once during assembly.

    Stored so every consumer orders identically without holding the rubric.
    """

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"invalid verdict: {self.verdict!r}")
        if self.verdict in ASSESSED_VERDICTS and not self.statement:
            raise ValueError(f"a {self.verdict} unit must state what is wrong")
        if self.verdict not in ASSESSED_VERDICTS and self.statement:
            raise ValueError(f"a {self.verdict} unit has nothing to state")
        if self.variable_name and not self.section_name:
            raise ValueError("a variable assessment must name its section")
        if self.verdict == "not_present" and self.optional:
            # Both values mean "nothing is there"; what separates them is whether the
            # rubric asked for it. An optional unit's absence is accepted by definition,
            # so `not_present` on one is not a second opinion - it is the same fact filed
            # as a shortfall. Left expressible, two optional units both absent came back
            # with different verdicts in the same section.
            raise ValueError("an optional unit that is absent is not_applicable")
        if self.verdict == "not_applicable" and not self.optional:
            # Whether absence is acceptable is the rubric author's decision, never the
            # model's. Without this a required unit could come back `not_applicable`
            # and be dropped from the worklist - a shortfall disappearing quietly,
            # which is the one failure mode this tool must not have.
            raise ValueError("only an optional unit can be not_applicable")
        if self.verdict in UNCITED_VERDICTS and self.cited_block_ids:
            raise ValueError("an absent unit cannot cite blocks")
        if self.verdict not in UNCITED_VERDICTS and not self.cited_block_ids:
            raise ValueError("an assessment must cite the block it was read from")

    @property
    def needs_work(self) -> bool:
        """Whether this names something to fix.

        Not a second axis: a read of the one axis, the way `is_present` is a read of
        `mapped_block_ids`. It exists because "what needs work" is asked in four
        places and each was writing the same tuple membership test.
        """
        return self.verdict in ASSESSED_VERDICTS


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
    units: list[Assessment] = field(default_factory=list)

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
    def verdict_counts(self) -> dict[str, int]:
        """This section's units, counted by verdict.

        A count of the one axis, not a bucketing into a second one: `3 vague` means
        three of a known number of units, and the word is the same word the unit
        wears. What it replaced counted findings, which was unbounded - a unit could
        hold several - and comparable to nothing.
        """
        counts = {verdict: 0 for verdict in VERDICTS}
        for unit in self.units:
            counts[unit.verdict] += 1
        return counts


@dataclass
class InspectionResult:
    """One document against one rubric."""

    doc_id: str
    sections: list[SectionAssessment] = field(default_factory=list)
    document_findings: list[Assessment] = field(default_factory=list)
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

    @property
    def intervention_term(self) -> str:
        """The class as it reads inside a prompt sentence.

        `intervention_class` is an identity: it selects this file and is checked against
        `type_key`. Derived on read rather than stored so the two cannot disagree, and
        named as Scout names it, because a reader who learns one service should not have
        to learn a second word for the same derivation.
        """
        return search_term(self.intervention_class)


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

    Two derived values `asdict` cannot see are added: each section's presence and its
    verdict counts. Both are reads of data already in the payload, published rather
    than left to the client because a client deriving them independently could
    disagree with the assessment it is displaying.

    Every other value here is the model's answer or the rubric's. There used to be
    three more - a unit status computed from its findings, a finding level looked up
    from its reason, and section counts of those statuses - all restating one
    judgement in three vocabularies.

    No flattened copy of the units is published. A worklist is those same units
    ordered by `rank`, which the presentation layer composes - a second array here
    would be a shape that can drift from the sections it came from.
    """
    payload = asdict(result)
    # `zip` truncates silently, so a shape that stopped lining up would leave later
    # sections without their derived values - and the API refuses that rather than
    # defaulting it, so this raise names the cause instead of the symptom.
    if len(result.sections) != len(payload["sections"]):
        raise ValueError("Inspector payload lost sections during serialization")
    for section, section_payload in zip(result.sections, payload["sections"]):
        section_payload["is_present"] = section.is_present
        section_payload["verdict_counts"] = section.verdict_counts
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
