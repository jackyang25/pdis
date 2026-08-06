"""Assembly: the rubric's units joined with the findings raised against them.

The one layer that creates nothing. Every value produced here is authored in the
rubric, observed by the model, or derived by a function in this file, so a reader
asking where a number came from has three places to look rather than twenty.

Kept apart from `models` on purpose: that module declares shapes, this one decides
how they combine.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from services.inspector.models import (
    FINDING_LEVELS,
    UNCITED_REASON,
    Finding,
    InspectionConfig,
    SectionAssessment,
    UnitAssessment,
)

RubricUnit = Tuple[str, Optional[str], bool]
"""One thing the rubric asks about: (section, variable or None, optional)."""


def rubric_units(config: InspectionConfig) -> list[RubricUnit]:
    """Every unit the rubric asks about, in the order the author wrote them.

    The document's denominator, taken from the rubric alone, which is why this is
    its own function rather than something read off the findings: a model that says
    nothing about a unit cannot remove it from the assessment.

    Rubric order is also the only priority signal in the system that somebody
    actually authored. It replaced a per-section `weight` that nobody calibrated,
    sat in eleven configs, and had one consumer.
    """
    units: list[RubricUnit] = []
    for section in config.sections:
        if not section.variables:
            units.append((section.name, None, section.optional))
            continue
        for variable in section.variables:
            units.append(
                (section.name, variable.name, section.optional or variable.optional)
            )
    return units


def assess_sections(
    config: InspectionConfig,
    findings: Sequence[Finding],
    *,
    mapped_blocks: dict[str, list[str]] | None = None,
) -> list[SectionAssessment]:
    """Join the rubric with the findings addressed to it.

    Every section and every unit appears whether or not the model spoke about it. A
    finding addressed to a unit the rubric does not contain raises rather than being
    dropped: it means the run and the rubric disagree about what was assessed, and a
    silent discard would leave the assessment looking complete.

    `mapped_blocks` carries the parse lineage the assessor observed, and presence is
    read from it rather than passed alongside: a section is present exactly when the
    mapper gave it blocks. Defaulting it keeps this callable from a test that only
    cares about the join.
    """
    mapping = mapped_blocks or {}

    sections: list[SectionAssessment] = []
    units_by_key: dict[tuple[str, str | None], UnitAssessment] = {}
    for section_spec in config.sections:
        units: list[UnitAssessment] = []
        for section_name, variable_name, optional in rubric_units(config):
            if section_name != section_spec.name:
                continue
            unit = UnitAssessment(variable_name=variable_name, optional=optional)
            units.append(unit)
            units_by_key[(section_name, variable_name)] = unit
        sections.append(
            SectionAssessment(
                section_name=section_spec.name,
                mapped_block_ids=list(mapping.get(section_spec.name, ())),
                units=units,
            )
        )

    for finding in findings:
        unit = units_by_key.get((finding.section_name, finding.variable_name))
        if unit is None:
            raise ValueError(
                "finding addresses a unit outside the rubric: "
                f"{finding.section_name!r} / {finding.variable_name!r}"
            )
        unit.findings.append(finding)
    return sections


def rank_findings(
    config: InspectionConfig,
    sections: Sequence[SectionAssessment],
    document_findings: Sequence[Finding] = (),
) -> list[Finding]:
    """Assign every finding its position and return them in that order.

    Ordered by level, then by the rubric's own sequence, then by reason. Nothing
    here is a judgment we invented: an unsatisfied requirement preceding an
    improvable one is what the two levels mean, and the rest of the order is the
    order the rubric author wrote.

    Findings on a `not_applicable` unit are excluded rather than ranked last. The
    rubric accepts their absence, so they are not work; they stay on the unit so it
    can still explain itself.

    Assigning this once, here, is what let a separately computed list of top issues
    go away. Every consumer sorts by `rank` and gets the same order.
    """
    from services.inspector.models import FINDING_REASONS  # local: display order only

    level_rank = {level: index for index, level in enumerate(FINDING_LEVELS)}
    unit_order = {
        (section, variable): index
        for index, (section, variable, _) in enumerate(rubric_units(config))
    }

    candidates: list[Tuple[int, int, int, Finding]] = []
    for section in sections:
        for unit in section.units:
            if unit.status == "not_applicable":
                continue
            position = unit_order[(section.section_name, unit.variable_name)]
            for finding in unit.findings:
                candidates.append(
                    (
                        level_rank[finding.level],
                        position,
                        FINDING_REASONS.index(finding.reason),
                        finding,
                    )
                )
    for offset, finding in enumerate(document_findings):
        # A conflict carries no unit, so it follows the units it shares a level
        # with rather than interleaving with them on an invented position.
        candidates.append(
            (
                level_rank[finding.level],
                len(unit_order) + offset,
                FINDING_REASONS.index(finding.reason),
                finding,
            )
        )

    ordered = [item[-1] for item in sorted(candidates, key=lambda item: item[:3])]
    for position, finding in enumerate(ordered):
        finding.rank = position
    return ordered


def absent_unit_findings(
    config: InspectionConfig, section_name: str
) -> list[Finding]:
    """One finding per unit of a section the document never wrote.

    A section with variables has no unit of its own, so each of its units reports
    its own absence. That keeps the denominator honest instead of collapsing a whole
    missing section into a single line that leaves the rest looking assessed.
    """
    spec = next((s for s in config.sections if s.name == section_name), None)
    if spec is None:
        raise ValueError(f"section outside the rubric: {section_name!r}")
    if not spec.variables:
        return [
            Finding(
                id=finding_id(section_name, None, UNCITED_REASON),
                reason=UNCITED_REASON,
                statement=f"The {section_name} section is not present in the document.",
                recommendation=f"Add a {section_name} section covering: {spec.description}",
                section_name=section_name,
            )
        ]
    return [
        Finding(
            id=finding_id(section_name, variable.name, UNCITED_REASON),
            reason=UNCITED_REASON,
            statement=f"{variable.name} is not present; the {section_name} section is absent.",
            recommendation=f"Add the {section_name} section and state {variable.name}.",
            section_name=section_name,
            variable_name=variable.name,
        )
        for variable in spec.variables
    ]


def finding_id(section_name: str | None, variable_name: str | None, reason: str) -> str:
    """A stable id for one unit's finding under one reason.

    Unique by construction: a unit raises each reason at most once, which the
    contract check enforces.
    """
    return "|".join((section_name or "", variable_name or "", reason))
