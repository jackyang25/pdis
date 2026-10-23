"""One variable's suggested target, from the evidence the run holds for it.

One variable per request: a suggestion weighs one variable's evidence, and another
variable's would only be noise in the prompt. The model owns the judgement - which values
to propose, which basis to lean on, why. Code checks the shape: the kind paired with its
fields, and a basis drawn only from this variable's own observations.
"""

from __future__ import annotations

from collections.abc import Sequence

from shared.ai import request_structured
from shared.errors import ModelResponseError
from shared.references import reference_array
from shared.vocabulary import AttributeDefinition

from ..contract import check_suggestion
from ..models import LEANS_ON, SUGGESTION_KINDS, GroupSummary, LLMClientProtocol, Observation, Suggestion

VARIABLES_PER_REQUEST = 1
MAX_TOKENS = 16000  # reasoning counts against it; a reply cut off is a failure


def build_system_prompt() -> str:
    return (
        "You suggest a target for ONE variable of an intervention target product profile (iTPP) "
        "that a team is drafting, from the evidence supplied and nothing else.\n\n"
        "Choose a kind:\n"
        "- range: for a variable measured in numbers. Give a minimum (the least a product must "
        "reach to be worth developing) and a preferred value (what would make it clearly better), "
        "each written with its unit. Either may be blank if the evidence supports only one.\n"
        "- statement: for a variable described in words. Give one short requirement.\n"
        "- insufficient: the evidence cannot support a suggestion. Give no values and no basis.\n\n"
        "Every suggestion cites the observation IDs it rests on in basis_ids, and says which kind of "
        "evidence it leans on: comparable_products (what similar products achieved), guidance (what "
        "a published profile or guideline asks), or both - and then cites at least one of each. "
        "Never state a number the evidence does not support. The rationale is one or two sentences "
        "naming the evidence it leans on."
    )


def suggest(
    variable: AttributeDefinition,
    observations: Sequence[Observation],
    statistics: Sequence[GroupSummary],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_term: str,
) -> Suggestion:
    if not observations:
        # Nothing could be cited, so nothing could be suggested; no model is asked to say so.
        return Suggestion(kind="insufficient", minimum="", preferred="", statement="", rationale="", leans_on="", basis_ids=())
    by_id = {observation.id: {"basis": observation.basis} for observation in observations}
    message = _message(variable, observations, statistics, indication=indication, intervention_term=intervention_term)
    schema = _schema([observation.id for observation in observations])
    error, budget = "", MAX_TOKENS
    for attempt in range(2):
        repair = f"\n\nYour prior answer was invalid: {error}. Answer again." if attempt and error else ""
        try:
            payload = request_structured(
                llm_client, build_system_prompt(), message + repair,
                schema_name="drafter_suggestion", schema=schema, max_tokens=budget,
            )
        except RuntimeError:
            # A provider error, most often a reply cut off at its limit: live runs saw the model
            # spend a whole budget reasoning. One more try, with twice the room, usually lands.
            if attempt:
                raise
            error, budget = "", MAX_TOKENS * 2
            continue
        if not isinstance(payload, dict):
            error = "no structured answer was returned"
            continue
        candidate = {key: payload.get(key) for key in ("kind", "minimum", "preferred", "statement", "rationale", "leans_on")}
        candidate["basis_ids"] = list(dict.fromkeys(payload.get("basis_ids") or []))
        try:
            check_suggestion(candidate, variable.name, by_id)
        except ValueError as exc:
            error = str(exc).removeprefix(f"{variable.name}: ")
            continue
        return Suggestion(
            kind=candidate["kind"],
            minimum=str(candidate["minimum"] or "").strip(),
            preferred=str(candidate["preferred"] or "").strip(),
            statement=str(candidate["statement"] or "").strip(),
            rationale=str(candidate["rationale"] or "").strip(),
            leans_on=candidate["leans_on"] or "",
            basis_ids=tuple(candidate["basis_ids"]),
        )
    raise ModelResponseError(f"Suggestion failed for {variable.name}: {error}.")


def _schema(observation_ids: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "minimum", "preferred", "statement", "rationale", "leans_on", "basis_ids"],
        "properties": {
            "kind": {"type": "string", "enum": list(SUGGESTION_KINDS)},
            # Blank unless the kind uses them. A conditional requirement is the one thing this
            # schema cannot express, so the kind carries the condition and code checks it.
            "minimum": {"type": "string"},
            "preferred": {"type": "string"},
            "statement": {"type": "string"},
            "rationale": {"type": "string"},
            "leans_on": {"type": "string", "enum": [*LEANS_ON, ""]},
            "basis_ids": reference_array(observation_ids),
        },
    }


def _message(variable, observations, statistics, *, indication, intervention_term) -> str:
    lines = []
    for observation in observations:
        value = ""
        if observation.value is not None:
            parts = [f"{observation.value.value:g}" if observation.value.value is not None else "",
                     f"{observation.value.lower:g}-{observation.value.upper:g}"
                     if observation.value.lower is not None and observation.value.upper is not None else ""]
            value = " (" + " ".join(part for part in parts if part) + f" {observation.value.unit})".replace("  ", " ")
        who = observation.product or observation.source_label
        lines.append(f"[{observation.id}] {observation.basis} · {who} · {observation.source_label}: \"{observation.quote}\"{value}")
    figures = [
        f"- {group.count} values stated in {group.unit}: median {group.median:g}, "
        f"middle half {group.lower_quartile:g}-{group.upper_quartile:g}, range {group.minimum:g}-{group.maximum:g}"
        for group in statistics
    ]
    return (
        f"Product type: {intervention_term}. Disease / condition: {indication}.\n"
        f"Variable: {variable.name}\nWhat it covers: {variable.description.strip()}\n\n"
        "Observations:\n" + "\n".join(lines)
        + ("\n\nValues stated in each unit across the comparable observations above, computed. They may "
           "measure different things, and one product may be reported by more than one source:\n"
           + "\n".join(figures) if figures else "")
    )
