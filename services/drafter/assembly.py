"""Deterministic assembly: the figures over comparable values.

Neither step reads prose. `summarise` groups the values a comparable product's verbatim
source states by the unit exactly as it is written - never converting, never pooling two
units, and never folding case, since `mIU/mL` and `MIU/mL` are different units - and
describes each group. A group is values that share a unit, not one measured cohort: they
may measure different endpoints, and one product may be reported by several sources. Every
reader says so; deciding which values measure the same thing would be its own model step.
"""

from __future__ import annotations

from collections.abc import Sequence

from shared.statistics import describe

from .models import GroupSummary, Observation

#: A group needs two values before it is a distribution rather than a number.
MIN_GROUP_SIZE = 2


def summarise(observations: Sequence[Observation]) -> list[GroupSummary]:
    groups: dict[str, list[tuple[str, float]]] = {}
    for observation in observations:
        value = observation.value
        if not observation.numeric_eligible or value is None or value.value is None:
            continue
        spelling = " ".join(value.unit.split())
        groups.setdefault(spelling, []).append((observation.id, value.value))
    summaries: list[GroupSummary] = []
    for spelling, members in groups.items():
        if len(members) < MIN_GROUP_SIZE:
            continue
        figures = describe([number for _, number in members])
        summaries.append(GroupSummary(
            unit=spelling, observation_ids=tuple(identifier for identifier, _ in members),
            count=figures.count, minimum=figures.minimum, maximum=figures.maximum,
            median=figures.median, lower_quartile=figures.lower_quartile, upper_quartile=figures.upper_quartile,
        ))
    return summaries
