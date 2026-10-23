"""Descriptive statistics over a cohort of comparable values.

Shared because two services describe a cohort: Scout's calibration, over measurements admitted
against a document's target, and Drafter's, over what comparable products achieved. The
arithmetic is the same and must stay the same, so it lives once. These are descriptive
figures - a median is not a confidence interval and a quartile is not a probability.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean, stdev

DECIMALS = 3


def quantile(values: Sequence[float], probability: float) -> float:
    """Linear interpolation between ranks of already sorted values."""
    if not values:
        raise ValueError("at least one benchmark value is required")
    position = (len(values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return values[lower_index]
    fraction = position - lower_index
    return values[lower_index] + fraction * (values[upper_index] - values[lower_index])


def empirical_percentile(values: Sequence[float], target: float) -> float:
    """Share of values below the target, counting values equal to it as half."""
    below = sum(value < target for value in values)
    equal = sum(value == target for value in values)
    return (below + 0.5 * equal) / len(values)


@dataclass(frozen=True)
class Summary:
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    lower_quartile: float
    upper_quartile: float
    #: None for a single value, where there is no spread to report.
    standard_deviation: float | None


def describe(values: Sequence[float]) -> Summary:
    """The cohort's figures, rounded as every reader displays them."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("at least one value is required")
    return Summary(
        count=len(ordered),
        minimum=round(ordered[0], DECIMALS),
        maximum=round(ordered[-1], DECIMALS),
        mean=round(fmean(ordered), DECIMALS),
        median=round(quantile(ordered, 0.5), DECIMALS),
        lower_quartile=round(quantile(ordered, 0.25), DECIMALS),
        upper_quartile=round(quantile(ordered, 0.75), DECIMALS),
        standard_deviation=round(stdev(ordered), DECIMALS) if len(ordered) >= 2 else None,
    )
