"""Whether a draft result is one Drafter could have produced.

Run on every result the pipeline returns and on every result a browser sends back for
export. The checks are structural - known IDs, the pairing of a suggestion's kind with its
fields, which basis may supply a number, figures that are the arithmetic of the observations
they sit beside - and never a judgement of what a suggestion means.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from shared.quotes import quote_in_text

from .assembly import summarise
from .models import (
    BASES,
    CAUSE_CODES,
    FAILURE_CODES,
    LEANS_ON_BY_BASES,
    RAISED_FAILURES,
    STATUSES,
    SUGGESTION_KINDS,
    Observation,
    ObservedValue,
)


def validate_result_contract(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("A draft result is an object")
    for key in ("org", "source_type", "intervention_class", "indication"):
        if not str(result.get(key) or "").strip():
            raise ValueError(f"{key} is required")
    variables = result.get("variables") or []
    if not variables:
        raise ValueError("A draft result holds at least one variable")
    names = [variable.get("name") for variable in variables]
    if len(set(names)) != len(names):
        raise ValueError("Variable names must be unique")
    for variable in variables:
        _variable(variable)
    return result


def _variable(variable: dict[str, Any]) -> None:
    name = variable.get("name")
    status = variable.get("status")
    if status not in STATUSES:
        raise ValueError(f"{name}: unknown status")
    observations = variable.get("observations") or []
    by_id = {observation.get("id"): observation for observation in observations}
    if len(by_id) != len(observations):
        raise ValueError(f"{name}: observation ids must be unique")
    for observation in observations:
        _observation(observation, name)
    if variable.get("statistics", []) != _figures(observations):
        raise ValueError(f"{name}: the figures are not those of the variable's observations")
    for count in ("unread_findings", "unverified_quotes"):
        value = variable.get(count, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name}: {count} is a count")

    failure, suggestion = variable.get("failure"), variable.get("suggestion")
    if status == "failed":
        if not failure or failure.get("code") not in FAILURE_CODES or not str(failure.get("message") or "").strip():
            raise ValueError(f"{name}: a failed variable carries a known failure code and message")
        cause = failure.get("cause")
        if failure["code"] in RAISED_FAILURES:
            if cause not in CAUSE_CODES:
                raise ValueError(f"{name}: a failed call carries a known cause")
        elif cause is not None:
            raise ValueError(f"{name}: a variable left without evidence carries no call's cause")
        if suggestion is not None:
            raise ValueError(f"{name}: a failed variable carries no suggestion")
    elif failure is not None:
        raise ValueError(f"{name}: only a failed variable carries a failure")

    if status == "complete":
        if suggestion is None:
            raise ValueError(f"{name}: a completed row carries its suggestion")
        check_suggestion(suggestion, name, by_id)



def _figures(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The figures `assembly.summarise` computes from these observations, as stored."""
    held = []
    for observation in observations:
        value = observation.get("value")
        if value is not None and (
            not isinstance(value, dict)
            or any(value.get(key) is not None and not isinstance(value.get(key), (int, float))
                   for key in ("value", "lower", "upper"))
        ):
            raise ValueError("an observation's value is numbers and a unit")
        held.append(Observation(
            id=str(observation.get("id")), basis=str(observation.get("basis")), url="", title="",
            source_label="", product="", measure="", quote="",
            value=ObservedValue(value=value.get("value"), lower=value.get("lower"), upper=value.get("upper"),
                                unit=str(value.get("unit") or ""), text=str(value.get("text") or ""))
            if value is not None else None,
            numeric_eligible=bool(observation.get("numeric_eligible")),
        ))
    # As stored: a saved result holds its lineage as a list, not a tuple.
    return [{**asdict(group), "observation_ids": list(group.observation_ids)} for group in summarise(held)]


def _observation(observation: dict[str, Any], name: str) -> None:
    if observation.get("basis") not in BASES:
        raise ValueError(f"{name}: unknown observation basis")
    if not str(observation.get("quote") or "").strip():
        raise ValueError(f"{name}: an observation quotes its source")
    value = observation.get("value")
    if value is not None and not quote_in_text(str(value.get("text") or ""), str(observation["quote"])):
        raise ValueError(f"{name}: a stated value carries the words of its quote that state it")
    if observation.get("numeric_eligible") and (
        observation.get("basis") != "comparable_product" or observation.get("value") is None
    ):
        raise ValueError(f"{name}: only a comparable product's stated value may enter statistics")


def check_suggestion(suggestion: dict[str, Any], name: str, observations: dict[str, dict]) -> None:
    """The pairing of a suggestion's kind with its fields and basis; raises ValueError."""
    kind = suggestion.get("kind")
    if kind not in SUGGESTION_KINDS:
        raise ValueError(f"{name}: unknown suggestion kind")
    minimum, preferred, statement = (str(suggestion.get(key) or "").strip() for key in ("minimum", "preferred", "statement"))
    basis_ids = suggestion.get("basis_ids") or []
    leans_on = suggestion.get("leans_on") or ""
    if not set(basis_ids) <= set(observations):
        raise ValueError(f"{name}: a suggestion cites only the variable's own observations")
    if kind == "insufficient":
        if minimum or preferred or statement or basis_ids or leans_on:
            raise ValueError(f"{name}: insufficient evidence carries no values and no basis")
        return
    if not basis_ids:
        raise ValueError(f"{name}: a suggestion cites the observations it rests on")
    if not str(suggestion.get("rationale") or "").strip():
        raise ValueError(f"{name}: a suggestion gives its rationale")
    if kind == "range" and (statement or not (minimum or preferred)):
        raise ValueError(f"{name}: a range carries a minimum or a preferred value, and no statement")
    if kind == "statement" and (minimum or preferred or not statement):
        raise ValueError(f"{name}: a statement carries its text, and no range")
    # Derived from the citations by the suggester, so a saved result whose label and
    # citations disagree was edited after the run.
    cited = frozenset(observations[identifier].get("basis") for identifier in basis_ids)
    if leans_on != LEANS_ON_BY_BASES.get(cited):
        raise ValueError(f"{name}: the basis it leans on is the basis it cites")
