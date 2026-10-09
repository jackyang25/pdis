"""Stateless free-query facade over the source controller."""

from __future__ import annotations

from typing import Sequence

from .controller import plan_requests, run_requests, validate_source_keys
from .models import (
    Finding,
    QueryFacets,
    RetrievalEntity,
    RetrievalIntent,
    SearchReport,
    SearchRuntime,
    SourceQueryIntent,
    merge_findings,
)
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES


#: What a caller states about a search in words - the query and each scope field, by
#: `run_pipeline`'s own parameter names - and what each one means. Sources and entities are
#: the two structured inputs beside these. Every schema that composes a search is named and
#: described from here: the API's request, which MCP publishes, and the Assistant's
#: suggested search. Each is read by an agent filling it in, so two wordings would tell two
#: agents different things about one field. A test pins each name to `run_pipeline`.
SEARCH_TEXT_FIELDS: dict[str, str] = {
    "query": (
        "A short search query in search terms, a dozen words at most, e.g. 'maternal RSV "
        "vaccine efficacy phase 3'. Not a question or an instruction."
    ),
    "condition": (
        "Disease or condition as a search term, e.g. 'respiratory syncytial virus'. Anchors "
        "structured sources such as trial registries."
    ),
    "intervention": "Intervention class in one or two words, e.g. 'vaccine', 'monoclonal antibody', 'drug'.",
    "product": "One named product, e.g. 'Abrysvo'. Narrows the intervention class; it does not replace it.",
    "population": "Who the question is about, in a few words, e.g. 'pregnant women 24-36 weeks'.",
    "outcome": "What is measured, in a few words, e.g. 'efficacy against severe LRTI'.",
    "region": "Countries or WHO regions the question is about, e.g. 'sub-Saharan Africa'.",
    "published_since": (
        "ISO date (YYYY-MM-DD). Keeps records published on or after it; records with no "
        "stated date are kept."
    ),
}
#: What `entities` holds, and what each entity states, for the same callers.
SEARCH_ENTITIES_DESCRIPTION = (
    "Named genes, proteins, compounds or products, each with its type. Sources that require "
    "an entity type plan nothing without one."
)
SEARCH_ENTITY_FIELDS: dict[str, str] = {
    "name": "The subject's name, e.g. a gene, protein, compound or product.",
    "entity_type": "What kind of subject `name` is.",
}


def run_pipeline(
    query: str,
    *,
    runtime: SearchRuntime,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_uses: int = DEFAULT_MAX_USES,
    sources: tuple[str, ...] = ("web",),
    condition: str | None = None,
    intervention: str | None = None,
    entities: Sequence[RetrievalEntity] = (),
    product: str | None = None,
    population: str | None = None,
    outcome: str | None = None,
    region: str = "",
    published_since: str = "",
    raise_source_errors: bool = False,
    progress_callback=None,
) -> SearchReport:
    """Run registered retrieval sources for `query` and report findings and lanes.

    Args:
        query: Free-text question or topic to search for.
        runtime: Injected capabilities available to registered source adapters.
        max_tokens: Token budget for the LLM's response.
        max_uses: Max number of web_search tool invocations the model
            may make per query.
        sources: Registered source adapter keys to union. Defaults to web.
        condition: Optional condition/disease, the anchor every field-addressed
            source builds its request around. Left blank, each such adapter falls
            back to `query` itself, which for a multi-word question is a field
            value the provider's index will not hold. Ignored by plain-text
            grammars, which read `query` directly.
        intervention: The intervention *class* - drug, vaccine, monoclonal
            antibody - carried at intent scope, which is where Scout puts the
            class from its run header. Ignored by sources whose grammar has no
            intervention field.
        product: One named product, narrowing the intervention field of the
            request the class already scopes. A separate parameter because they
            are different values doing different work: the class is the scope a
            source is asked about, and the product is a narrowing added beside
            it, so a source issues both requests rather than choosing. Passing
            the product in place of the class loses the broader request.
        entities: Named subjects a source may address its API by - a gene, a
            protein, a compound. A source declaring `required_entity_types` plans
            nothing without one, because it has no subject to name, so passing
            none silently limits the run to the sources that read prose. Scout
            takes these from a parsed document; a free-text caller states them.
        population: Who the question is about. A stated subject phrase for the
            literature grammars, which otherwise take the whole query as the
            subject. Structured sources have no such field and ignore it.
        outcome: What is being measured. Read before `population` when a
            literature adapter picks the one phrase a query asks about, because
            it names the question more specifically than its subjects do.
        region: Countries or WHO regions the caller is deciding for. Scopes the whole
            run rather than one query, and reaches a provider's own location field
            where it has one. Sources without such a field ignore it.
        published_since: ISO date bound, or "" for none. Passed to the provider by
            sources declaring `honors_date_bound`, which is the only place a bound
            changes what gets ranked rather than only what survives.
        raise_source_errors: Re-raise any adapter failures. Defaults to the
            standalone Searcher's graceful partial-result behavior.
        progress_callback: Optional callable for streaming progress
            (matches the convention used by other services' pipelines).

    Returns:
        SearchReport - the deduplicated findings, and one outcome per native
        request so an empty lane stays distinguishable from a failed one.

    Adapter failures are isolated as outcomes. They raise only when
    `raise_source_errors` is true.
    """
    selected = validate_source_keys(sources)
    intent = RetrievalIntent(
        scope_ref="query",
        topic=query,
        description="",
        indication=condition or "",
        intervention_class=intervention or "",
        entities=tuple(entities),
        region=region,
        published_since=published_since,
        queries=(
            SourceQueryIntent(
                text=query,
                tracks=("general",),
                # Only the two facets a caller states here. `condition` and
                # `intervention` are carried at intent scope above, and stating them
                # again as query facets would add a narrowed request identical to the
                # scope request, spending one of a source's requests on nothing.
                facets=QueryFacets(
                    # Not `condition`: every field-addressed source declares condition
                    # its anchor, and an anchor always takes the intent's value, so a
                    # query-level condition would narrow nothing and be dropped.
                    intervention=product or "",
                    population=population or "",
                    outcome=outcome or "",
                ),
            ),
        ),
    )
    requests = plan_requests([intent], sources=selected)
    outcomes = run_requests(
        requests,
        runtime=runtime,
        max_tokens=max_tokens,
        max_uses=max_uses,
        progress=(
            lambda completed, total: progress_callback(
                "search", completed=completed, total=total
            )
        )
        if progress_callback
        else None,
    )
    failures = [outcome for outcome in outcomes if outcome.status == "failed"]
    if failures and raise_source_errors:
        failed = ", ".join(outcome.request.source for outcome in failures)
        raise RuntimeError(f"Retrieval source failure(s): {failed}")
    findings = [
        finding
        for outcome in outcomes
        if outcome.status == "complete"
        for finding in outcome.findings
    ]

    by_url: dict[str, Finding] = {}
    out: list[Finding] = []
    for finding in findings:
        if finding.url in by_url:
            merge_findings(by_url[finding.url], finding)
            continue
        by_url[finding.url] = finding
        out.append(finding)
    return SearchReport(findings=out, outcomes=list(outcomes))
