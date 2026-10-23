"""Descriptive statistics shared by Scout's calibration and Drafter's comparable values."""

from __future__ import annotations

import unittest

from shared.statistics import describe, empirical_percentile, quantile


class StatisticsTests(unittest.TestCase):
    def test_quantile_interpolates_between_ranks(self):
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(quantile(values, 0.25), 1.75)
        self.assertEqual(quantile(values, 0.5), 2.5)
        self.assertEqual(quantile(values, 0.75), 3.25)

    def test_quantile_of_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            quantile([], 0.5)

    def test_percentile_counts_ties_as_half(self):
        self.assertEqual(empirical_percentile([1.0, 2.0, 2.0, 3.0], 2.0), 0.5)

    def test_describe_sorts_and_rounds(self):
        summary = describe([3.0, 1.0, 2.0])
        self.assertEqual((summary.count, summary.minimum, summary.maximum), (3, 1.0, 3.0))
        self.assertEqual(summary.median, 2.0)
        self.assertEqual(summary.standard_deviation, 1.0)

    def test_one_value_has_no_spread(self):
        self.assertIsNone(describe([5.0]).standard_deviation)

    def test_describing_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            describe([])


if __name__ == "__main__":
    unittest.main()
