"""Stage 2: extract atomic Insights from web Findings.

Given a flat list of Findings (collected across all queries), the LLM
extracts atomic factual statements, each tied to one or more supporting
Findings by URL. We then re-attach the full Finding objects.
"""

from __future__ import annotations

import json
import logging
import re

from services.searcher import Finding

from ..models import Insight, LLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 24000


def extract_insights(
    findings: list[Finding],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    attribute_ref: str | None = None,
    attribute_description: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Insight]:
    """Return Insights extracted from the supplied Findings."""
    if not findings:
        return []

    system_prompt = _system_prompt(
        indication=indication,
        intervention_class=intervention_class,
        attribute_ref=attribute_ref,
        attribute_description=attribute_description,
    )
    user_message = _user_message(findings)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    parsed = _parse_insights(raw)
    if not parsed and raw.strip():
        # A non-empty but unparseable reply is a transient formatting glitch -
        # worth one retry. An EMPTY reply means the model found nothing to
        # extract or the prompt was refused by content policy; that won't
        # change on retry, so skip it quietly instead of spamming + re-calling.
        raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
        parsed = _parse_insights(raw)

    findings_by_url = {f.url: f for f in findings}
    insights: list[Insight] = []
    for item in parsed:
        statement = item.get("statement", "").strip()
        urls = item.get("supporting_finding_urls", []) or []
        supporting = [findings_by_url[u] for u in urls if u in findings_by_url]
        if not statement or not supporting:
            continue
        # Use the query of the first supporting finding (best available attribution)
        query = supporting[0].query
        insights.append(
            Insight(
                statement=statement,
                supporting_findings=supporting,
                query=query,
                attribute_ref=attribute_ref,
            )
        )
    return insights


def _system_prompt(
    *,
    indication: str,
    intervention_class: str,
    attribute_ref: str | None,
    attribute_description: str,
) -> str:
    return (
        f"You extract atomic factual insights from web search findings about "
        f"a {intervention_class} for {indication}.\n\n"
        "You are extracting insights for ONE specific variable:\n"
        f"Variable: {attribute_ref or 'unknown'}\n"
        f"Definition: {attribute_description or 'No definition provided.'}\n\n"
        "Relevance rule:\n"
        "- Extract ONLY facts that are genuinely about THIS variable's topic, as defined above.\n"
        "- If a finding is about a DIFFERENT topic, SKIP it - do not extract it. "
        "Examples of skips: an identity fact like \"X is a malaria vaccine\" when "
        "the variable is about price; a general dosing-schedule recommendation when "
        "the variable is about a companion diagnostic.\n"
        "- Returning an EMPTY list is correct and expected when the findings contain "
        "nothing about this variable's topic. Do NOT stretch loosely-related facts to "
        "fill the field.\n"
        "- Keep facts that are clearly on-topic OR closely related to the variable's "
        "definition. When genuinely unsure whether a fact fits, prefer keeping it over "
        "dropping it (favor recall slightly, to avoid emptying fields that have real content).\n\n"
        "Rules:\n"
        "- Each Insight is ONE atomic factual statement (one fact, not a paragraph).\n"
        "- Every Insight must cite at least one supporting Finding by its URL.\n"
        "- MERGE duplicates: if several findings state the SAME fact - e.g. the same "
        "announcement in different languages, a press release and its mirror/republish, "
        "or a PubMed record and its PMC full-text - produce ONE insight that cites ALL "
        "those URLs, not one insight per copy. Only emit separate insights for genuinely "
        "distinct facts/sources.\n"
        "- Write every Insight statement in English, even when the supporting Finding "
        "is in another language. Preserve the original source via its URL/title.\n"
        "- Prefer recent, source-attributable facts (regulatory actions, trial readouts, "
        "approvals, safety signals). Skip opinion and marketing language.\n"
        "- Extract only SUBSTANTIVE facts: approvals, recommendations, trial readouts, "
        "efficacy/safety findings, regulatory actions, new products, epidemiology shifts. "
        "Do NOT extract meta-statements that merely note a resource exists - e.g. "
        "\"X published a Q&A page\", \"a webpage describes Y\", \"a fact sheet is available\". "
        "Those are not insights. Extract the underlying fact only if the source states one.\n"
        "- Do not invent facts not present in the findings.\n\n"
        "Return ONLY JSON. No markdown, no preamble. Format:\n"
        "[\n"
        '  {"statement": "...", "supporting_finding_urls": ["https://...", "https://..."]},\n'
        "  ...\n"
        "]"
    )


def _user_message(findings: list[Finding]) -> str:
    lines = ["Findings:"]
    for f in findings:
        lines.append(f"\n--- {f.url} ---")
        lines.append(f"title: {f.title}")
        if f.excerpt:
            lines.append(f"excerpt: {f.excerpt}")
    lines.append("\nExtract insights now.")
    return "\n".join(lines)


def _parse_insights(raw: str) -> list[dict]:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_array(text))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [p for p in parsed if isinstance(p, dict)]


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
