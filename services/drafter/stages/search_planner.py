"""Each variable's searches: what comparable products achieved, and what guidance asks.

One request per variable: a variable's queries are a set (they divide its ground between
them), but two variables' queries are not, so each variable is planned alone.
"""

from __future__ import annotations

from shared.ai import request_structured
from shared.errors import ModelResponseError
from shared.vocabulary import AttributeDefinition, searchable_attribute_phrase

from services.searcher import QueryFacets, RetrievalIntent, SourceQueryIntent

from ..models import DrafterConfig, LLMClientProtocol

VARIABLES_PER_REQUEST = 1
QUERIES_PER_VARIABLE = 4
MAX_TOKENS = 8000  # reasoning counts against it; a reply cut off is a failure
#: Lineage labels a query carries through retrieval; they name why it was asked.
PURPOSES = ("comparable", "guidance")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["queries"],
    "properties": {
        "queries": {
            "type": "array",
            "maxItems": QUERIES_PER_VARIABLE,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query", "purpose", "facets"],
                "properties": {
                    "query": {"type": "string", "minLength": 1},
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
    for attempt in range(2):
        repair = "\n\nYour prior answer held no usable query. Answer again." if attempt else ""
        payload = request_structured(
            llm_client, build_system_prompt(config.query_guidance), message + repair,
            schema_name="drafter_search_plan", schema=SCHEMA, max_tokens=MAX_TOKENS,
        )
        queries = _queries(payload)
        if queries:
            return RetrievalIntent(
                scope_ref=variable.name,
                topic=searchable_attribute_phrase(variable.name),
                description=variable.description.strip(),
                indication=indication,
                intervention_class=intervention_term,
                evidence_domain=variable.evidence_domain,
                queries=tuple(queries),
            )
    raise ModelResponseError(f"Search planning returned no usable query for {variable.name}.")


def _queries(payload: object) -> list[SourceQueryIntent]:
    if not isinstance(payload, dict) or not isinstance(payload.get("queries"), list):
        return []
    seen: set[str] = set()
    queries: list[SourceQueryIntent] = []
    for item in payload["queries"]:
        if not isinstance(item, dict) or item.get("purpose") not in PURPOSES:
            continue
        text = " ".join(str(item.get("query") or "").split())
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        facets = item.get("facets") if isinstance(item.get("facets"), dict) else {}
        queries.append(SourceQueryIntent(
            text=text,
            tracks=(item["purpose"],),
            facets=QueryFacets(**{name: str(facets.get(name) or "") for name in ("condition", "intervention", "population", "outcome")}),
        ))
    return queries[:QUERIES_PER_VARIABLE]
