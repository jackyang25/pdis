"""One Drafter run: from a product context to a draft of suggested targets.

```text
variables → search planning → retrieval → evidence reading → figures → suggestion
```

Every fan-out is one flat, bounded queue. A variable that cannot be planned, read or
suggested is recorded as failed, with its code, and the rest of the run carries on; a context
that does not exist stops the run before any search is spent.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace

from services.searcher import Finding, RetrievalIntent, SearchRuntime
from shared.batching import map_ordered
from shared.errors import ModelResponseError
from shared.vocabulary import AttributeDefinition, attribute_definitions, indications_for, search_term

from .assembly import summarise
from .configuration import SOURCE_TYPE, find_config
from .contract import validate_result_contract
from .models import (
    DraftResult,
    Failure,
    LLMClientProtocol,
    Observation,
    SourceError,
    Suggestion,
    VariableDraft,
)
from .retrieval import RetrievalReport, retrieve
from .stages.evidence_reader import ReadObservation, eligible_findings, read_finding
from .stages.search_planner import plan_searches
from .stages.suggester import suggest

logger = logging.getLogger(__name__)

PLANNING_WORKERS = 6
READING_WORKERS = 8
SUGGESTION_WORKERS = 6

ProgressFn = Callable[..., None]


def run_pipeline(
    *,
    org: str,
    intervention_class: str,
    indication: str,
    llm_client: LLMClientProtocol,
    runtime: SearchRuntime,
    progress_callback: ProgressFn | None = None,
) -> DraftResult:
    config = find_config(org, SOURCE_TYPE, intervention_class)
    if indication not in indications_for(intervention_class):
        raise ValueError(f"Unknown disease / condition {indication!r} for {intervention_class}.")
    variables = list(attribute_definitions(intervention_class))
    intervention_term, indication_term = search_term(intervention_class), search_term(indication)
    progress = progress_callback or (lambda *args, **kwargs: None)

    open_variables = variables
    failures: dict[str, Failure] = {}
    intents: dict[str, RetrievalIntent] = {}
    if open_variables:
        intents = _plan(open_variables, config, llm_client, indication_term, intervention_term, failures, progress)

    report = RetrievalReport(found={}, failed_sources=(), unconfigured_sources=(), failed_for={}, source_errors={})
    if intents:
        progress("search")
        report = retrieve(
            list(intents.values()), sources=config.sources, runtime=runtime,
            progress=lambda done, total: progress("search", completed=done, total=total),
        )
    found = report.found

    planned = [variable for variable in open_variables if variable.name in intents]
    observations, unread = _read(planned, found, llm_client, indication_term, intervention_term, progress)
    for variable in planned:
        observations.setdefault(variable.name, [])
        # Nothing to suggest from because the sources could not be read is a failure of the
        # run, not a reading of the evidence; "not enough evidence" would claim the latter.
        unreachable = [*report.failed_for.get(variable.name, ())]
        if not observations[variable.name] and (unreachable or unread.get(variable.name, 0)):
            reasons = []
            if unreachable:
                reasons.append(f"these sources failed: {', '.join(unreachable)}")
            if unread.get(variable.name, 0):
                reasons.append(f"{unread[variable.name]} retrieved sources could not be read")
            failures[variable.name] = Failure(
                "evidence_unavailable", f"No evidence could be read for this variable; {'; '.join(reasons)}.",
            )
    planned = [variable for variable in planned if variable.name not in failures]
    suggestions = _suggest(planned, observations, llm_client, indication_term, intervention_term, failures, progress)

    drafts = [
        _variable(variable, observations.get(variable.name, []), suggestions.get(variable.name),
                  failures.get(variable.name), unread.get(variable.name, 0))
        for variable in variables
    ]
    result = DraftResult(
        org=org, source_type=SOURCE_TYPE, intervention_class=intervention_class, indication=indication,
        display_name=config.display_name, sources=config.sources,
        failed_sources=report.failed_sources, unconfigured_sources=report.unconfigured_sources,
        source_errors=tuple(SourceError(source, message) for source, message in report.source_errors.items()),
        variables=tuple(drafts),
    )
    validate_result_contract(result.to_dict())
    return result


def _counter(progress: ProgressFn, stage: str, total: int) -> Callable[[], None]:
    lock, done = threading.Lock(), [0]
    progress(stage, completed=0, total=total)

    def tick() -> None:
        with lock:
            done[0] += 1
            progress(stage, completed=done[0], total=total)

    return tick


def _plan(variables, config, llm_client, indication, intervention_term, failures, progress) -> dict[str, RetrievalIntent]:
    tick = _counter(progress, "plan", len(variables))

    def plan(variable: AttributeDefinition) -> RetrievalIntent | None:
        try:
            return plan_searches(variable, config, llm_client, indication=indication, intervention_term=intervention_term)
        except Exception as exc:  # noqa: BLE001 - a provider error costs this variable, never the run
            failures[variable.name] = Failure("search_planning_failed", _failure_message(exc))
            return None
        finally:
            tick()

    planned = map_ordered(list(variables), plan, workers=PLANNING_WORKERS)
    return {variable.name: intent for variable, intent in zip(variables, planned, strict=True) if intent is not None}


def _read(variables, found, llm_client, indication, intervention_term, progress):
    pairs = [(variable, finding) for variable in variables for finding in eligible_findings(found.get(variable.name, []))]
    tick = _counter(progress, "evidence", len(pairs))

    def read(pair: tuple[AttributeDefinition, Finding]) -> list[ReadObservation] | None:
        try:
            return read_finding(pair[0], pair[1], llm_client, indication=indication, intervention_term=intervention_term)
        except Exception:  # noqa: BLE001 - one unreadable source is set aside and counted
            logger.warning("Evidence reading failed for %s from %s", pair[0].name, pair[1].url, exc_info=True)
            return None
        finally:
            tick()

    readings = map_ordered(pairs, read, workers=READING_WORKERS)
    observations: dict[str, list[Observation]] = {}
    unread: dict[str, int] = {}
    for (variable, _), reading in zip(pairs, readings, strict=True):
        if reading is None:
            unread[variable.name] = unread.get(variable.name, 0) + 1
            continue
        held = observations.setdefault(variable.name, [])
        for item in reading:
            held.append(Observation(id=f"{variable.name}:o{len(held) + 1}", **vars(item)))
    return observations, unread


def _suggest(variables, observations, llm_client, indication, intervention_term, failures, progress) -> dict[str, Suggestion]:
    tick = _counter(progress, "suggest", len(variables))

    def run(variable: AttributeDefinition) -> Suggestion | None:
        held = observations.get(variable.name, [])
        try:
            return suggest(variable, held, summarise(held), llm_client, indication=indication, intervention_term=intervention_term)
        except Exception as exc:  # noqa: BLE001 - a provider error costs this variable, never the run
            failures[variable.name] = Failure("suggestion_failed", _failure_message(exc))
            return None
        finally:
            tick()

    made = map_ordered(list(variables), run, workers=SUGGESTION_WORKERS)
    return {variable.name: suggestion for variable, suggestion in zip(variables, made, strict=True) if suggestion is not None}


def _variable(
    variable: AttributeDefinition,
    observations: Sequence[Observation],
    suggestion: Suggestion | None,
    failure: Failure | None,
    unread: int,
) -> VariableDraft:
    base = VariableDraft(
        name=variable.name, label=_label(variable.name), description=variable.description.strip(),
        evidence_domain=variable.evidence_domain, status="complete", failure=None,
        observations=tuple(observations), statistics=tuple(summarise(observations)),
        suggestion=suggestion, unread_findings=unread,
    )
    if failure is not None:
        return replace(base, status="failed", failure=failure, suggestion=None)
    return base


def _failure_message(exc: Exception) -> str:
    """The reason, readable on the result: the stage's own words, or the provider's."""
    if isinstance(exc, ModelResponseError):
        return str(exc)
    logger.warning("Drafter stage failed", exc_info=exc)
    return f"The model service failed: {exc}" if str(exc) else f"The model service failed ({type(exc).__name__})."


def _label(name: str) -> str:
    words = name.split(".", 1)[-1].replace("_", " ")
    return words[:1].upper() + words[1:]
