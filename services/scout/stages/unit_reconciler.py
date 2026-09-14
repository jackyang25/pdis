"""Identity of dynamically extracted document claims, before retrieval.

The model partitions existing units; code preserves their source lineage. This
is not quantitative-target reconciliation or external-insight reconciliation:
those own different atoms and run after this provider boundary has closed.
"""

from __future__ import annotations

from dataclasses import asdict, replace
import json

from ..ai import request_structured
from ..ai_contracts import unit_reconciliation
from ..models import Attribute, LLMClientProtocol


# One complete extracted set per request: identity is a partition of that set,
# including duplicates across extraction chunks. Arbitrary batching would make
# equivalence depend on where an extraction happened to split the document.
UNIT_SETS_PER_REQUEST = 1
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
    images_by_block_id: dict[str, str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Attribute]:
    """Return a complete identity partition or fail before downstream processing.

    A malformed partition gets one retry, never guessed repairs or a silent
    'deduplicated' success. Provider failures propagate through the run boundary.
    Transient IDs are positions, not names: extraction names may still collide.
    """
    if len(units) < 2:
        return units
    by_id = {f"unit-{index}": unit for index, unit in enumerate(units)}
    contract = unit_reconciliation(list(by_id))
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
    images = [
        {"block_id": block_id, "data_url": image}
        for block_id, image in (images_by_block_id or {}).items()
        if block_id in cited_ids
    ]
    prompt = build_system_prompt()
    for attempt in range(2):
        parsed = request_structured(
            llm_client, contract,
            prompt + ("\nThe previous response was not a complete valid partition. "
                      "Include every ID exactly once and each representative among its members."
                      if attempt else ""),
            payload, max_tokens=max_tokens, images=images or None,
        )
        groups = _validated_groups(parsed, list(by_id))
        if groups is not None:
            return _merge_groups(by_id, groups)
    raise ValueError("Dynamic unit reconciliation failed: invalid partition after retry")


def _validated_groups(
    parsed: object, allowed_ids: list[str],
) -> list[tuple[str, list[str]]] | None:
    if not isinstance(parsed, list):
        return None
    allowed = set(allowed_ids)
    seen: set[str] = set()
    groups: list[tuple[str, list[str]]] = []
    for group in parsed:
        if not isinstance(group, dict) or set(group) != {
            "representative_unit_id", "member_unit_ids",
        }:
            return None
        representative = group["representative_unit_id"]
        members = group["member_unit_ids"]
        if not isinstance(representative, str) or representative not in allowed:
            return None
        if not isinstance(members, list) or not members or representative not in members:
            return None
        for member in members:
            if not isinstance(member, str) or member not in allowed or member in seen:
                return None
            seen.add(member)
        groups.append((representative, members))
    return groups if seen == allowed else None


def _merge_groups(
    by_id: dict[str, Attribute], groups: list[tuple[str, list[str]]],
) -> list[Attribute]:
    order = {unit_id: index for index, unit_id in enumerate(by_id)}
    result: list[Attribute] = []
    for representative, members in sorted(groups, key=lambda g: min(order[m] for m in g[1])):
        sources = [by_id[member] for member in sorted(members, key=order.__getitem__)]
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
