"""One Drafter run: from a product context to a draft of suggested targets.

```text
variables → search planning → retrieval → evidence reading → figures → suggestion
```

Every fan-out is one flat, bounded queue reporting completed/total. A variable that cannot be
planned, read or suggested is recorded as failed, with its code and the call's cause, and the
rest of the run carries on; a context that does not exist, or a programming error, stops the
run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import TypeVar

from services.searcher import Finding, RetrievalIntent, SearchRuntime
from shared.ai import RECORDABLE_FAILURES, failure_code
from shared.batching import map_ordered
from shared.errors import ModelResponseError
from shared.vocabulary import (
    AttributeDefinition,
    attribute_definitions,
    attribute_label,
    indications_for,
    search_term,
)

from .assembly import summarise
from .configuration import SOURCE_TYPE, find_config
from .contract import validate_result_contract
from .models import (
    DraftResult,
    Failure,
    LLMClientProtocol,
    MAX_INTENDED_USE_CHARS,
    Observation,
    SourceError,
    Suggestion,
    VariableDraft,
)
from .retrieval import RetrievalReport, retrieve
from .stages.evidence_reader import Reading, eligible_findings, read_finding
from .stages.search_planner import plan_searches
from .stages.suggester import suggest

logger = logging.getLogger(__name__)

PLANNING_WORKERS = 6
READING_WORKERS = 8
SUGGESTION_WORKERS = 6


ProgressFn = Callable[..., None]
_T = TypeVar("_T")
_R = TypeVar("_R")


def run_pipeline(
    *,
    org: str,
    intervention_class: str,
    indication: str,
    llm_client: LLMClientProtocol,
    runtime: SearchRuntime,
    intended_use: str = "",
    progress_callback: ProgressFn | None = None,
) -> DraftResult:
    config = find_config(org, SOURCE_TYPE, intervention_class)
    if indication not in indications_for(intervention_class):
        raise ValueError(f"Unknown disease / condition {indication!r} for {intervention_class}.")
    intended_use = " ".join(intended_use.split())
    if len(intended_use) > MAX_INTENDED_USE_CHARS:
        raise ValueError(f"The intended use is at most {MAX_INTENDED_USE_CHARS} characters.")
    variables = list(attribute_definitions(intervention_class))
    intervention_term, indication_term = search_term(intervention_class), search_term(indication)
    progress = progress_callback or (lambda *args, **kwargs: None)

    failures: dict[str, Failure] = {}
    intents = _plan(variables, config, llm_client, indication_term, intervention_term, intended_use, failures, progress)

    report = RetrievalReport(found={}, failed_sources=(), unconfigured_sources=(), failed_for={},
                             source_errors={}, asked={})
    if intents:
        progress("search")
        report = retrieve(
            list(intents.values()), sources=config.sources, runtime=runtime,
            progress=lambda done, total: progress("search", completed=done, total=total),
        )

    planned = [variable for variable in variables if variable.name in intents]
    observations, unread, unverified = _read(planned, report.found, llm_client, indication_term, intervention_term,
                                             config.programme_context, progress)
    for variable in planned:
        failure = _evidence_failure(
            variable.name, observations.get(variable.name, []), report,
            unread.get(variable.name, 0), unverified.get(variable.name, 0),
        )
        if failure is not None:
            failures[variable.name] = failure
    planned = [variable for variable in planned if variable.name not in failures]
    suggestions = _suggest(planned, observations, llm_client, indication_term, intervention_term,
                           config.programme_context, intended_use, failures, progress)

    drafts = [
        _variable(variable, observations.get(variable.name, []), suggestions.get(variable.name),
                  failures.get(variable.name), unread.get(variable.name, 0), unverified.get(variable.name, 0))
        for variable in variables
    ]
    result = DraftResult(
        org=org, source_type=SOURCE_TYPE, intervention_class=intervention_class, indication=indication,
        intended_use=intended_use, display_name=config.display_name, sources=config.sources,
        failed_sources=report.failed_sources, unconfigured_sources=report.unconfigured_sources,
        source_errors=tuple(SourceError(source, message) for source, message in report.source_errors.items()),
        variables=tuple(drafts),
    )
    validate_result_contract(result.to_dict())
    return result


def _evidence_failure(
    name: str, observations: Sequence[Observation], report: RetrievalReport, unread: int, unverified: int,
) -> Failure | None:
    """Why a variable has nothing to suggest from, when the reason is the run rather than the evidence.

    "Not enough evidence" is a reading of evidence. A variable no request was sent for, or
    whose sources failed, could not be read, or quoted words they do not contain, had none
    read - saying it was insufficient would report a pipeline failure as a finding.
    """
    if not report.asked.get(name):
        unconfigured = ", ".join(report.unconfigured_sources)
        reason = (f"these sources are not configured in this deployment: {unconfigured}" if unconfigured
                  else "none of the configured sources applies to it")
        return Failure("evidence_unavailable", f"No source was searched for this variable; {reason}.")
    if observations:
        return None
    reasons = []
    unreachable = report.failed_for.get(name, ())
    if unreachable:
        reasons.append(f"these sources failed: {', '.join(unreachable)}")
    if unread:
        reasons.append(f"{unread} retrieved sources could not be read")
    if unverified:
        reasons.append(f"{unverified} quotes could not be found in their sources")
    if not reasons:
        return None
    return Failure("evidence_unavailable", f"No evidence could be read for this variable; {'; '.join(reasons)}.")


def _fan_out(stage: str, items: Sequence[_T], run: Callable[[_T], _R], workers: int, progress: ProgressFn) -> list[_R]:
    progress(stage, completed=0, total=len(items))
    return map_ordered(
        list(items), run, workers=workers,
        on_progress=lambda done, total: progress(stage, completed=done, total=total),
    )


def _plan(variables, config, llm_client, indication, intervention_term, intended_use, failures,
          progress) -> dict[str, RetrievalIntent]:
    def plan(variable: AttributeDefinition) -> RetrievalIntent | Failure:
        try:
            return plan_searches(variable, config, llm_client, indication=indication, intervention_term=intervention_term,
                                 intended_use=intended_use)
        except RECORDABLE_FAILURES as exc:  # a model or provider failure costs this variable, never the run
            return _failure("search_planning_failed", exc)

    planned = _fan_out("plan", variables, plan, PLANNING_WORKERS, progress)
    intents: dict[str, RetrievalIntent] = {}
    for variable, outcome in zip(variables, planned, strict=True):
        if isinstance(outcome, Failure):
            failures[variable.name] = outcome
        else:
            intents[variable.name] = outcome
    return intents


def _read(variables, found, llm_client, indication, intervention_term, programme_context, progress):
    pairs = [(variable, finding) for variable in variables for finding in eligible_findings(found.get(variable.name, []))]

    def read(pair: tuple[AttributeDefinition, Finding]) -> Reading | None:
        try:
            return read_finding(pair[0], pair[1], llm_client, indication=indication, intervention_term=intervention_term,
                                programme_context=programme_context)
        except RECORDABLE_FAILURES:  # one unreadable source is set aside and counted
            logger.warning("Evidence reading failed for %s from %s", pair[0].name, pair[1].url, exc_info=True)
            return None

    readings = _fan_out("evidence", pairs, read, READING_WORKERS, progress)
    observations: dict[str, list[Observation]] = {}
    unread: dict[str, int] = {}
    unverified: dict[str, int] = {}
    for (variable, _), reading in zip(pairs, readings, strict=True):
        if reading is None:
            unread[variable.name] = unread.get(variable.name, 0) + 1
            continue
        if reading.unverified_quotes:
            unverified[variable.name] = unverified.get(variable.name, 0) + reading.unverified_quotes
        held = observations.setdefault(variable.name, [])
        for item in reading.observations:
            held.append(Observation(id=f"{variable.name}:o{len(held) + 1}", **vars(item)))
    return observations, unread, unverified


def _suggest(variables, observations, llm_client, indication, intervention_term, programme_context, intended_use,
             failures, progress) -> dict[str, Suggestion]:
    def run(variable: AttributeDefinition) -> Suggestion | Failure:
        held = observations.get(variable.name, [])
        try:
            return suggest(variable, held, summarise(held), llm_client, indication=indication,
                           intervention_term=intervention_term, programme_context=programme_context,
                           intended_use=intended_use)
        except RECORDABLE_FAILURES as exc:  # a model or provider failure costs this variable, never the run
            return _failure("suggestion_failed", exc)

    made = _fan_out("suggest", variables, run, SUGGESTION_WORKERS, progress)
    suggestions: dict[str, Suggestion] = {}
    for variable, outcome in zip(variables, made, strict=True):
        if isinstance(outcome, Failure):
            failures[variable.name] = outcome
        else:
            suggestions[variable.name] = outcome
    return suggestions


def _variable(
    variable: AttributeDefinition,
    observations: Sequence[Observation],
    suggestion: Suggestion | None,
    failure: Failure | None,
    unread: int,
    unverified: int,
) -> VariableDraft:
    base = VariableDraft(
        name=variable.name, label=attribute_label(variable.name), description=variable.description.strip(),
        evidence_domain=variable.evidence_domain, status="complete", failure=None,
        observations=tuple(observations), statistics=tuple(summarise(observations)),
        suggestion=suggestion, unread_findings=unread, unverified_quotes=unverified,
    )
    if failure is not None:
        return replace(base, status="failed", failure=failure, suggestion=None)
    return base


def _failure(code: str, exc: Exception) -> Failure:
    """The stage's code, the call's cause, and the reason in the stage's or provider's words."""
    if isinstance(exc, ModelResponseError):
        message = str(exc)
    else:
        logger.warning("Drafter stage failed", exc_info=exc)
        message = f"The model service failed: {exc}" if str(exc) else f"The model service failed ({type(exc).__name__})."
    return Failure(code, message, failure_code(exc))
