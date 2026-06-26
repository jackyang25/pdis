"""Stage 1: derive web search queries from one TPP attribute variable.

Each attribute is treated as a self-contained topic. The scout pipeline
calls this stage once per attribute and feeds the resulting focused queries
into searcher.
"""

from __future__ import annotations

import json
import logging
import re

from ..models import Attribute, LLMClientProtocol, ScoutTypeConfig

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 5000


def extract_queries_for_variable(
    attribute: Attribute,
    config: ScoutTypeConfig,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    queries_per_variable: int,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Generate web search queries for one TPP variable across additive tracks.

    Tracks are additive (each adds queries, never replaces another) and unioned
    losslessly: general coverage, optional Global-South emphasis, and optional
    counterfactual (disconfirming) evidence.
    """
    user_message = _user_message_for_variable(attribute)

    queries = _run_track(
        _system_prompt_for_variable(
            config,
            indication=indication,
            attribute=attribute,
            queries_per_variable=queries_per_variable,
        ),
        user_message,
        llm_client,
        max_tokens,
        cap=queries_per_variable,
        attribute_name=attribute.name,
        track="general",
    )

    if config.geographic_emphasis and config.geographic_queries_per_variable > 0:
        queries += _run_track(
            _system_prompt_for_geographic_variable(
                config,
                indication=indication,
                attribute=attribute,
                geographic_queries_per_variable=config.geographic_queries_per_variable,
            ),
            user_message,
            llm_client,
            max_tokens,
            cap=config.geographic_queries_per_variable,
            attribute_name=attribute.name,
            track="geographic",
        )

    if config.counterfactual_queries_per_variable > 0:
        queries += _run_track(
            _system_prompt_for_counterfactual_variable(
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
        )

    if config.precedent_queries_per_variable > 0:
        queries += _run_track(
            _system_prompt_for_precedent_variable(
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
        )

    total = (
        queries_per_variable
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
) -> list[str]:
    """Run one query-generation track (call + parse, retry once on empty)."""
    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    queries = _parse_queries(raw)
    if not queries:
        logger.warning(
            "query_extractor produced no parsable %s queries for %r; retrying once",
            track,
            attribute_name,
        )
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        queries = _parse_queries(raw)
    return queries[:cap]


def _system_prompt_for_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    queries_per_variable: int,
) -> str:
    parts = [
        "You generate web search queries to surface up-to-date information "
        f"relevant to ONE TPP variable: {attribute.name}.",
        f"Product class: {config.intervention_class}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must be about the specific TPP variable named above and "
        "nothing else. This document has separate variables for efficacy, safety, "
        "dosing, duration, cost, etc. - do NOT pull those topics into this variable's "
        "queries unless THIS variable IS that topic. The domain guidance below tells you "
        "HOW to search (which sources, recency, modalities); it does not widen the SUBJECT "
        "beyond this one variable. Example: for the variable \"Indication\", search the "
        "disease/target-population scope (e.g. which products are indicated for the "
        "disease) - not efficacy percentages or dosing schedules.",
        "Favor recent developments (roughly the last 1-2 years). Do NOT hardcode a "
        "specific calendar year in the query text - the live web search stays current "
        "on its own. Use relative terms like \"recent\" or \"latest\", or omit the year "
        "entirely.",
        "Generate a diverse query set across THREE axes: content, source, and language. "
        "Content coverage should include standard of care and new scientific data when "
        "those angles fit this variable. Source coverage should spread across regulators, "
        "registries, literature, procurement/access bodies, and LMIC authorities rather "
        "than repeatedly naming only FDA or EMA. Language coverage should include native "
        "language phrasing for the configured languages, not translated English.",
        config.query_extraction_guidance.strip(),
    ]
    if config.priority_sources:
        parts.append(
            "When relevant, try to name priority sources in the query text "
            "(regulatory agencies, registries, literature, key companies): "
            + ", ".join(config.priority_sources)
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
    parts.append(
        f"Return EXACTLY {queries_per_variable} quer"
        f"{'y' if queries_per_variable == 1 else 'ies'} as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words. The set must be diverse "
        "across content angles, priority sources, and configured languages. Each query "
        f"must be specific to the {attribute.name} variable. Example:\n"
        '["latest WHO RSV vaccine efficacy evidence"]'
    )
    return "\n\n".join(parts)


def _user_message_for_variable(attribute: Attribute) -> str:
    return (
        f"TPP variable: {attribute.name}\n"
        f"What this variable covers: {attribute.description}\n\n"
        "Generate the queries for this variable now."
    )


def _system_prompt_for_geographic_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    geographic_queries_per_variable: int,
) -> str:
    parts = [
        "You generate ADDITIVE Global-South web search queries for ONE TPP variable. "
        "These queries are added to the general query set, never substituted for it.",
        f"TPP variable: {attribute.name}.",
        f"Product class: {config.intervention_class}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must remain about THIS variable. Do not pull in other "
        "variables like efficacy, safety, dosing, duration, or cost unless this "
        "variable is that topic.",
        "Favor recent developments (roughly the last 1-2 years). Do NOT hardcode a "
        "specific calendar year in the query text. Use relative terms like "
        "\"recent\" or \"latest\", or omit the year entirely.",
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
    if config.geographic_emphasis:
        parts.append("Configured geographic emphasis: " + ", ".join(config.geographic_emphasis) + ".")
    if config.priority_sources:
        parts.append("Priority sources to spread across: " + ", ".join(config.priority_sources) + ".")
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Include language diversity across this additive query group when possible."
        )
    parts.append(
        f"Return EXACTLY {geographic_queries_per_variable} quer"
        f"{'y' if geographic_queries_per_variable == 1 else 'ies'} as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words."
    )
    return "\n\n".join(parts)


def _system_prompt_for_counterfactual_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    counterfactual_queries_per_variable: int,
) -> str:
    parts = [
        "You generate ADDITIVE COUNTERFACTUAL web search queries for ONE TPP variable. "
        "These actively seek evidence that DISPUTES, WEAKENS, or CONTRADICTS the "
        "document's target for this variable. They are added to the general query set, "
        "never substituted for it.",
        f"TPP variable: {attribute.name}.",
        f"Product class: {config.intervention_class}. Indication: {indication}.",
        f"What this variable covers: {attribute.description.strip()}",
        "SCOPE: Every query must remain about THIS variable. Do not pull in other "
        "variables like efficacy, safety, dosing, duration, or cost unless this variable "
        "is that topic.",
        "Favor recent developments (roughly the last 1-2 years). Do NOT hardcode a "
        "specific calendar year. Use relative terms like \"recent\" or \"latest\", or "
        "omit the year entirely.",
        "Counterfactual emphasis: search for DISCONFIRMING evidence - null or failed "
        "results, efficacy waning or shortfalls, safety signals or adverse events, "
        "feasibility / cost / cold-chain problems, limited generalizability across "
        "regions or populations, regulatory setbacks, or evidence that the target is "
        "unmet or unachievable. Seek the strongest genuine counter-evidence, not "
        "strawmen.",
        "Return the counterfactual queries only; the caller appends them after the "
        "other tracks.",
    ]
    if config.priority_sources:
        parts.append("Priority sources to spread across: " + ", ".join(config.priority_sources) + ".")
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Use native-language phrasing where it helps surface non-English evidence."
        )
    parts.append(
        f"Return EXACTLY {counterfactual_queries_per_variable} quer"
        f"{'y' if counterfactual_queries_per_variable == 1 else 'ies'} as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words."
    )
    return "\n\n".join(parts)


def _system_prompt_for_precedent_variable(
    config: ScoutTypeConfig,
    *,
    indication: str,
    attribute: Attribute,
    precedent_queries_per_variable: int,
) -> str:
    parts = [
        "You generate ADDITIVE PRECEDENT web search queries for ONE TPP variable. "
        "These seek evidence of whether this variable's target/approach has been "
        "ATTEMPTED BEFORE - so a downstream classifier can tell a genuinely novel "
        "target apart from one that has prior precedent. They are added to the general "
        "query set, never substituted for it.",
        f"TPP variable: {attribute.name}.",
        f"Product class: {config.intervention_class}. Indication: {indication}.",
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
        "Recency: precedent is HISTORICAL - do NOT restrict to recent years. Prior "
        "attempts may be old; include first-in-class, original-development, and historical "
        "framing. Do not hardcode a specific calendar year in the query text.",
        "Do NOT seek disconfirming/failure evidence here (a separate track covers that); "
        "seek the EXISTENCE of prior or analogous work, positive or negative.",
        "Return the precedent queries only; the caller appends them after the other tracks.",
    ]
    if config.priority_sources:
        parts.append("Priority sources to spread across: " + ", ".join(config.priority_sources) + ".")
    if config.languages:
        parts.append(
            "Configured languages: "
            + ", ".join(config.languages)
            + ". Use native-language phrasing where it helps surface non-English evidence."
        )
    parts.append(
        f"Return EXACTLY {precedent_queries_per_variable} quer"
        f"{'y' if precedent_queries_per_variable == 1 else 'ies'} as a JSON array of strings. "
        "No markdown, no commentary. Each query 5-15 words."
    )
    return "\n\n".join(parts)


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        normalized = " ".join(query.split()).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _parse_queries(raw: str) -> list[str]:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_array(text))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(q).strip() for q in parsed if str(q).strip()]


def _strip_fences(s: str) -> str:
    m = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", s, re.DOTALL)
    return m.group(1) if m else s


def _extract_json_array(s: str) -> str:
    decoder = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "[":
            continue
        try:
            parsed, end = decoder.raw_decode(s[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return s[i : i + end]
    return s
