"""Stage: decide which extracted insights state the same external fact.

Extraction creates objects. This layer decides identity, and nothing else: it
may only partition the supplied insights and name a representative, never
rewrite a statement, a citation, or a field assignment. Keeping identity out of
the extraction prompt means duplicate detection improves by editing one prompt
rather than by changing how insights are produced. It is the only layer that
decides it: no statement is merged beforehand for reading alike, because two
statements that differ only in case or spacing are for the model to call one fact.

One request carries one field's insights, because the answer is a statement
about that set. Insights belonging to different fields are never compared.
"""

from __future__ import annotations

import hashlib
import json

from shared.ai import Effort, ModelTask
from shared.batching import map_ordered

from ..ai_contracts import insight_reconciliation
from ..identity import Partition, partition
from ..insight_evidence import supporting_findings
from ..models import IdentityReconciliation, Insight, LLMClientProtocol

#: One field's insights per request: the partition is a statement about that set.
FIELDS_PER_REQUEST = 1
#: The reasoning tier at low effort: the decision is whether two statements are one
#: fact, over a short list, once per field.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "low"
# Reasoning counts against the budget; the reply itself is only IDs.
DEFAULT_MAX_TOKENS = 16000
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
        "publication of the same result are one fact. Two statements worded identically, "
        "or differing only in case or spacing, are one fact. Equal numbers alone are not "
        "sufficient: keep different products, populations, endpoints, time points, study "
        "arms, or reporting sources separate. A more specific subgroup finding is not the "
        "same fact as its broader population. Different measurements of one study remain "
        "separate facts. When genuinely unsure, keep the insights separate.\n"
        "For each group, choose the member whose wording states the fact most completely "
        "and neutrally as representative.\n\n"
        "OUTPUT CONTRACT\n"
        "Return every supplied insight ID exactly once, including singleton groups, with "
        "each representative listed among its own members. Return only the schema-bound "
        "response."
    )


def reconcile_duplicate_insights(
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[list[Insight], list[IdentityReconciliation]]:
    """Merge insights that state one fact, preserving every citation.

    Returns the insights with unique IDs, and one record per field that had two or
    more to compare. A field whose partition failed keeps every insight and says so.
    """
    by_field: dict[str, list[Insight]] = {}
    for insight in insights:
        by_field.setdefault(insight.attribute_ref or "", []).append(insight)
    fields = [field for field, group in by_field.items() if len(group) > 1]

    def reconcile_field(field: str) -> Partition:
        return _partition(field, by_field[field], llm_client, max_tokens=max_tokens)

    partitions = dict(zip(
        fields,
        map_ordered(fields, reconcile_field, workers=RECONCILIATION_WORKERS),
    ))
    merged: list[Insight] = []
    for field, group in by_field.items():
        result = partitions.get(field)
        merged.extend(_merge(group, result) if result else group)
    return unique_ids(merged), [partitions[field].record for field in fields]


def _partition(
    field: str,
    insights: list[Insight],
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> Partition:
    # Positions, not insight IDs: an ID is derived from the statement and its records,
    # so two identical statements share one, and a partition needs every item named.
    ids = [f"insight-{index}" for index in range(len(insights))]
    payload = json.dumps(
        [
            {
                "insight_id": transient_id,
                "statement": insight.statement,
                "sources": [
                    {"record": finding.record_key, "title": finding.title, "lane": finding.source}
                    for finding in insight.supporting_findings
                ],
            }
            for transient_id, insight in zip(ids, insights)
        ],
        ensure_ascii=False,
        indent=2,
    )
    return partition(
        llm_client,
        insight_reconciliation(ids),
        build_reconciliation_system_prompt(),
        payload,
        ids=ids,
        representative_key="representative_insight_id",
        members_key="member_insight_ids",
        layer="insights",
        scope=field,
        max_tokens=max_tokens,
        task=TASK,
        effort=EFFORT,
    )


def _merge(insights: list[Insight], result: Partition) -> list[Insight]:
    """Keep each representative in its place and union its members' provenance."""
    by_id = {f"insight-{index}": insight for index, insight in enumerate(insights)}
    merged: list[Insight] = []
    for representative_id, member_ids in result.groups:
        representative = by_id[representative_id]
        members = [by_id[member_id] for member_id in member_ids]
        if len(members) > 1:
            representative.supporting_findings = supporting_findings(
                [representative, *(member for member in members if member is not representative)]
            )
            representative.query_tracks = list(
                dict.fromkeys(track for member in members for track in member.query_tracks)
            )
            representative.retrieval_target_ids = list(dict.fromkeys(
                target_id for member in members for target_id in member.retrieval_target_ids
            ))
            # The ID is derived from the cited records, which the union may have extended.
            representative.refresh_id()
        merged.append(representative)
    return merged


def unique_ids(insights: list[Insight]) -> list[Insight]:
    """Give insights that derive one ID distinct ones, in order.

    Two insights derive one ID when they state one fact in the same words from the
    same records and the identity layer kept them apart, or could not run. Allocation,
    not identity: the first keeps its ID and the next is suffixed, so both survive.
    """
    seen: set[str] = set()
    for insight in insights:
        base, ordinal = insight.id, 2
        while insight.id in seen:
            insight.id = f"{base}-{hashlib.sha256(f'{base}:{ordinal}'.encode()).hexdigest()[:4]}"
            ordinal += 1
        seen.add(insight.id)
    return insights
