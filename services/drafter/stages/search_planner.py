"""Each variable's searches: what comparable products achieved, and what guidance asks.

One request per variable: a variable's queries are a set (they divide its ground between
them), but two variables' queries are not, so each variable is planned alone.
"""

from __future__ import annotations

from shared.ai import Effort, ModelTask, request_validated
from shared.schemas import non_empty_text
from shared.vocabulary import AttributeDefinition, searchable_attribute_phrase

from services.searcher import QueryFacets, RetrievalIntent, SourceQueryIntent

from ..models import DrafterConfig, LLMClientProtocol

VARIABLES_PER_REQUEST = 1
QUERIES_PER_VARIABLE = 4
#: The fast tier: writing queries is Scout's query extraction under another name, which
#: runs on the fast tier; what the queries find is judged later, by the suggestion.
TASK: ModelTask = "fast"
#: Low: four short queries and their facets.
EFFORT: Effort = "low"
#: A few hundred tokens of answer; the rest is reasoning room.
MAX_TOKENS = 4000
#: Lineage labels a query carries through retrieval; they name why it was asked.
PURPOSES = ("comparable", "guidance")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["queries"],
    "properties": {
        "queries": {
            "type": "array",
            # At least one: a plan with no query searches nothing, and the parser refuses it.
            "minItems": 1,
            "maxItems": QUERIES_PER_VARIABLE,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query", "purpose", "facets"],
                "properties": {
                    "query": non_empty_text(),
                    "purpose": {"type": "string", "enum": list(PURPOSES)},
                    "facets": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["condition", "intervention", "population", "outcome"],
                        "properties": {
                            name: {"type": "string"} for name in ("condition", "intervention", "population", "outcome")
                        },
                    },
                },
            },
        },
    },
}


def build_system_prompt(query_guidance: str) -> str:
    return (
        "You plan literature, registry and guidance searches for ONE variable of an intervention "
        "target product profile (iTPP) that a team is drafting.\n\n"
        f"Write up to {QUERIES_PER_VARIABLE} short search queries. Each has a purpose:\n"
        "- comparable: finds what existing or late-stage products for this disease achieved or "
        "specify for this variable.\n"
        "- guidance: finds what a published target profile, guideline or programme requirement asks "
        "of a new product for this variable.\n"
        "Write at least one of each where the variable could plausibly have both.\n\n"
        "For each query also state its facets: condition, intervention, population and outcome, "
        "each blank when the query does not state it. Do not restate the condition in other words.\n\n"
        f"Domain guidance:\n{query_guidance.strip()}"
    )


def plan_searches(
    variable: AttributeDefinition,
    config: DrafterConfig,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_term: str,
) -> RetrievalIntent:
    message = (
        f"Product type: {intervention_term}. Disease / condition: {indication}.\n"
        f"Variable: {variable.name} ({searchable_attribute_phrase(variable.name)})\n"
        f"What it covers: {variable.description.strip()}"
    )

    def parse(payload: dict | None) -> RetrievalIntent:
        queries = _queries(payload)
        if not queries:
            raise ValueError("no usable query was returned")
        return RetrievalIntent(
            scope_ref=variable.name,
            topic=searchable_attribute_phrase(variable.name),
            description=variable.description.strip(),
            indication=indication,
            intervention_class=intervention_term,
            evidence_domain=variable.evidence_domain,
            queries=tuple(queries),
        )

    return request_validated(
        llm_client, build_system_prompt(config.query_guidance), message,
        schema_name="drafter_search_plan", schema=SCHEMA, max_tokens=MAX_TOKENS,
        task=TASK, effort=EFFORT,
        parse=parse, failure=f"Search planning failed for {variable.name}",
        repair=lambda error: f"\n\nYour prior answer was not a usable plan: {error}. Answer again.",
    )


def _queries(payload: object) -> list[SourceQueryIntent]:
    """Every query the plan wrote, in its order.

    Not deduplicated: two queries are the same request only if a source's grammar makes
    them one, and Searcher already collapses identical native requests while keeping
    each query's lineage. Comparing their text here would be string identity deciding
    what the model meant.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("queries"), list):
        return []
    queries: list[SourceQueryIntent] = []
    for item in payload["queries"]:
        text = " ".join(str(item.get("query") or "").split())
        if not text:
            raise ValueError("a query is blank")
        facets = item.get("facets") or {}
        queries.append(SourceQueryIntent(
            text=text,
            tracks=(item["purpose"],),
            facets=QueryFacets(**{name: str(facets.get(name) or "") for name in ("condition", "intervention", "population", "outcome")}),
        ))
    return queries
