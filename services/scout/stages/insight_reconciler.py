"""Stage: decide which extracted insights state the same external fact.

Extraction creates objects. This layer decides identity, and nothing else: it
may only partition the supplied insight IDs and name a representative, never
rewrite a statement, a citation, or a field assignment. Keeping identity out of
the extraction prompt means duplicate detection improves by editing one prompt
rather than by changing how insights are produced.

One request carries one field's insights, because the answer is a statement
about that set. Insights belonging to different fields are never compared.
"""

from __future__ import annotations

import json
import logging

from ..ai import request_structured
from ..ai_contracts import insight_reconciliation
from shared.batching import map_ordered
from ..models import Insight, LLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 6000
RECONCILIATION_WORKERS = 6


def build_reconciliation_system_prompt() -> str:
    """Instructions sent when grouping repeated statements of one fact."""
    return (
        "ROLE\n"
        "You reconcile already-extracted external insights for one evaluation field. "
        "You may only partition the supplied insight IDs and select an existing "
        "representative; you cannot rewrite statements, citations, or field assignments.\n\n"
        "INPUT AUTHORITY\n"
        "The supplied statements are immutable. Reconciliation changes identity grouping "
        "only.\n\n"
        "DECISION PROCEDURE\n"
        "Group insights only when they state the SAME atomic external fact, including the "
        "same reported entity, population, and measurement. A translation, a mirror or "
        "republication, a preprint and its journal version, and a registry record and its "
        "publication of the same result are one fact. Equal numbers alone are not "
        "sufficient: keep different products, populations, endpoints, time points, study "
        "arms, or reporting sources separate. A more specific subgroup finding is not the "
        "same fact as its broader population. Different measurements of one study remain "
        "separate facts. When genuinely unsure, keep the insights separate.\n"
        "For each group, choose the member whose wording states the fact most completely "
        "and neutrally as representative.\n\n"
        "OUTPUT CONTRACT\n"
        "Return every supplied insight ID exactly once, including singleton groups, and "
        "give each group a short reason. Return only the schema-bound response."
    )


def reconcile_duplicate_insights(
    insights: list[Insight],
    llm_client: LLMClientProtocol | None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Insight]:
    """Merge semantically duplicate insights, preserving every citation.

    Failure, an unparsable reply, or an incomplete partition retains every
    insight unchanged: a visible duplicate is recoverable, a silently dropped
    source is not.
    """
    if llm_client is None or len(insights) < 2:
        return insights

    by_field: dict[str, list[Insight]] = {}
    for insight in insights:
        by_field.setdefault(insight.attribute_ref or "", []).append(insight)

    fields = [field for field, group in by_field.items() if len(group) > 1]
    if not fields:
        return insights

    def reconcile_field(field: str) -> dict[str, str]:
        return _representatives(by_field[field], llm_client, max_tokens=max_tokens)

    member_to_representative: dict[str, str] = {}
    for mapping in map_ordered(
        fields, reconcile_field, workers=RECONCILIATION_WORKERS
    ):
        member_to_representative.update(mapping)

    if not member_to_representative:
        return insights
    return _merge_into_representatives(insights, member_to_representative)


def _representatives(
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> dict[str, str]:
    """Return one member-to-representative map for a complete partition."""
    allowed_ids = [insight.id for insight in insights]
    contract = insight_reconciliation(allowed_ids)
    prompt = build_reconciliation_system_prompt()
    payload = json.dumps(
        [
            {
                "insight_id": insight.id,
                "statement": insight.statement,
                "cited_urls": [
                    finding.url for finding in insight.supporting_findings
                ],
                "source_lanes": sorted({
                    finding.source for finding in insight.supporting_findings
                }),
            }
            for insight in insights
        ],
        ensure_ascii=False,
        indent=2,
    )
    try:
        parsed = request_structured(
            llm_client,
            contract,
            prompt,
            payload,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # Identity triage must degrade to no grouping.
        logger.warning(
            "Insight reconciliation failed; retaining insights unchanged: %s", exc
        )
        return {}
    mapping = _validated_partition(parsed, allowed_ids)
    if mapping is None:
        logger.warning(
            "Insight reconciliation returned an invalid partition of %d insight(s); "
            "retaining them unchanged",
            len(allowed_ids),
        )
        return {}
    return mapping


def _validated_partition(
    parsed: object,
    allowed_ids: list[str],
) -> dict[str, str] | None:
    """Accept only a complete partition drawn from the supplied IDs."""
    if not isinstance(parsed, list):
        return None
    allowed = set(allowed_ids)
    mapping: dict[str, str] = {}
    for group in parsed:
        if not isinstance(group, dict):
            return None
        representative = str(group.get("representative_insight_id", "")).strip()
        members = group.get("member_insight_ids")
        if representative not in allowed or not isinstance(members, list):
            return None
        member_ids = [str(member).strip() for member in members]
        if representative not in member_ids:
            member_ids.append(representative)
        for member_id in member_ids:
            if member_id not in allowed or member_id in mapping:
                return None
            mapping[member_id] = representative
    if set(mapping) != allowed:
        return None
    return mapping


def _merge_into_representatives(
    insights: list[Insight],
    member_to_representative: dict[str, str],
) -> list[Insight]:
    """Keep each representative in place and union its members' provenance."""
    by_id = {insight.id: insight for insight in insights}
    merged: list[Insight] = []
    for insight in insights:
        representative_id = member_to_representative.get(insight.id, insight.id)
        if representative_id == insight.id:
            merged.append(insight)
            continue
        representative = by_id.get(representative_id)
        if representative is None:
            merged.append(insight)
            continue
        seen_urls = {
            finding.url for finding in representative.supporting_findings
        }
        for finding in insight.supporting_findings:
            if finding.url not in seen_urls:
                representative.supporting_findings.append(finding)
                seen_urls.add(finding.url)
        representative.query_tracks = list(
            dict.fromkeys([*representative.query_tracks, *insight.query_tracks])
        )
        representative.retrieval_target_ids = list(
            dict.fromkeys([
                *representative.retrieval_target_ids,
                *insight.retrieval_target_ids,
            ])
        )
    return merged
