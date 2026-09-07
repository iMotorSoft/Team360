"""Unit tests for seasonality domain, forecast, metrics, backtest."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.seasonality import forecast as fc
from modules.telchi.investigation.validation.seasonality import metrics as mt
from modules.telchi.investigation.validation.seasonality import backtest as bt
from modules.telchi.investigation.validation.seasonality import seasonality_domain as sd


def series_from(pairs: dict[tuple[int, int], float]):
    return {k: v for k, v in pairs.items()}


class TestZeroFill(unittest.TestCase):
    def test_fill_missing_months(self):
        s = {(2025, 1): 100.0, (2025, 4): 80.0}
        f = sd.fill_zero_months(s)
        self.assertEqual(f[(2025, 2)], 0.0)
        self.assertEqual(f[(2025, 3)], 0.0)
        self.assertEqual(f[(2025, 1)], 100.0)
        self.assertEqual(len(f), 4)


class TestClassify(unittest.TestCase):
    def _seasonal(self):
        s = {}
        for y in (2023, 2024, 2025):
            for m in range(1, 13):
                q = 100.0
                if m in (11, 12, 1):
                    q = 600.0
                s[(y, m)] = q
        return s

    def test_seasonal(self):
        p = sd.classify(self._seasonal(), 2026, 3)
        self.assertEqual(p.pattern, sd.PATTERN_SEASONAL)
        self.assertEqual(p.confidence, "HIGH")

    def test_stable(self):
        s = {(y, m): 100.0 for y in (2024, 2025) for m in range(1, 13)}
        p = sd.classify(s, 2026, 3)
        self.assertEqual(p.pattern, sd.PATTERN_STABLE)

    def test_discontinued(self):
        s = {(2023, 1): 100.0, (2023, 2): 80.0, (2023, 3): 90.0,
             (2023, 4): 70.0, (2023, 5): 60.0, (2023, 6): 50.0,
             (2023, 7): 40.0, (2023, 8): 30.0, (2023, 9): 20.0,
             (2023, 10): 10.0, (2023, 11): 5.0, (2023, 12): 2.0}
        p = sd.classify(s, 2026, 3)
        self.assertEqual(p.pattern, sd.PATTERN_DISCONTINUED)

    def test_growing(self):
        s = {}
        for y in (2024, 2025):
            base = 100.0 if y == 2024 else 300.0
            for m in range(1, 13):
                s[(y, m)] = base
        p = sd.classify(s, 2026, 3)
        self.assertEqual(p.pattern, sd.PATTERN_GROWING)

    def test_insufficient(self):
        s = {(2025, 1): 50.0, (2025, 2): 60.0}
        p = sd.classify(s, 2026, 3)
        self.assertEqual(p.pattern, sd.PATTERN_INSUFFICIENT)


class TestForecast(unittest.TestCase):
    def setUp(self):
        self.s = {}
        for y in (2023, 2024, 2025):
            for m in range(1, 13):
                self.s[(y, m)] = 100.0 + m * 10

    def test_smly(self):
        self.assertEqual(fc.same_month_last_year(self.s, 2026, 5), 150.0)

    def test_naive(self):
        self.assertEqual(fc.naive_last_month(self.s, 2026, 1), self.s[(2025, 12)])

    def test_seasonal_ma(self):
        # mean of same month over 2023,2024,2025
        self.assertEqual(fc.seasonal_moving_average(self.s, 2026, 5), 150.0)

    def test_clamp_negative(self):
        self.assertEqual(fc.naive_last_month({}, 2026, 1), 0.0)


class TestMetrics(unittest.TestCase):
    def test_mae(self):
        self.assertEqual(mt.mae([10, 20], [12, 18]), 2.0)

    def test_wape(self):
        self.assertAlmostEqual(mt.wape([100, 100], [110, 90]), 0.1)

    def test_bias(self):
        self.assertAlmostEqual(mt.bias([10, 10], [12, 12]), 2.0)
        self.assertAlmostEqual(mt.bias([10, 10], [8, 8]), -2.0)


class TestBacktest(unittest.TestCase):
    def test_no_leakage(self):
        s = {(y, m): 100.0 for y in (2024, 2025) for m in range(1, 13)}
        snaps = [(2025, 6), (2025, 7)]
        res = bt.walk_forward(s, snaps, horizon=2, methods=["SAME_MONTH_LAST_YEAR"])
        r = res["SAME_MONTH_LAST_YEAR"]
        self.assertEqual(r["n"], 4)  # 2 snapshots x 2 horizon
        # SMLY at snapshot 2025-06 for month 7 = series[2024-07] = 100; actual 2025-07 = 100
        self.assertEqual(r["mae"], 0.0)
        self.assertEqual(r["wape"], 0.0)
        self.assertEqual(r["bias"], 0.0)

    def test_choose_method(self):
        res = {
            "A": {"wape": 0.3, "mae": 10.0, "n": 5},
            "B": {"wape": 0.2, "mae": 12.0, "n": 5},
        }
        self.assertEqual(bt.choose_method(res), "B")


if __name__ == "__main__":
    unittest.main()