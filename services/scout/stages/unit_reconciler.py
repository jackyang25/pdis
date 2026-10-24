"""Identity of dynamically extracted document claims, before retrieval.

The model partitions existing units; code preserves their source lineage. This
is not quantitative-target reconciliation or external-insight reconciliation:
those own different atoms and run after this provider boundary has closed.
"""

from __future__ import annotations

from dataclasses import asdict, replace
import json

from shared.ai import Effort, ModelTask

from ..ai_contracts import unit_reconciliation
from ..identity import Group, partition
from ..models import Attribute, IdentityReconciliation, LLMClientProtocol


# One complete extracted set per request: identity is a partition of that set,
# including duplicates across extraction chunks. Arbitrary batching would make
# equivalence depend on where an extraction happened to split the document.
UNIT_SETS_PER_REQUEST = 1
#: The reasoning tier at medium effort: one call per run, and a wrong merge removes a
#: claim from everything downstream while a missed one only repeats it.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "medium"
DEFAULT_MAX_TOKENS = 8000


def build_system_prompt() -> str:
    return (
        "ROLE\n"
        "Decide which already-extracted document units express the same checkable "
        "assertion. Partition the supplied unit IDs and choose an existing representative "
        "for each group. Do not extract, rewrite, rank, or judge claims.\n\n"
        "SCOPE\n"
        "Each unit's description defines what is being evaluated; its document_spans "
        "supply the actual assertion and surrounding context. Read them together. "
        "Two units citing the same paragraph or image can evaluate different assertions. "
        "Shared names, passages, evidence domains, topics, or numbers do not establish "
        "identity. Differently named or paraphrased units may express the same assertion. "
        "Attached images are labeled with their exact block IDs and belong only to "
        "units citing those IDs.\n\n"
        "IDENTITY RULE\n"
        "Merge only restatements of the SAME assertion with equivalent subject, "
        "population, endpoint or milestone, value or date, conditions, and modality "
        "(planned, expected, or achieved). Preserve negation and uncertainty. Keep "
        "different products, dates, populations, comparators, conditions, minimum versus "
        "optimistic targets, and plans versus completed events separate. A submission "
        "and an approval are different milestones. Conflicting statements must remain "
        "separate; do not choose which is correct or newer. A broader claim and a "
        "narrower claim, or partially overlapping compound claims, are not duplicates. "
        "Missing qualifiers do not establish equivalence: merge only when the cited "
        "context establishes the same scope. When uncertain, keep singleton groups.\n\n"
        "REPRESENTATIVE\n"
        "Choose the existing member whose description most clearly identifies the "
        "shared assertion, consistent with all members' cited context. Code retains "
        "that member's name, description, and evidence domain and unions all members' "
        "source passages and entities. You cannot invent replacement text or citations.\n\n"
        "OUTPUT\n"
        "Return every supplied unit ID exactly once in member_unit_ids, including "
        "singleton groups. Each representative_unit_id must belong to its own group. "
        "Return only the schema-bound groups."
    )


def reconcile_units(
    units: list[Attribute],
    llm_client: LLMClientProtocol,
    *,
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[list[Attribute], IdentityReconciliation | None]:
    """Return the reconciled units and what the identity layer decided.

    Zero or one unit needs no call and records nothing. A partition that stays invalid
    after one retry, or a failed call, leaves every unit as extracted and records the
    failure (`identity.partition`). Transient IDs are positions, not names: extraction
    names may still collide.
    """
    if len(units) < 2:
        return units, None
    by_id = {f"unit-{index}": unit for index, unit in enumerate(units)}
    payload = json.dumps([
        {
            "unit_id": unit_id,
            "name": unit.name,
            "description": unit.description,
            "evidence_domain": unit.evidence_domain,
            "document_spans": [asdict(span) for span in unit.document_spans],
        }
        for unit_id, unit in by_id.items()
    ], ensure_ascii=False)
    cited_ids = {block_id for unit in units for block_id in unit.block_ids}
    result = partition(
        llm_client,
        unit_reconciliation(list(by_id)),
        build_system_prompt(),
        payload,
        ids=list(by_id),
        representative_key="representative_unit_id",
        members_key="member_unit_ids",
        layer="document_units",
        max_tokens=max_tokens,
        task=TASK,
        effort=EFFORT,
        images=[image for image in images or [] if image["block_id"] in cited_ids] or None,
    )
    return _merge_groups(by_id, result.groups), result.record


def _merge_groups(by_id: dict[str, Attribute], groups: list[Group]) -> list[Attribute]:
    result: list[Attribute] = []
    for representative, members in groups:
        sources = [by_id[member] for member in members]
        spans = {
            (span.quote, tuple(span.block_ids)): span
            for source in sources for span in source.document_spans
        }
        # Attribute derives target text and block IDs from these exact spans.
        # Only provenance is combined; the representative's authored fields stay intact.
        result.append(replace(
            by_id[representative], document_spans=list(spans.values()),
            entities=list(dict.fromkeys(entity for source in sources for entity in source.entities)),
        ))
    return result
