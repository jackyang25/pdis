"""Whether a draft result is one Drafter could have produced.

Run on every result the pipeline returns and on every result a browser sends back for
export. The checks are structural - known IDs, the pairing of a suggestion's kind with its
fields, which basis may supply a number - and never a judgement of what a suggestion means.
"""

from __future__ import annotations

from typing import Any

from .models import (
    BASES,
    FAILURE_CODES,
    LEANS_ON,
    STATUSES,
    SUGGESTION_KINDS,
)

#: A suggestion that leans on one basis cites only that basis; one leaning on both cites each.
_LEANS_ON_BASES = {
    "comparable_products": {"comparable_product"},
    "guidance": {"published_guidance"},
    "both": {"comparable_product", "published_guidance"},
}


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

    failure, suggestion = variable.get("failure"), variable.get("suggestion")
    if status == "failed":
        if not failure or failure.get("code") not in FAILURE_CODES or not str(failure.get("message") or "").strip():
            raise ValueError(f"{name}: a failed variable carries a known failure code and message")
        if suggestion is not None:
            raise ValueError(f"{name}: a failed variable carries no suggestion")
    elif failure is not None:
        raise ValueError(f"{name}: only a failed variable carries a failure")

    if status == "complete":
        if suggestion is None:
            raise ValueError(f"{name}: a completed row carries its suggestion")
        check_suggestion(suggestion, name, by_id)



def _observation(observation: dict[str, Any], name: str) -> None:
    if observation.get("basis") not in BASES:
        raise ValueError(f"{name}: unknown observation basis")
    if not str(observation.get("quote") or "").strip():
        raise ValueError(f"{name}: an observation quotes its source")
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
    if not basis_ids or leans_on not in LEANS_ON:
        raise ValueError(f"{name}: a suggestion names its basis")
    if not str(suggestion.get("rationale") or "").strip():
        raise ValueError(f"{name}: a suggestion gives its rationale")
    if kind == "range" and (statement or not (minimum or preferred)):
        raise ValueError(f"{name}: a range carries a minimum or a preferred value, and no statement")
    if kind == "statement" and (minimum or preferred or not statement):
        raise ValueError(f"{name}: a statement carries its text, and no range")
    cited = {observations[identifier].get("basis") for identifier in basis_ids}
    if cited != _LEANS_ON_BASES[leans_on]:
        raise ValueError(f"{name}: the basis it leans on must be the basis it cites")
