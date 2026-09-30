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
    """A named subject a structured source can address directly."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"\S", description="The subject's name, e.g. a gene, protein or compound.")
    entity_type: EntityType = Field(description="What kind of subject `name` is.")

    @field_validator("name")
    @classmethod
    def strip_nonempty_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("entity name cannot be empty")
        return stripped


# Every field is described because the schema is what an agent reads: MCP tool discovery
# publishes these descriptions and nothing else. They restate `run_pipeline`'s contract.
class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1, pattern=r"\S",
        description="The evidence question in plain words, e.g. 'maternal RSV vaccine efficacy against severe infant LRTI'.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Source keys from searcher_sources. Empty searches the server's default sources.",
    )
    condition: str = Field("", description="Disease or condition, e.g. 'respiratory syncytial virus'. Anchors structured sources such as trial registries.")
    intervention: str = Field("", description="Intervention class, e.g. 'vaccine', 'monoclonal antibody', 'drug'.")
    entities: list[SearchEntityInput] = Field(
        default_factory=list,
        description="Named genes, proteins or compounds. Sources that require an entity type plan nothing without one.",
    )
    product: str = Field("", description="One named product, e.g. 'Abrysvo'. Narrows the intervention class; it does not replace it.")
    population: str = Field("", description="Who the question is about, e.g. 'pregnant women 24-36 weeks'.")
    outcome: str = Field("", description="What is measured, e.g. 'efficacy against severe LRTI'.")
    region: str = Field("", description="Countries or WHO regions the question is about, e.g. 'sub-Saharan Africa'.")
    published_since: str = Field(
        "", description="ISO date (YYYY-MM-DD). Keeps records published on or after it; records with no stated date are kept.",
    )
    max_findings: int | None = Field(
        None, ge=1, le=500,
        description="Upper bound on returned findings, taken from each source in turn so no source is crowded out. `omitted_findings` reports what was left out. Empty returns everything.",
    )


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
    findings = [FindingOut(**item) for item in findings_to_dicts(report.findings)]
    kept = _balanced(findings, request.max_findings)
    return SearcherRunResponse(
        query=request.query,
        findings=kept,
        lanes=[SearchLaneOut(**item) for item in outcomes_to_dicts(report.outcomes)],
        omitted_findings=len(findings) - len(kept),
    )


def _balanced(findings: list[FindingOut], limit: int | None) -> list[FindingOut]:
    """At most `limit` findings, taken from each source in turn, in their original order.

    Findings arrive grouped by source, so keeping the first `limit` would drop whole sources
    that happened to run later. Rotating through sources keeps each one represented; within
    a source the original order is kept, and the result preserves arrival order. This only
    selects among findings already returned; it judges none of them.
    """
    if limit is None or len(findings) <= limit:
        return findings
    by_source: dict[str, list[int]] = {}
    for position, finding in enumerate(findings):
        by_source.setdefault(finding.source, []).append(position)
    queues = list(by_source.values())
    chosen: list[int] = []
    while len(chosen) < limit:
        for queue in queues:
            if queue and len(chosen) < limit:
                chosen.append(queue.pop(0))
    return [findings[position] for position in sorted(chosen)]


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
