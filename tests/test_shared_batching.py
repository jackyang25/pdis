"""One shared batching and fan-out policy for Scout's model stages."""

from __future__ import annotations

import threading
import unittest

from shared.batching import (
    budgeted_batches,
    fixed_batches,
    grouped_batches,
    map_ordered,
)


class FixedBatchTests(unittest.TestCase):
    def test_per_item_scope_isolates_every_decision(self) -> None:
        self.assertEqual(fixed_batches([1, 2, 3], 1), [[1], [2], [3]])

    def test_set_scope_packs_up_to_the_declared_size(self) -> None:
        self.assertEqual(fixed_batches([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_no_items_produces_no_requests(self) -> None:
        self.assertEqual(fixed_batches([], 3), [])


class BudgetedBatchTests(unittest.TestCase):
    def test_a_character_budget_closes_a_batch_before_the_count_does(self) -> None:
        batches = budgeted_batches(
            ["aaaa", "bbbb", "cc"],
            max_items=10,
            max_chars=8,
            size_of=len,
        )
        self.assertEqual(batches, [["aaaa", "bbbb"], ["cc"]])

    def test_a_single_oversized_item_still_gets_its_own_request(self) -> None:
        batches = budgeted_batches(
            ["x" * 50, "y"],
            max_items=10,
            max_chars=8,
            size_of=len,
        )
        self.assertEqual(batches, [["x" * 50], ["y"]])

    def test_the_item_count_closes_a_batch_before_the_budget_does(self) -> None:
        batches = budgeted_batches(
            ["a", "b", "c"],
            max_items=2,
            max_chars=1000,
            size_of=len,
        )
        self.assertEqual(batches, [["a", "b"], ["c"]])


class GroupedBatchTests(unittest.TestCase):
    def test_one_group_is_never_split_across_requests(self) -> None:
        items = [("r1", "a"), ("r2", "b"), ("r1", "c")]
        batches = grouped_batches(items, key=lambda item: item[0], groups_per_batch=1)
        self.assertEqual(batches, [[("r1", "a"), ("r1", "c")], [("r2", "b")]])

    def test_unrelated_groups_share_a_request_only_when_declared(self) -> None:
        items = [("r1", "a"), ("r2", "b"), ("r3", "c")]
        batches = grouped_batches(items, key=lambda item: item[0], groups_per_batch=2)
        self.assertEqual(batches, [[("r1", "a"), ("r2", "b")], [("r3", "c")]])


class MapOrderedTests(unittest.TestCase):
    def test_results_follow_input_order_regardless_of_completion_order(self) -> None:
        started = threading.Barrier(3)

        def slow_first(value: int) -> int:
            started.wait(timeout=5)
            return value * 2

        self.assertEqual(map_ordered([1, 2, 3], slow_first, workers=3), [2, 4, 6])

    def test_fan_out_never_requests_more_workers_than_items(self) -> None:
        observed: list[int] = []
        lock = threading.Lock()

        def record(value: int) -> int:
            with lock:
                observed.append(value)
            return value

        self.assertEqual(map_ordered([7], record, workers=16), [7])
        self.assertEqual(observed, [7])

    def test_no_items_runs_no_work(self) -> None:
        def unreachable(_value: int) -> int:
            raise AssertionError("no work should run")

        self.assertEqual(map_ordered([], unreachable, workers=4), [])


if __name__ == "__main__":
    unittest.main()
