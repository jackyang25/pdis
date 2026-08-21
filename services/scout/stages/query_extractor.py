"""Stage 1: derive source-neutral retrieval intents from one document unit.

Each attribute is treated as a self-contained topic. The scout pipeline
calls this stage once per attribute and feeds the resulting focused queries
into searcher.
"""

from __future__ import annotations

import json
import logging

from services.searcher import QueryFacets

from ..ai import request_structured
from ..ai_contracts import query_batch
from ..context import BLOCK_ID_JSON_INSTRUCTION, document_block_ids, validated_block_ids
from ..models import (
    Attribute,
    LLMClientProtocol,
    QuantitativeTarget,
    QueryIntent,
    RetrievalScopeLedger,
    ScoutTypeConfig,
)
from ..prompt_primitives import COMPARATOR_POLICY_PRIMITIVE, SEMANTIC_DIMENSIONS_PRIMITIVE

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 5000

QUERY_FACET_INSTRUCTION = (
    "STATED QUERY PARTS\n"
    "Alongside each query, populate `facets` with the parts of that same query. "
    "Registries and regulatory databases accept fields, not sentences, and they use "
    "these instead of re-reading your text. condition is the disease or health "
    "problem searched; intervention is the product, platform, or approach; population "
    "is who the result must describe; outcome is the property or endpoint being "
    "measured. Use the exact wording a database would index, not a paraphrase of the "
    "whole query. Give ONE concept per facet: a single indexable phrase, never a list, "
    "and never two ideas joined by a comma, a slash, or \"and\". If a query genuinely "
    "covers two outcomes, it is two queries. Leave a facet as an empty string when the "
    "query does not constrain it - an empty facet widens the search to this field's "
    "scope, while a guessed one silently narrows it. Facets never replace the query "
    "text; both are returned together."
)


def extract_queries_for_variable(
    attribute: Attribute,
    quantitative_targets: list[QuantitativeTarget],
    config: ScoutTypeConfig,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    scope: RetrievalScopeLedger,
    queries_per_variable: int,
    document_context: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[QueryIntent]:
    """Generate retrieval intents for one variable across additive tracks.

    Tracks are additive (each adds queries, never replaces another) and unioned
    losslessly: general coverage, optional Global-South emphasis, and optional
    counterfactual (disconfirming) evidence.
    """
    if not attribute.target_resolved or not attribute.document_target:
        return []
    user_message = _user_message_for_variable(attribute, document_context)
    target_blocks = {
        target.id: target.doc_block_ids for target in quantitative_targets
        if attribute.name in target.analysis_attribute_refs
    }
    target_query_contexts = {
        target.id: _target_retrieval_text(target)
        for target in quantitative_targets
        if attribute.name in target.analysis_attribute_refs
    }
    general_budget = max(queries_per_variable, len(target_blocks))

    queries = _run_track(
        build_system_prompt_for_variable(
            config,
            indication=indication,
            attribute=attribute,
            quantitative_targets=quantitative_targets,
            queries_per_variable=general_budget,
        ),
        user_message,
        llm_client,
        max_tokens,
        cap=general_budget,
        attribute_name=attribute.name,
        track="general",
        allowed_block_ids=document_block_ids(document_context),
        allowed_target_ids=set(target_blocks),
        target_blocks=target_blocks,
        target_query_contexts=target_query_contexts,
        required_target_ids=set(target_blocks),
        fallback_context=(indication, config.intervention_term, attribute.name),
    )

    if config.geographic_emphasis and config.geographic_queries_per_variable > 0:
        queries += _run_track(
            build_system_prompt_for_geographic_variable(
                config,
                indication=indication,
                attribute=attribute,
                geographic_queries_per_variable=config.geographic_queries_per_variable,
                region=scope.value("region"),
            ),
            user_message,
            llm_client,
            max_tokens,
            cap=config.geographic_queries_per_variable,
            attribute_name=attribute.name,
            track="geographic",
            allowed_block_ids=document_block_ids(document_context),
            allowed_target_ids=set(target_blocks),
            target_blocks=target_blocks,
            target_query_contexts=target_query_contexts,
        )

    if config.counterfactual_queries_per_variable > 0:
        queries += _run_track(
            build_system_prompt_for_counterfactual_variable(
                config,
                indication=indication,
                attribute=attribute,
                counterfactual_queries_per_variable=config.counterfactual_queries_per_variable,
            ),
            user_message,
            llm_client,
            max_tokens,
            cap=config.counterfactual_queries_per_variable,
            attribute_name=attribute.name,
            track="counterfactual",
            allowed_block_ids=document_block_ids(document_context),
            allowed_target_ids=set(target_blocks),
            target_blocks=target_blocks,
            target_query_contexts=target_query_contexts,
        )

    if config.precedent_queries_per_variable > 0:
        queries += _run_track(
            build_system_prompt_for_precedent_variable(
                config,
                indication=indication,
                attribute=attribute,
                precedent_queries_per_variable=config.precedent_queries_per_variable,
            ),
            user_message,
            llm_client,
            max_tokens,
            cap=config.precedent_queries_per_variable,
            attribute_name=attribute.name,
            track="precedent",
            allowed_block_ids=document_block_ids(document_context),
            allowed_target_ids=set(target_blocks),
            target_blocks=target_blocks,
            target_query_contexts=target_query_contexts,
        )

    total = (
        general_budget
        + config.geographic_queries_per_variable
        + config.counterfactual_queries_per_variable
        + config.precedent_queries_per_variable
    )
    return _dedupe_queries(queries)[:total]


def _run_track(
    system_prompt: str,
    user_message: str,
    llm_client: LLMClientProtocol,
    max_tokens: int,
    *,
    cap: int,
    attribute_name: str,
    track: str,
    allowed_block_ids: set[str],
    allowed_target_ids: set[str],
    target_blocks: dict[str, list[str]],
    target_query_contexts: dict[str, str],
    required_target_ids: set[str] | None = None,
    fallback_context: tuple[str, str, str] | None = None,
) -> list[QueryIntent]:
    """Run one query-generation track (call + parse, retry once on empty)."""
    contract = query_batch(
        sorted(allowed_block_ids),
        sorted(allowed_target_ids),
    )
    raw = request_structured(
        llm_client,
        contract,
        system_prompt,
        user_message,
        max_tokens=max_tokens,
        task="fast",
    )
    queries = _parse_queries(
        raw,
        allowed_block_ids,
        allowed_target_ids=allowed_target_ids,
        target_blocks=target_blocks,
    )
    missing_targets = _missing_target_ids(queries, required_target_ids or set())
    if not queries or missing_targets:
        logger.warning(
            "query_extractor produced incomplete %s query coverage for %r; retrying once",
            track,
            attribute_name,
        )
        raw = request_structured(
            llm_client,
            contract,
            system_prompt,
            user_message,
            max_tokens=max_tokens,
            task="fast",
        )
        queries = _parse_queries(
            raw,
            allowed_block_ids,
            allowed_target_ids=allowed_target_ids,
            target_blocks=target_blocks,
        )
    for query in queries:
        query.tracks = [track]
    queries = queries[:cap]
    if required_target_ids and fallback_context:
        indication, intervention_class, attribute_name = fallback_context
        for target_id in sorted(_missing_target_ids(queries, required_target_ids)):
            queries.append(
                QueryIntent(
                    text=" ".join(
                        (
                            indication,
                            intervention_class,
                            attribute_name.replace("_", " "),
                            target_query_contexts[target_id],
                            "reported numeric results",
                        )
                    ),
                    tracks=[track],
                    doc_block_ids=list(target_blocks[target_id]),
                    target_ids=[target_id],
                )
            )
        while len(queries) > cap:
            removable = next(
                (index for index, query in enumerate(queries) if not query.target_ids),
                None,
            )
            if removable is None:
                break
            queries.pop(removable)
    return queries


def _missing_target_ids(
    queries: list[QueryIntent], required: set[str]
) -> set[str]:
    covered = {target_id for query in queries for target_id in query.target_ids}
    return required - covered


def _target_retrieval_descriptor(target: QuantitativeTarget) -> dict[str, object]:
    """Project a numeric target into threshold-neutral retrieval meaning.

    Retrieval needs the outcome being measured, not the target magnitude that
    determines whether evidence passes. Keeping this projection beside query
    generation prevents adapters and prompts from independently reinterpreting
    the quantitative contract.
    """
    dimensions = _target_retrieval_dimensions(target)
    return {
        "target_id": target.id,
        "unit": target.unit,
        "dimensions": dimensions,
        "comparison_contract": {
            name: {"mode": rule.mode, "scope": rule.scope}
            for name, rule in target.comparison_contract.items()
            if rule.mode != "unconstrained"
        },
    }


def _target_retrieval_dimensions(target: QuantitativeTarget) -> dict[str, str]:
    dimensions: dict[str, str] = {}
    for field_name, rule in target.comparison_contract.items():
        if rule.mode == "unconstrained":
            continue
        slot = target.semantic_profile[field_name]
        phrase = ""
        if rule.scope:
            phrase = rule.scope
        elif slot.state == "specified" and slot.value:
            phrase = slot.value
        elif slot.state == "other" and slot.other:
            phrase = slot.other
        if phrase:
            dimensions[field_name] = phrase
    return dimensions


def _target_retrieval_text(target: QuantitativeTarget) -> str:
    phrases = [
        *_target_retrieval_dimensions(target).values(),
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        normalized = " ".join(str(phrase).split())
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        unique.append(normalized)
    if target.unit:
        unique.append(f"reported in {target.unit}")
    return " ".join(unique)


# --- Which era a track asks about -------------------------------------------
# One rule per stance, named once. It was four inline copies that had already
# drifted apart in wording, and a track's era is a choice worth seeing as a choice:
# a builder picks a constant rather than restating the rule in its own prose.
#
# Neither is a filter. A retrieval index reads "recent" as a word to match, so era
# is expressed through the SUBJECT asked about. A real date bound is a source
# adapter's parameter, recorded in `SearchTrace.request_options`, never a query term.

CURRENT_ERA = (
    "Prefer current developments - recent readouts, the present standard of care, "
    "live registrations - when the field admits them. Express that through the "
    "SUBJECT you ask about, never through words like \"recent\" or \"latest\" and "
    "never a calendar year: a retrieval index reads those as terms to match, not as a "
    "date bound, so they narrow results to documents that happen to contain the word. "
    "Any real date bound belongs to the source adapter, not to this query."
)

HISTORICAL_ERA = (
    "Precedent is HISTORICAL - do NOT restrict to recent years. Prior attempts may be "
    "old; include first-in-class, original-development, and historical framing. Do not "
    "hardcode a specific calendar year in the query text."
)


def build_system_prompt_for_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    quantitative_targets: list[QuantitativeTarget],
    queries_per_variable: int,
) -> str:
    parts = [
        "ROLE\n"
        "Generate source-neutral retrieval intents for one canonical field and its linked "
        "reviewed quantitative targets.",
        "INPUT AUTHORITY\n"
        f"Field: {attribute.name}\n"
        f"Product class: {config.intervention_term}\n"
        f"Indication: {indication}\n"
        f"Field definition: {attribute.description.strip()}",
        "SCOPE\nEvery query must be about the specific field named above and "
        "nothing else. This document has separate variables for efficacy, safety, "
        "dosing, duration, cost, etc. - do NOT pull those topics into this variable's "
        "queries unless THIS variable IS that topic. The domain guidance below tells you "
        "HOW to search (which sources, recency, modalities); it does not widen the SUBJECT "
        "beyond this one variable. Example: for the variable \"Indication\", search the "
        "disease/target-population scope (e.g. which products are indicated for the "
        "disease) - not efficacy percentages or dosing schedules.",
        CURRENT_ERA,
        "Generate a diverse query set across THREE axes: content, source, and language. "
        "Content coverage should include standard of care and new scientific data when "
        "those angles fit this variable. Source coverage should spread across regulators, "
        "registries, literature, procurement/access bodies, and LMIC authorities rather "
        "than repeatedly naming only FDA or EMA. Language coverage should include native "
        "language phrasing for the configured languages, not translated English.",
        config.query_extraction_guidance.strip(),
    ]
    if config.priority_institutions:
        parts.append(
            "When relevant, name authoritative institutions in the intent "
            "(regulators, access bodies, or key companies): "
            + ", ".join(config.priority_institutions)
            + "."
        )
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Generate at least one query in each configured language when "
            "queries_per_variable allows it. Use native-language search phrasing "
            "for non-English languages."
        )
    if config.modalities:
        parts.append(
            "Relevant platform technologies to consider when they bear on "
            "the variable topic: "
            + ", ".join(config.modalities)
            + "."
        )
    linked_targets = [
        target for target in quantitative_targets
        if attribute.name in target.analysis_attribute_refs
    ]
    if linked_targets:
        parts.append(
            "SHARED PRIMITIVES\n"
            + SEMANTIC_DIMENSIONS_PRIMITIVE + "\n\n"
            + COMPARATOR_POLICY_PRIMITIVE + "\n\n"
            "THRESHOLD-NEUTRAL TARGET DESCRIPTORS\n"
            + json.dumps(
                [
                    _target_retrieval_descriptor(target)
                    for target in linked_targets
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\nThe returned set must cover every listed target at least once. "
            "For a target-specific query, copy its ID into target_ids. Do not attach "
            "an ID when the query is only general field coverage. For each target-specific "
            "query, search for reported numeric results matching its measure and endpoint; "
            "apply its direct-comparator contract rather than requiring the document candidate's "
            "exact name. A compatible scope is the retrieval boundary; an exact scope is an "
            "identity requirement. Use result language appropriate to the statistic, such as estimate, "
            "rate, confidence interval, or study result. NEVER include the document's target "
            "value, comparator, threshold/optimal role, or pass/fail wording in a query: valid "
            "comparators on either side of the target must remain retrievable."
        )
    parts.append(QUERY_FACET_INSTRUCTION)
    parts.append(
        "OUTPUT CONTRACT\n"
        f"Return EXACTLY {queries_per_variable} quer"
        f"{'y' if queries_per_variable == 1 else 'ies'} in the structured `queries` array. "
        "No markdown, no commentary. Each query 5-15 words. The set must be diverse "
        "across content angles, authoritative institutions, and configured languages. Each query "
        f"must be specific to the {attribute.name} variable. doc_block_ids must contain "
        "the exact uploaded-document blocks whose claim shaped that query; use [] only "
        "for a general coverage query not tied to one document claim. "
        f"{BLOCK_ID_JSON_INSTRUCTION} Return only the schema-bound response."
    )
    return "\n\n".join(parts)


def _user_message_for_variable(attribute: Attribute, document_context: str) -> str:
    return (
        f"variable: {attribute.name}\n"
        f"What this variable covers: {attribute.description}\n\n"
        "Canonical document binding (authoritative claims to test):\n"
        f"{document_context or '(no relevant document text found)'}\n\n"
        "Generate the queries for this variable now."
    )


def build_system_prompt_for_geographic_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    geographic_queries_per_variable: int,
    region: str = "",
) -> str:
    """The one track that is about place, so the only one the run's region reaches.

    Two halves, and both are needed. The config's institutions and languages are the
    comparator set - a declared statement of which settings this programme is judged
    against, stable across runs. `region` is what the document itself states, read from
    the attribute declaring `supplies_scope` and cited to its blocks.

    Given only the first half, this track asked about China and Indonesia for a
    sub-Saharan Africa programme, because the config list is the same for every run. Given
    only the second, it would lose the comparators, and a programme has to be judged
    against settings other than its own. So the region is additive here exactly as this
    track is additive to the general one.

    The region is not passed to the other tracks on purpose. `general`, `counterfactual`
    and `precedent` are broad by design, and narrowing them to one geography would answer
    a smaller question than the one asked.
    """
    parts = [
        "You generate ADDITIVE Global-South retrieval intents for ONE variable. "
        "These queries are added to the general query set, never substituted for it.",
        f"variable: {attribute.name}.",
        f"Product class: {config.intervention_term}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must remain about THIS variable. Do not pull in other "
        "variables like efficacy, safety, dosing, duration, or cost unless this "
        "variable is that topic.",
        CURRENT_ERA,
        "Global-South emphasis: target national regulators and implementation/access "
        "evidence from LMIC settings. Include regulators such as SAHPRA, NMPA, BPOM, "
        "CDSCO, ANVISA; regional bodies such as Africa CDC and WHO regional offices; "
        "and field evidence about access, equity, procurement, adoption, delivery, "
        "deficiencies, unmet needs, and gaps not addressed by current standard of care.",
        "Use native-language phrasing when using non-English configured languages. "
        "Do not translate English queries word-for-word.",
        "Return the Global-South queries only; the caller appends them after the "
        "general queries.",
    ]
    if region:
        parts.append(
            "THE DOCUMENT'S OWN GEOGRAPHY\n"
            f"This programme states its geography as: {region}. Spend most of this "
            "track's queries there - that is the setting the document will be judged "
            "in. Keep some for the comparator institutions listed below, because a "
            "target has to be read against settings other than its own; a region "
            "returning nothing on its own says little without one that returns "
            "something.\n"
            "Where the configured languages include ones spoken in that geography, "
            "prefer those for the native-language queries. Do not use a configured "
            "language that has no reach there, and do not introduce a language the "
            "configuration does not list."
        )
    if config.geographic_emphasis:
        parts.append("Configured geographic emphasis: " + ", ".join(config.geographic_emphasis) + ".")
    if config.priority_institutions:
        parts.append(
            "Authoritative institutions to spread across: "
            + ", ".join(config.priority_institutions)
            + "."
        )
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Include language diversity across this additive query group when possible."
        )
    parts.append(QUERY_FACET_INSTRUCTION)
    parts.append(
        f"Return EXACTLY {geographic_queries_per_variable} quer"
        f"{'y' if geographic_queries_per_variable == 1 else 'ies'} in the structured `queries` array. "
        "Return only the schema-bound response. "
        f"{BLOCK_ID_JSON_INSTRUCTION} "
        "Each query 5-15 words."
    )
    return "\n\n".join(parts)


def build_system_prompt_for_counterfactual_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    counterfactual_queries_per_variable: int,
) -> str:
    parts = [
        "You generate ADDITIVE COUNTERFACTUAL retrieval intents for ONE variable. "
        "These actively seek evidence that DISPUTES, WEAKENS, or CONTRADICTS the "
        "document's target for this variable. They are added to the general query set, "
        "never substituted for it.",
        f"variable: {attribute.name}.",
        f"Product class: {config.intervention_term}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must remain about THIS variable. Do not pull in other "
        "variables like efficacy, safety, dosing, duration, or cost unless this variable "
        "is that topic.",
        CURRENT_ERA,
        "Counterfactual emphasis: search for DISCONFIRMING evidence - null or failed "
        "results, efficacy waning or shortfalls, safety signals or adverse events, "
        "feasibility / cost / cold-chain problems, limited generalizability across "
        "regions or populations, regulatory setbacks, or evidence that the target is "
        "unmet or unachievable. Seek the strongest genuine counter-evidence, not "
        "strawmen.",
        "Return the counterfactual queries only; the caller appends them after the "
        "other tracks.",
    ]
    if config.priority_institutions:
        parts.append(
            "Authoritative institutions to spread across: "
            + ", ".join(config.priority_institutions)
            + "."
        )
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Use native-language phrasing where it helps surface non-English evidence."
        )
    parts.append(QUERY_FACET_INSTRUCTION)
    parts.append(
        f"Return EXACTLY {counterfactual_queries_per_variable} quer"
        f"{'y' if counterfactual_queries_per_variable == 1 else 'ies'} in the structured `queries` array. "
        "Return only the schema-bound response. "
        f"{BLOCK_ID_JSON_INSTRUCTION} "
        "Each query 5-15 words."
    )
    return "\n\n".join(parts)


def build_system_prompt_for_precedent_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    precedent_queries_per_variable: int,
) -> str:
    parts = [
        "You generate ADDITIVE PRECEDENT retrieval intents for ONE variable. "
        "These seek evidence of whether this variable's target/approach has been "
        "ATTEMPTED BEFORE - so a downstream classifier can tell a genuinely novel "
        "target apart from one that has prior precedent. They are added to the general "
        "query set, never substituted for it.",
        f"variable: {attribute.name}.",
        f"Product class: {config.intervention_term}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must remain about THIS variable. Do not pull in other "
        "variables like efficacy, safety, dosing, duration, or cost unless this variable "
        "is that topic.",
        "Precedent emphasis: search for PRIOR or EXISTING attempts at this target/approach - "
        "earlier or current products pursuing the same target for this indication, past "
        "programs or trials that pursued it (whether they succeeded, stalled, or were "
        "abandoned), and the same platform/mechanism proven in ADJACENT indications as "
        "analogous precedent. The goal is to establish whether the approach is new or has "
        "a track record.",
        HISTORICAL_ERA,
        "Do NOT seek disconfirming/failure evidence here (a separate track covers that); "
        "seek the EXISTENCE of prior or analogous work, positive or negative.",
        "Return the precedent queries only; the caller appends them after the other tracks.",
    ]
    if config.priority_institutions:
        parts.append(
            "Authoritative institutions to spread across: "
            + ", ".join(config.priority_institutions)
            + "."
        )
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Use native-language phrasing where it helps surface non-English evidence."
        )
    parts.append(QUERY_FACET_INSTRUCTION)
    parts.append(
        f"Return EXACTLY {precedent_queries_per_variable} quer"
        f"{'y' if precedent_queries_per_variable == 1 else 'ies'} in the structured `queries` array. "
        "Return only the schema-bound response. "
        f"{BLOCK_ID_JSON_INSTRUCTION} "
        "Each query 5-15 words."
    )
    return "\n\n".join(parts)


def _dedupe_queries(queries: list[QueryIntent]) -> list[QueryIntent]:
    by_text: dict[str, QueryIntent] = {}
    out: list[QueryIntent] = []
    for query in queries:
        normalized = " ".join(query.text.split()).strip()
        if not normalized:
            continue
        key = normalized.lower()
        existing = by_text.get(key)
        if existing is not None:
            existing.tracks = list(dict.fromkeys([*existing.tracks, *query.tracks]))
            existing.doc_block_ids = list(
                dict.fromkeys([*existing.doc_block_ids, *query.doc_block_ids])
            )
            existing.target_ids = list(
                dict.fromkeys([*existing.target_ids, *query.target_ids])
            )
            continue
        intent = QueryIntent(
            text=normalized,
            tracks=list(dict.fromkeys(query.tracks)),
            doc_block_ids=list(dict.fromkeys(query.doc_block_ids)),
            target_ids=list(dict.fromkeys(query.target_ids)),
            facets=query.facets,
        )
        by_text[key] = intent
        out.append(intent)
    return out


def _parse_queries(
    raw: object,
    allowed_block_ids: set[str],
    *,
    allowed_target_ids: set[str] | None = None,
    target_blocks: dict[str, list[str]] | None = None,
) -> list[QueryIntent]:
    parsed = raw
    if not isinstance(parsed, list):
        return []
    out: list[QueryIntent] = []
    for item in parsed:
        if isinstance(item, str):
            query = item.strip()
            facets = QueryFacets()
            block_ids: list[str] = []
            target_ids: list[str] = []
        elif isinstance(item, dict):
            query = str(item.get("query", "")).strip()
            facets = _parsed_facets(item.get("facets"))
            block_ids = validated_block_ids(item.get("doc_block_ids"), allowed_block_ids)
            target_ids = [
                target_id
                for target_id in item.get("target_ids", [])
                if isinstance(target_id, str)
                and target_id in (allowed_target_ids or set())
            ] if isinstance(item.get("target_ids", []), list) else []
            block_ids = list(
                dict.fromkeys(
                    [
                        *block_ids,
                        *(
                            block_id
                            for target_id in target_ids
                            for block_id in (target_blocks or {}).get(target_id, [])
                            if block_id in allowed_block_ids
                        ),
                    ]
                )
            )
        else:
            continue
        if query:
            out.append(
                QueryIntent(
                    text=query,
                    doc_block_ids=block_ids,
                    target_ids=list(dict.fromkeys(target_ids)),
                    facets=facets,
                )
            )
    return out


def _parsed_facets(raw: object) -> QueryFacets:
    """Read the stated query parts, treating an absent slot as unstated."""
    if not isinstance(raw, dict):
        return QueryFacets()
    return QueryFacets(
        condition=str(raw.get("condition", "")),
        intervention=str(raw.get("intervention", "")),
        population=str(raw.get("population", "")),
        outcome=str(raw.get("outcome", "")),
    )
