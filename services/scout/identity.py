"""One mechanic for Scout's identity layers: partition a set by one model call.

Four layers decide which of their items are the same thing - dynamically extracted
document claims, numeric targets, one field's insights, and program and product names.
Each owns its prompt, its items and how it merges a group. What they shared, and had
each written differently, is the call and what happens when it fails: one raised and
stopped the run, two swallowed any exception and logged it, so duplicates were counted
twice with nothing in the result to say why.

Now one rule. A partition is validated as complete - every supplied ID exactly once,
each group naming one of its own members as representative - and an invalid one is
retried once with the error named. If no valid partition is obtained, the run continues
with the set unmerged and an :class:`IdentityReconciliation` records the failure and its
code. Stopping would discard a run over a duplicate a reader can see; merging on a guess
would hide one. Merging is never approximated by comparing strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from shared.ai import RECORDABLE_FAILURES, Effort, ModelTask, failure_code

from .ai import request_validated
from .ai_contracts import AIContract
from .models import IdentityReconciliation, LLMClientProtocol

#: One group: its representative and every member, the representative included, in
#: the order the items were supplied.
Group = tuple[str, list[str]]


@dataclass(frozen=True)
class Partition:
    groups: list[Group]
    record: IdentityReconciliation

    def representative_of(self) -> dict[str, str]:
        """Each member's representative; a representative maps to itself."""
        return {
            member: representative
            for representative, members in self.groups
            for member in members
        }


def singletons(ids: list[str]) -> list[Group]:
    return [(item, [item]) for item in ids]


def partition(
    llm_client: LLMClientProtocol,
    contract: AIContract,
    system_prompt: str,
    message: str,
    *,
    ids: list[str],
    representative_key: str,
    members_key: str,
    layer: str,
    scope: str = "",
    max_tokens: int,
    task: ModelTask,
    effort: Effort | None,
    images: list[dict[str, str]] | None = None,
    accept: Callable[[list[Group]], None] | None = None,
) -> Partition:
    """Ask for a complete partition of ``ids``; record, never raise, if none is obtained.

    ``accept`` adds a layer's own structural rule over a valid partition - numeric
    targets may only group when their calculation inputs agree - and raises
    ``ValueError`` naming what it refuses, which the retry then reads.
    """
    order = {item: index for index, item in enumerate(ids)}

    def parse(parsed: object) -> list[Group]:
        groups = _validated_groups(parsed, order, representative_key, members_key)
        if accept is not None:
            accept(groups)
        return groups

    try:
        groups = request_validated(
            llm_client,
            contract,
            system_prompt,
            message,
            max_tokens=max_tokens,
            parse=parse,
            failure=f"Identity reconciliation of {layer.replace('_', ' ')} failed",
            images=images,
            task=task,
            effort=effort,
        )
    except RECORDABLE_FAILURES as exc:
        return Partition(
            groups=singletons(ids),
            record=IdentityReconciliation(
                layer=layer,
                scope=scope,
                status="not_reconciled",
                items=len(ids),
                failure_code=failure_code(exc),
                reason=str(exc),
            ),
        )
    return Partition(
        groups=groups,
        record=IdentityReconciliation(
            layer=layer,
            scope=scope,
            status="reconciled",
            items=len(ids),
            merged=len(ids) - len(groups),
        ),
    )


def _validated_groups(
    parsed: object,
    order: dict[str, int],
    representative_key: str,
    members_key: str,
) -> list[Group]:
    """Accept only a complete partition drawn from the supplied IDs."""
    if not isinstance(parsed, list):
        raise ValueError("no groups array was returned")
    seen: set[str] = set()
    groups: list[Group] = []
    for raw in parsed:
        if not isinstance(raw, dict):
            raise ValueError("every group must be an object")
        representative = raw.get(representative_key)
        members = raw.get(members_key)
        if representative not in order or not isinstance(members, list):
            raise ValueError("every group names a supplied representative and its members")
        if representative not in members:
            raise ValueError(
                f"representative {representative} must be listed among its own members"
            )
        for member in members:
            if member not in order:
                raise ValueError(f"{member!r} is not a supplied ID")
            if member in seen:
                raise ValueError(f"{member} appears in more than one group")
            seen.add(member)
        groups.append((representative, sorted(dict.fromkeys(members), key=order.__getitem__)))
    missing = [item for item in order if item not in seen]
    if missing:
        raise ValueError(
            "every supplied ID must appear in exactly one group; missing: "
            + ", ".join(missing[:20])
        )
    return sorted(groups, key=lambda group: order[group[1][0]])
