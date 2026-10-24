"""Assemble the run's retrieval scope: what this run is about, and who said so.

Two suppliers, and the difference matters more than the values. The header supplies the
condition and the intervention class, because a reader chose them. The document supplies
the geography, because a target profile states where it is aimed and nobody should have
to retype it.

The document half is one bounded call per dimension, and it is a *normalisation* rather
than an extraction: the value is already in `Attribute.document_target`, bound and cited
by the target resolver. What this stage decides is narrower - whether that text names a
place a provider's location field could index, and if so which phrase. "LMIC focus,
Gavi-eligible countries" is a real document target and not a location a registry holds.

Which attribute states which dimension is declared in `shared/attributes.yaml` as
`supplies_scope`, never matched by name here. A stage hunting for `*.target_countries`
works until an intervention class names it something else, and then finds nothing and
reports success.
"""

from __future__ import annotations

from shared.ai import Effort, ModelTask

from ..ai import request_validated
from ..ai_contracts import run_scope_value
from ..context import render_canonical_binding
from ..models import (
    RUN_SCOPE_DIMENSIONS,
    Attribute,
    LLMClientProtocol,
    RetrievalScopeLedger,
)

#: One reading per scope dimension: a per-item decision about one bound target.
DIMENSIONS_PER_REQUEST = 1
#: The fast tier at low effort: the place is already bound and cited by the target
#: resolver, and the stage decides only whether that text names an indexable place.
TASK: ModelTask = "fast"
EFFORT: Effort = "low"
#: Reasoning counts against the budget, so it is sized for the thinking, not the reply.
DEFAULT_MAX_TOKENS = 8000


def build_system_prompt(dimension: str) -> str:
    return f"""You are reading one variable of a product-development document to decide what it says about the run's {dimension}.

`found`: "yes" only if the text names a place a clinical-trial registry or regulator
would hold in a location field - a country, or a region a registry indexes such as
"sub-Saharan Africa". "no" for anything else, including a policy category like "LMIC",
"low- and middle-income countries", "Gavi-eligible", "global", or a tier or market
description. Those describe a class of country, not a place a database can be asked
about, and a request built from one returns nothing while looking like a filter.

`value`: when found, the single phrase a provider would index, in the document's own
words where they are already indexable. One place, never a list: if the document names
several, give the one its own text treats as primary. Empty when `found` is "no".

`block_ids`: the blocks the value was read from. Required when `found` is "yes" - a
value that cannot be pointed at is a value nobody can check. Empty when it is "no".

You are not deciding where the product should be studied, and you are not completing a
document that left this open. A document that states no geography narrows nothing, which
is a correct and common answer."""


def _user_message(attribute: Attribute) -> str:
    return (
        f"variable: {attribute.name}\n"
        f"What this variable covers: {attribute.description.strip()}\n\n"
        "What the document states for it, by the block each passage was read from:\n"
        f"{render_canonical_binding(attribute) or '(the document stated nothing for this variable)'}\n\n"
        "Decide now."
    )


def resolve_retrieval_scope(
    attributes: list[Attribute],
    llm_client: LLMClientProtocol | None,
    *,
    condition: str,
    intervention_class: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> RetrievalScopeLedger:
    """Return one complete ledger: header values, document values, and the gaps.

    A dimension no attribute supplies, whose attribute bound nothing, or whose document
    states no indexable place is recorded `unset`: nobody supplied it, which the ledger
    keeps distinguishable from a reader who deliberately widened the search. A reading
    that stays invalid after its retry raises instead, because recording it `unset`
    would silently widen the search on a failure.
    """
    supplied: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    if condition.strip():
        supplied["condition"] = (condition.strip(), "header", ())
    if intervention_class.strip():
        supplied["intervention"] = (intervention_class.strip(), "header", ())

    for dimension in RUN_SCOPE_DIMENSIONS:
        if dimension in supplied:
            continue
        source = _supplying_attribute(attributes, dimension)
        if source is None or llm_client is None:
            continue
        resolved = _read_dimension(source, dimension, llm_client, max_tokens=max_tokens)
        if resolved:
            supplied[dimension] = resolved

    return RetrievalScopeLedger.of(**supplied)


def _supplying_attribute(
    attributes: list[Attribute],
    dimension: str,
) -> Attribute | None:
    """The one attribute declaring itself the supplier, with a bound document target."""
    for attribute in attributes:
        if attribute.supplies_scope != dimension:
            continue
        if not attribute.document_target.strip() or not attribute.block_ids:
            # Declared supplier, nothing bound. Not an error: a document may simply not
            # state its geography, and inventing one here is the failure to avoid.
            return None
        return attribute
    return None


def _read_dimension(
    attribute: Attribute,
    dimension: str,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> tuple[str, str, tuple[str, ...]] | None:
    allowed = list(dict.fromkeys(attribute.block_ids))

    def parse(parsed: object) -> tuple[str, str, tuple[str, ...]] | None:
        if not isinstance(parsed, dict):
            raise ValueError("no structured reading was returned")
        found = str(parsed.get("found", "")).strip().lower()
        if found not in {"yes", "no"}:
            raise ValueError('found must be "yes" or "no"')
        if found == "no":
            return None
        value = " ".join(str(parsed.get("value") or "").split())
        cited = tuple(
            block_id
            for block_id in dict.fromkeys(
                str(item).strip() for item in parsed.get("block_ids") or []
            )
            if block_id in allowed
        )
        if not value or not cited:
            # A claimed reading with no phrase or no supplied block is not a reading.
            raise ValueError(
                'found is "yes" but the value is empty or cites no supplied block'
            )
        return (value, "document", cited)

    return request_validated(
        llm_client,
        run_scope_value(allowed),
        build_system_prompt(dimension),
        _user_message(attribute),
        max_tokens=max_tokens,
        task=TASK,
        effort=EFFORT,
        parse=parse,
        failure=f"Run scope {dimension} could not be read from {attribute.name}",
    )
