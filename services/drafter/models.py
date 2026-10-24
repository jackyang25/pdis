"""Drafter's shapes: its configuration and the draft a run produces.

`configuration.py` loads and checks configuration; the stages fill a `DraftResult`;
`contract.py` decides whether a result is one this tool could have produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from shared import ai as _ai
from shared.ai import Effort, FailureCode, ModelTask, Verbosity

CONFIGS_DIR = Path(__file__).parent / "configs"


class LLMClientProtocol(Protocol):
    """The model surface Drafter needs, published so callers can inject one."""

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        trailing_text: str = "",
        task: ModelTask = "reasoning",
        effort: Effort | None = None,
        verbosity: Verbosity | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any] | None: ...


# --- configuration -----------------------------------------------------------------------

@dataclass(frozen=True)
class DrafterConfig:
    type_key: str
    org: str
    source_type: str
    intervention_class: str
    display_name: str
    #: Searcher source keys this product type reads.
    sources: tuple[str, ...]
    #: Domain framing for search planning, read into the prompt verbatim.
    query_guidance: str


# --- vocabularies ------------------------------------------------------------------------

#: A suggestion is a range for a numeric variable, one statement for any other, or the
#: model's finding that the evidence it was given cannot support either.
SUGGESTION_KINDS = ("range", "statement", "insufficient")
#: What an observation is evidence of. Kept apart in every reader: what has been done, and
#: what is being asked for.
BASES = ("comparable_product", "published_guidance")
LEANS_ON = ("comparable_products", "guidance", "both")
#: Which basis a suggestion leans on follows from what it cites, so it is read off the
#: cited observations rather than asked for: a model naming it separately could name one
#: basis and cite the other, and the contract then refused an answer whose citations
#: were sound.
LEANS_ON_BY_BASES: dict[frozenset[str], str] = {
    frozenset({"comparable_product"}): "comparable_products",
    frozenset({"published_guidance"}): "guidance",
    frozenset({"comparable_product", "published_guidance"}): "both",
}
STATUSES = ("complete", "failed")
#: Pipeline failures, recorded by code and never offered to a model.
FAILURE_CODES = ("search_planning_failed", "evidence_unavailable", "suggestion_failed")
#: The failures raised by a model or provider call, each carrying one of `CAUSE_CODES`
#: (`shared.ai.FAILURE_CODES`). `evidence_unavailable` is concluded from counts, not raised.
RAISED_FAILURES = ("search_planning_failed", "suggestion_failed")
CAUSE_CODES = _ai.FAILURE_CODES


# --- result ------------------------------------------------------------------------------

@dataclass(frozen=True)
class ObservedValue:
    value: float | None
    lower: float | None
    upper: float | None
    unit: str
    #: The words of the observation's quote that state the number, exactly as written.
    #: Code checks only that they are in the quote; what they mean is the reader's.
    text: str


@dataclass(frozen=True)
class Observation:
    """One thing a source says about one variable, in its own words."""
    id: str
    basis: str
    url: str
    title: str
    source_label: str
    product: str
    measure: str
    quote: str
    value: ObservedValue | None
    #: True only for a comparable product's value from a verbatim literature, registry or
    #: regulatory excerpt - the text that may supply a number.
    numeric_eligible: bool


@dataclass(frozen=True)
class SourceError:
    """Why a source failed in this run, in the provider's own words."""
    source: str
    message: str


@dataclass(frozen=True)
class GroupSummary:
    """Comparable values sharing one stated unit. Units are never converted or pooled."""
    unit: str
    #: The observations the values came from, in order: lineage is listed, never counted.
    observation_ids: tuple[str, ...]
    count: int
    minimum: float
    maximum: float
    median: float
    lower_quartile: float
    upper_quartile: float


@dataclass(frozen=True)
class Suggestion:
    kind: str
    minimum: str
    preferred: str
    statement: str
    rationale: str
    leans_on: str
    basis_ids: tuple[str, ...]


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    #: Why the call failed, for the two failures a call raises; None for `evidence_unavailable`.
    cause: FailureCode | None = None


@dataclass(frozen=True)
class VariableDraft:
    name: str
    label: str
    description: str
    evidence_domain: str
    status: str
    failure: Failure | None
    observations: tuple[Observation, ...]
    statistics: tuple[GroupSummary, ...]
    suggestion: Suggestion | None
    #: Sources retrieved for this variable whose reading failed twice and were set aside.
    unread_findings: int = 0
    #: Quotes a reader offered that their excerpt does not contain, so were not kept.
    unverified_quotes: int = 0


@dataclass(frozen=True)
class DraftResult:
    org: str
    source_type: str
    intervention_class: str
    indication: str
    display_name: str
    sources: tuple[str, ...]
    #: Sources every request to which failed in this run.
    failed_sources: tuple[str, ...]
    #: Sources this deployment has not configured, so they were never asked.
    unconfigured_sources: tuple[str, ...]
    #: The provider's message for every source that failed at least once.
    source_errors: tuple[SourceError, ...]
    variables: tuple[VariableDraft, ...]

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        def lists(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: lists(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [lists(item) for item in value]
            return value

        return lists(asdict(self))
