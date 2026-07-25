"""Stage 2: extract atomic Insights from external retrieval Findings.

Given a flat list of Findings (collected across all queries), the LLM
extracts atomic factual statements, each tied to one or more supporting
Findings by URL. We then re-attach the full Finding objects.
"""

from __future__ import annotations

import logging
import re

from services.searcher import Finding

from ..ai import request_structured
from ..ai_contracts import insight_batch
from ..models import Insight, LLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 24000
MAX_FINDING_EXCERPT_CHARS = 6000


def extract_insights(
    findings: list[Finding],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    attribute_ref: str | None = None,
    attribute_description: str = "",
    query_tracks: dict[str, list[str]] | None = None,
    query_targets: dict[str, list[str]] | None = None,
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
    user_message = _user_message(findings, query_tracks=query_tracks)
    contract = insight_batch(list(dict.fromkeys(finding.url for finding in findings)))

    parsed = request_structured(
        llm_client,
        contract,
        system_prompt,
        user_message,
        max_tokens=max_tokens,
    )
    if not isinstance(parsed, list):
        parsed = request_structured(
            llm_client,
            contract,
            system_prompt,
            user_message,
            max_tokens=max_tokens,
        )
    parsed = _validated_insights(parsed)

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
        tracks = list(
            dict.fromkeys(
                track
                for finding in supporting
                for finding_query in (finding.queries or [finding.query])
                for track in (query_tracks or {}).get(finding_query, [])
            )
        )
        retrieval_target_ids = list(
            dict.fromkeys(
                target_id
                for finding in supporting
                for finding_query in (finding.queries or [finding.query])
                for target_id in (query_targets or {}).get(finding_query, [])
            )
        )
        insights.append(
            Insight(
                statement=statement,
                supporting_findings=supporting,
                query=query,
                query_tracks=tracks,
                retrieval_target_ids=retrieval_target_ids,
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
        f"You extract atomic factual insights from external search findings about "
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
        "- Preserve claim ownership. A value mentioned as background from a prior study, "
        "product, guideline, or publication is NOT a result of the current source record. "
        "If retained, the statement must explicitly attribute it to that prior evidence. "
        "Never rewrite background as a result of the page, paper, or registry record that "
        "mentions it. Skip the fact when ownership remains ambiguous.\n"
        "- Registry protocols and planned outcomes describe what a study intends to measure; "
        "they are not observed results. State them as planned only when that planning fact is "
        "itself relevant to this variable.\n"
        "- Do not invent facts not present in the findings.\n\n"
        "Return only the schema-bound `insights` response."
    )


def _user_message(
    findings: list[Finding],
    *,
    query_tracks: dict[str, list[str]] | None = None,
) -> str:
    lines = ["Findings:"]
    for f in findings:
        lines.append(f"\n--- {f.url} ---")
        lines.append(f"title: {f.title}")
        lines.append(f"source lane: {f.source}")
        if f.published_at:
            lines.append(f"published: {f.published_at.isoformat()}")
        queries = getattr(f, "queries", None) or [f.query]
        lines.append(f"discovered by: {' | '.join(q for q in queries if q)}")
        tracks = list(
            dict.fromkeys(
                track for query in queries for track in (query_tracks or {}).get(query, [])
            )
        )
        if tracks:
            lines.append(f"coverage tracks: {', '.join(tracks)}")
        if f.excerpt:
            excerpt = f.excerpt[:MAX_FINDING_EXCERPT_CHARS]
            if len(f.excerpt) > MAX_FINDING_EXCERPT_CHARS:
                excerpt += "...[source excerpt clipped]"
            lines.append(f"excerpt: {excerpt}")
    lines.append("\nExtract insights now.")
    return "\n".join(lines)


def merge_duplicate_insights(insights: list[Insight]) -> list[Insight]:
    """Merge exact/near-exact statements emitted by separate finding batches.

    The LLM deduplicates within each batch. This deterministic second pass keeps
    batch parallelism from duplicating the same atomic fact across batches while
    preserving the union of every cited Finding.
    """
    by_statement: dict[tuple[str, str], Insight] = {}
    out: list[Insight] = []
    for insight in insights:
        normalized = re.sub(r"[^a-z0-9]+", " ", insight.statement.lower()).strip()
        key = (insight.attribute_ref or "", normalized)
        existing = by_statement.get(key)
        if existing is None:
            by_statement[key] = insight
            out.append(insight)
            continue
        seen_urls = {finding.url for finding in existing.supporting_findings}
        for finding in insight.supporting_findings:
            if finding.url not in seen_urls:
                existing.supporting_findings.append(finding)
                seen_urls.add(finding.url)
        existing.query_tracks = list(
            dict.fromkeys([*existing.query_tracks, *insight.query_tracks])
        )
        existing.retrieval_target_ids = list(
            dict.fromkeys(
                [*existing.retrieval_target_ids, *insight.retrieval_target_ids]
            )
        )
        existing.refresh_id()
    return out


def _validated_insights(parsed: object) -> list[dict]:
    if not isinstance(parsed, list):
        return []
    return [p for p in parsed if isinstance(p, dict)]
