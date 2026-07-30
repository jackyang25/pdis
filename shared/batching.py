"""One batching and fan-out policy for every service's model stages.

Every stage sends bounded requests, so every stage needs a batching decision.
Making that decision once, here, keeps it visible instead of re-derived per
stage. The rule is:

  A request may contain several items ONLY when the stage's answer is a
  statement about the set — deduplication, partitioning, or one aggregate
  judgement. A stage that returns one decision per item must send one item per
  request, because unrelated items in a shared prompt can influence each
  other's decision and batch composition shifts between runs.

Stages declare which case they are with a module-level ``<ITEMS>_PER_REQUEST``
constant carrying its justification, and call the matching helper below. Speed
comes from :func:`map_ordered` fan-out, never from packing unrelated items into
one prompt.

One documented exception exists: ``conformity.LEDGER_UNITS_PER_REQUEST`` batches
per-unit decisions because the same constant also bounds how much document the
model may read. Splitting those two roles changes token cost or the prompt, so it
is tracked at that constant rather than silently resolved here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Hashable, Iterable, Sequence, TypeVar

_T = TypeVar("_T")
_R = TypeVar("_R")


def fixed_batches(items: Sequence[_T], size: int) -> list[list[_T]]:
    """Split items into requests of at most ``size``.

    ``size=1`` is the per-item scope: one decision, one request.
    """
    if size < 1:
        raise ValueError("batch size must be at least 1")
    return [
        list(items[index:index + size])
        for index in range(0, len(items), size)
    ]


def budgeted_batches(
    items: Iterable[_T],
    *,
    max_items: int,
    max_chars: int,
    size_of: Callable[[_T], int],
) -> list[list[_T]]:
    """Split items by both a count and a rendered-size budget.

    An item larger than ``max_chars`` still gets its own request rather than
    being dropped; truncation is each stage's own concern.
    """
    if max_items < 1:
        raise ValueError("batch size must be at least 1")
    batches: list[list[_T]] = []
    current: list[_T] = []
    current_chars = 0
    for item in items:
        size = size_of(item)
        if current and (
            len(current) >= max_items
            or current_chars + size > max_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def grouped_batches(
    items: Iterable[_T],
    *,
    key: Callable[[_T], Hashable],
    groups_per_batch: int,
) -> list[list[_T]]:
    """Keep every item sharing a ``key`` in one request, never split.

    Use this where items belong to a container that must be judged whole — all
    passages of one source record, for instance — while still limiting how many
    unrelated containers share a prompt.
    """
    if groups_per_batch < 1:
        raise ValueError("batch size must be at least 1")
    grouped: dict[Hashable, list[_T]] = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)

    batches: list[list[_T]] = []
    current: list[_T] = []
    current_groups = 0
    for group in grouped.values():
        if current and current_groups >= groups_per_batch:
            batches.append(current)
            current = []
            current_groups = 0
        current.extend(group)
        current_groups += 1
    if current:
        batches.append(current)
    return batches


def map_ordered(
    items: Sequence[_T],
    run: Callable[[_T], _R],
    *,
    workers: int,
) -> list[_R]:
    """Run ``run`` over ``items`` concurrently, returning results in input order.

    Ordered results keep a stage's output independent of completion order, so
    fan-out changes throughput and nothing else.
    """
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as executor:
        return list(executor.map(run, items))
