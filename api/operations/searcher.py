"""Transport-neutral Searcher input validation, preparation and execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.deps import (
    ConfigurationError,
    MissingCredentialError,
    get_search_integrations,
    get_search_runtime,
)
from api.operations.errors import OperationError
from api.schemas import (
    FindingOut,
    SearchLaneOut,
    SearcherRunResponse,
    SearchSourceOut,
    SourceAttributionOut,
)
from services.searcher import (
    ENTITY_TYPES,
    RetrievalEntity,
    SearchRuntime,
    findings_to_dicts,
    outcomes_to_dicts,
    run_pipeline,
    source_specs,
    unconfigured_source_keys,
    validate_source_keys,
)


EntityType = Enum(
    "EntityType",
    {value.upper(): value for value in sorted(ENTITY_TYPES)},
    type=str,
)


class SearchEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"\S")
    entity_type: EntityType

    @field_validator("name")
    @classmethod
    def strip_nonempty_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("entity name cannot be empty")
        return stripped


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, pattern=r"\S")
    sources: list[str] = Field(default_factory=list)
    condition: str = ""
    intervention: str = ""
    entities: list[SearchEntityInput] = Field(default_factory=list)
    product: str = ""
    population: str = ""
    outcome: str = ""
    region: str = ""
    published_since: str = ""


@dataclass(frozen=True)
class PreparedSearch:
    request: SearchInput
    selected: tuple[str, ...]
    runtime: SearchRuntime


def _configuration_error(exc: Exception) -> OperationError:
    return OperationError("missing_configuration", str(exc))


def prepare_search(request: SearchInput) -> PreparedSearch:
    """Validate source selection and construct the server-owned runtime once."""
    requested = tuple(source.strip() for source in request.sources if source.strip())
    try:
        selected = (
            validate_source_keys(requested)
            if requested
            else tuple(
                source.key for source in source_specs() if source.default_enabled
            )
        )
    except ValueError as exc:
        raise OperationError("invalid_sources", str(exc)) from exc
    try:
        runtime = get_search_runtime()
    except (MissingCredentialError, ConfigurationError) as exc:
        raise _configuration_error(exc) from exc
    missing = unconfigured_source_keys(selected, runtime)
    if missing:
        raise OperationError(
            "unconfigured_sources",
            f"Unconfigured retrieval source(s): {', '.join(missing)}",
        )
    return PreparedSearch(request=request, selected=selected, runtime=runtime)


def execute_search(
    prepared: PreparedSearch,
    progress_callback: Callable[..., None] | None = None,
) -> SearcherRunResponse:
    """Execute a prepared search and map its service report to the public result."""
    request = prepared.request
    report = run_pipeline(
        request.query,
        runtime=prepared.runtime,
        sources=prepared.selected,
        condition=request.condition.strip() or None,
        intervention=request.intervention.strip() or None,
        entities=tuple(
            RetrievalEntity(name=entity.name, entity_type=entity.entity_type.value)
            for entity in request.entities
        ),
        product=request.product.strip() or None,
        region=request.region.strip(),
        published_since=request.published_since.strip(),
        population=request.population.strip() or None,
        outcome=request.outcome.strip() or None,
        progress_callback=progress_callback,
    )
    return SearcherRunResponse(
        query=request.query,
        findings=[FindingOut(**item) for item in findings_to_dicts(report.findings)],
        lanes=[SearchLaneOut(**item) for item in outcomes_to_dicts(report.outcomes)],
    )


def list_sources() -> list[SearchSourceOut]:
    """Return registered source metadata with server configuration state."""
    try:
        integrations = get_search_integrations()
    except ConfigurationError as exc:
        raise _configuration_error(exc) from exc
    return [
        SearchSourceOut(
            key=source.key,
            label=source.label,
            default_enabled=source.default_enabled,
            configured=(
                not source.integration_key or source.integration_key in integrations
            ),
            evidence_domains=list(source.evidence_domains),
            required_entity_types=list(source.required_entity_types),
            reads=list(source.reads),
            evidence_class=source.evidence_class,
            jurisdiction=source.jurisdiction,
            honors_date_bound=source.honors_date_bound,
            attribution=(
                SourceAttributionOut(
                    label=source.attribution.label,
                    url=source.attribution.url,
                    prefix=source.attribution.prefix,
                )
                if source.attribution
                else None
            ),
        )
        for source in source_specs()
    ]
