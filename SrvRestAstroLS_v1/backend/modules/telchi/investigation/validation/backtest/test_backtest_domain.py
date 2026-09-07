"""Unit tests for the purchase decision backtest domain (pure, no HANA)."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.backtest.backtest_domain import (
    VERDICT_CONSISTENT, VERDICT_EARLY_WARNING, VERDICT_MISSED, VERDICT_OVERBUY,
    actual_stockout, early_warning_accuracy, fill_zero_months, predict_stockout,
    verdict_for,
)


class TestZeroFill(unittest.TestCase):
    def test_fill_range(self):
        s = {(2025, 1): 10.0}
        f = fill_zero_months(s, (2025, 1), (2025, 3))
        self.assertEqual(f[(2025, 2)], 0.0)
        self.assertEqual(f[(2025, 3)], 0.0)
        self.assertEqual(f[(2025, 1)], 10.0)


class TestWaterfall(unittest.TestCase):
    def test_predict_stockout(self):
        fc = {(2025, 2): 60.0, (2025, 3): 60.0, (2025, 4): 60.0}
        self.assertEqual(predict_stockout("RAW", 100.0, fc), (2025, 3))

    def test_predict_safe(self):
        fc = {(2025, 2): 30.0, (2025, 3): 30.0}
        self.assertIsNone(predict_stockout("RAW", 100.0, fc))

    def test_actual_stockout(self):
        act = {(2025, 2): 50.0, (2025, 3): 60.0}
        self.assertEqual(actual_stockout("RAW", 80.0, act), (2025, 3))


class TestVerdict(unittest.TestCase):
    def test_early_warning(self):
        self.assertEqual(verdict_for((2025, 3), (2025, 3)), VERDICT_EARLY_WARNING)

    def test_missed(self):
        self.assertEqual(verdict_for(None, (2025, 3)), VERDICT_MISSED)

    def test_overbuy(self):
        self.assertEqual(verdict_for((2025, 3), None), VERDICT_OVERBUY)

    def test_consistent(self):
        self.assertEqual(verdict_for(None, None), VERDICT_CONSISTENT)


class TestAccuracy(unittest.TestCase):
    def test_within_tolerance(self):
        self.assertTrue(early_warning_accuracy((2025, 3), (2025, 2)))
        self.assertTrue(early_warning_accuracy((2025, 3), (2025, 4)))

    def test_outside_tolerance(self):
        self.assertFalse(early_warning_accuracy((2025, 3), (2025, 6)))

    def test_none(self):
        self.assertFalse(early_warning_accuracy(None, (2025, 3)))


if __name__ == "__main__":
    unittest.main()
