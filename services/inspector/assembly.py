"""Assembly: the rubric's units joined with the verdicts returned against them.

The one layer that creates nothing. Every value produced here is authored in the
rubric, observed by the model, or derived by a function in this file, so a reader
asking where a number came from has three places to look rather than twenty.

Kept apart from `models` on purpose: that module declares shapes, this one decides
how they combine.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from services.inspector.models import (
    VERDICTS,
    Assessment,
    InspectionConfig,
    SectionAssessment,
)

RubricUnit = Tuple[str, Optional[str], bool]
"""One thing the rubric asks about: (section, variable or None, optional)."""


def rubric_units(config: InspectionConfig) -> list[RubricUnit]:
    """Every unit the rubric asks about, in the order the author wrote them.

    The document's denominator, taken from the rubric alone, which is why this is
    its own function rather than something read off the answers: a model that says
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
    assessments: Sequence[Assessment],
    *,
    mapped_blocks: dict[str, list[str]] | None = None,
) -> list[SectionAssessment]:
    """Join the rubric with the verdicts addressed to it.

    Every rubric unit must have exactly one assessment, and both directions raise.
    An assessment for a unit the rubric does not contain means the run and the rubric
    disagree about what was assessed; a unit with no assessment means the run did not
    finish. Either way a silent fill would leave the result looking complete.

    Deliberately not defaulted to `specified`: the assessor makes one call per unit,
    so a missing answer is a failed call, and "not checked" reading as "nothing
    wrong" is the one mistake this tool cannot make.

    `mapped_blocks` carries the parse lineage the assessor observed, and presence is
    read from it rather than passed alongside: a section is present exactly when the
    mapper gave it blocks. Defaulting it keeps this callable from a test that only
    cares about the join.
    """
    mapping = mapped_blocks or {}
    answered = {
        (item.section_name, item.variable_name): item for item in assessments
    }

    known = {(section, variable) for section, variable, _ in rubric_units(config)}
    for key in answered:
        if key not in known:
            raise ValueError(
                "assessment addresses a unit outside the rubric: "
                f"{key[0]!r} / {key[1]!r}"
            )
    for section, variable, _ in rubric_units(config):
        if (section, variable) not in answered:
            raise ValueError(
                f"no assessment for rubric unit: {section!r} / {variable!r}"
            )

    sections: list[SectionAssessment] = []
    for section_spec in config.sections:
        units: list[Assessment] = []
        for section_name, variable_name, optional in rubric_units(config):
            if section_name != section_spec.name:
                continue
            del optional  # the assessment carries it; the rubric is checked above
            units.append(answered[(section_name, variable_name)])
        sections.append(
            SectionAssessment(
                section_name=section_spec.name,
                mapped_block_ids=list(mapping.get(section_spec.name, ())),
                units=units,
            )
        )
    return sections


def rank_assessments(
    config: InspectionConfig,
    sections: Sequence[SectionAssessment],
    document_assessments: Sequence[Assessment] = (),
) -> list[Assessment]:
    """Assign every unit that needs work its position, and return them in that order.

    Ordered by verdict, then by the rubric's own sequence. Neither is a judgment we
    invented: the vocabulary is declared worst-first and that is its display order,
    and the rest is the order the rubric author wrote.

    `specified` and `not_applicable` units are excluded rather than ranked last. One
    is the rubric satisfied and the other is the rubric not asking, so neither is
    work.

    Assigning this once, here, is what let a separately computed list of top issues
    go away. Every consumer sorts by `rank` and gets the same order.
    """
    verdict_rank = {verdict: index for index, verdict in enumerate(VERDICTS)}
    unit_order = {
        (section, variable): index
        for index, (section, variable, _) in enumerate(rubric_units(config))
    }

    candidates: list[Tuple[int, int, Assessment]] = []
    for section in sections:
        for unit in section.units:
            if not unit.needs_work:
                continue
            position = unit_order[(section.section_name, unit.variable_name)]
            candidates.append((verdict_rank[unit.verdict], position, unit))
    for offset, item in enumerate(document_assessments):
        # A conflict carries no unit, so it follows the units it shares a verdict
        # with rather than interleaving with them on an invented position.
        candidates.append(
            (verdict_rank[item.verdict], len(unit_order) + offset, item)
        )

    ordered = [item[-1] for item in sorted(candidates, key=lambda item: item[:2])]
    for position, item in enumerate(ordered):
        item.rank = position
    return ordered


def absent_unit_assessments(
    config: InspectionConfig, section_name: str
) -> list[Assessment]:
    """One verdict per unit of a section the document never wrote.

    A section with variables has no unit of its own, so each of its units reports
    its own absence. That keeps the denominator honest instead of collapsing a whole
    missing section into a single line that leaves the rest looking assessed.
    """
    spec = next((s for s in config.sections if s.name == section_name), None)
    if spec is None:
        raise ValueError(f"section outside the rubric: {section_name!r}")
    if not spec.variables:
        return [
            Assessment(
                id=unit_id(section_name, None),
                verdict="not_present",
                # The rubric's own description of what this section should contain,
                # folded into the sentence. It used to sit in a `recommendation` beside
                # this one - and unlike the per-variable case, where both sentences were
                # built from names already on the row, this one carries something that
                # appears nowhere else on screen. The field went; the fact did not.
                statement=(
                    f"The {section_name} section is not present in the document. "
                    f"It should cover: {spec.description}"
                ),
                section_name=section_name,
                optional=spec.optional,
            )
        ]
    return [
        Assessment(
            id=unit_id(section_name, variable.name),
            verdict="not_present",
            statement=f"{variable.name} is not present; the {section_name} section is absent.",
            section_name=section_name,
            variable_name=variable.name,
            optional=spec.optional or variable.optional,
        )
        for variable in spec.variables
    ]


def unit_id(section_name: str | None, variable_name: str | None) -> str:
    """A stable id for one rubric unit.

    Unique by construction, and no longer by enforcement: a unit carries one verdict,
    so the id needs no reason to disambiguate it and the contract check that policed
    "at most one finding per reason per unit" has nothing left to police.
    """
    return "|".join((section_name or "", variable_name or ""))
