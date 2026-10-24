"""One variable's suggested target, from the evidence the run holds for it.

One variable per request: a suggestion weighs one variable's evidence, and another
variable's would only be noise in the prompt. The model owns the judgement - which values
to propose, which observations to rest on, why. Code checks the shape and reads one fact
off the answer instead of asking for it: which basis the suggestion leans on is whatever
its cited observations are evidence of.

The schema states each kind's shape as its own variant - a range with a minimum, a range
with only a preferred value, a statement, or insufficient evidence - so a reply that pairs
a kind with the wrong fields is one the model cannot produce, rather than one the contract
refuses after the call was paid for.
"""

from __future__ import annotations

from collections.abc import Sequence

from shared.ai import Effort, ModelTask, request_validated
from shared.references import reference_array
from shared.schemas import blank_text, non_empty_text
from shared.vocabulary import AttributeDefinition, searchable_attribute_phrase

from ..contract import check_suggestion
from ..models import LEANS_ON_BY_BASES, GroupSummary, LLMClientProtocol, Observation, Suggestion

VARIABLES_PER_REQUEST = 1
#: The reasoning tier: weighing what comparable products achieved against what guidance
#: asks, and choosing a minimum and a preferred value, is the one judgement Drafter makes.
TASK: ModelTask = "reasoning"
#: Medium. The prompt is under a thousand tokens of observations and figures; at the
#: provider's default effort live runs spent 16k and then 32k reasoning tokens on it and
#: were still cut off. A reply cut off here is asked again at low effort, same budget.
EFFORT: Effort = "medium"
#: The answer is a few short fields; the rest is reasoning room.
MAX_TOKENS = 12000


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
        "Every suggestion cites in basis_ids the observation IDs it rests on. Each observation is "
        "evidence of what a comparable product achieved or of what published guidance asks; cite "
        "the ones your suggestion actually leans on. Only observations marked as figures may supply "
        "a number; the others are context. Never state a number the evidence does not support. "
        "Every answer gives a rationale of one or two sentences: for a range or a statement, "
        "naming the evidence it leans on; for insufficient, saying what the evidence lacks. "
        "The rationale is read by the team, who never see observation IDs: name evidence by "
        "its product or its source, and keep the IDs to basis_ids."
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

    def parse(payload: dict | None) -> Suggestion:
        answer = payload.get("suggestion") if isinstance(payload, dict) else None
        if not isinstance(answer, dict):
            raise ValueError("no structured answer was returned")
        basis_ids = tuple(dict.fromkeys(answer.get("basis_ids") or []))
        unknown = [identifier for identifier in basis_ids if identifier not in by_id]
        if unknown:
            raise ValueError(f"cites observations this variable does not hold: {unknown}")
        cited = frozenset(by_id[identifier]["basis"] for identifier in basis_ids)
        suggestion = Suggestion(
            kind=str(answer.get("kind") or ""),
            minimum=" ".join(str(answer.get("minimum") or "").split()),
            preferred=" ".join(str(answer.get("preferred") or "").split()),
            statement=" ".join(str(answer.get("statement") or "").split()),
            rationale=" ".join(str(answer.get("rationale") or "").split()),
            leans_on=LEANS_ON_BY_BASES.get(cited, ""),
            basis_ids=basis_ids,
        )
        try:
            check_suggestion(vars(suggestion), variable.name, by_id)
        except ValueError as exc:
            raise ValueError(str(exc).removeprefix(f"{variable.name}: ")) from exc
        if not suggestion.rationale:
            raise ValueError("a suggestion gives its rationale")
        return suggestion

    return request_validated(
        llm_client, build_system_prompt(),
        _message(variable, observations, statistics, indication=indication, intervention_term=intervention_term),
        schema_name="drafter_suggestion", schema=_schema([observation.id for observation in observations]),
        max_tokens=MAX_TOKENS, task=TASK, effort=EFFORT,
        parse=parse, failure=f"Suggestion failed for {variable.name}",
        repair=lambda error: f"\n\nYour prior answer was invalid: {error}. Answer again.",
    )


def _schema(observation_ids: list[str]) -> dict:
    """One variant per kind, nested under `suggestion` because a strict root is an object."""
    cited = {**reference_array(observation_ids), "minItems": 1}
    text = non_empty_text()

    def variant(kind: str, *, minimum: dict, preferred: dict, statement: dict, basis_ids: dict) -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "minimum", "preferred", "statement", "rationale", "basis_ids"],
            "properties": {
                "kind": {"type": "string", "enum": [kind]},
                "minimum": minimum,
                "preferred": preferred,
                "statement": statement,
                # Every model answer explains itself, insufficient included. Only the
                # insufficient code writes without asking a model has an empty rationale.
                "rationale": text,
                "basis_ids": basis_ids,
            },
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["suggestion"],
        "properties": {"suggestion": {"anyOf": [
            variant("range", minimum=text, preferred={"type": "string"}, statement=blank_text(), basis_ids=cited),
            variant("range", minimum=blank_text(), preferred=text, statement=blank_text(), basis_ids=cited),
            variant("statement", minimum=blank_text(), preferred=blank_text(), statement=text, basis_ids=cited),
            variant("insufficient", minimum=blank_text(), preferred=blank_text(), statement=blank_text(),
                    basis_ids={"type": "array", "items": {"type": "string"}, "maxItems": 0}),
        ]}},
    }


def _message(variable, observations, statistics, *, indication, intervention_term) -> str:
    """The variable, each observation as the reader recorded it, and the computed figures.

    Each observation says what was measured, the number the reader took from its quote and
    whether that number may supply a figure; each figure says which observations it was
    computed from, so a number in the figures can be traced to the quotes behind it.
    """
    lines = []
    for observation in observations:
        who = observation.product or observation.source_label
        parts = [f"[{observation.id}] {observation.basis}", who, observation.source_label]
        if observation.measure:
            parts.append(f"measures: {observation.measure}")
        line = " · ".join(parts) + f': "{observation.quote}"'
        if observation.value is not None:
            line += f" | read as {_number(observation.value)}" + (
                " (may supply a figure)" if observation.numeric_eligible else " (context, not a figure)"
            )
        lines.append(line)
    figures = [
        f"- {group.count} values stated in {group.unit}, from {', '.join(group.observation_ids)}: "
        f"median {group.median:g}, middle half {group.lower_quartile:g}-{group.upper_quartile:g}, "
        f"range {group.minimum:g}-{group.maximum:g}"
        for group in statistics
    ]
    return (
        f"Product type: {intervention_term}. Disease / condition: {indication}.\n"
        f"Variable: {searchable_attribute_phrase(variable.name)}\n"
        f"What it covers: {variable.description.strip()}\n\n"
        "Observations:\n" + "\n".join(lines)
        + ("\n\nValues stated in each unit across the comparable observations above, computed. They may "
           "measure different things, and one product may be reported by more than one source:\n"
           + "\n".join(figures) if figures else "")
    )


def _number(value) -> str:
    """The reader's number as one phrase: a figure, a range, or a figure within a range."""
    parts = []
    if value.value is not None:
        parts.append(f"{value.value:g}")
    if value.lower is not None and value.upper is not None:
        parts.append(f"{value.lower:g}-{value.upper:g}")
    return " ".join([*parts, value.unit]).strip()
