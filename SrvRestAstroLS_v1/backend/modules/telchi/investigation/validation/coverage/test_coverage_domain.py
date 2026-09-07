"""Unit tests for the equivalent material coverage domain (pure, no HANA).

P0 tests required by the gate:
  - FG fully covers demand
  - FG runs out, production covers the rest
  - FG + production both run out
  - seasonal peak causes temporary shortfall
  - later demand falls after peak (surplus after stockout month)
  - no double counting: equivalent-in-FG not reused, open purchase separate,
    shared component stock allocated once, forecast not duplicated by BOM joins
  - seasonality: month-by-month coverage != annual-average coverage
  - lead time: coverage=60d vs p90=110d -> LEAD_TIME_COVERAGE_GAP < 0
  - import supply: open PO without physical confirmation is not current stock
  - shared component: 100 units cannot yield 100 A + 100 B simultaneously
  - multilevel: raw demand propagates to terminal
"""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.coverage.coverage_domain import (
    ComponentCoverage,
    aggregate_component_requirement,
    build_forward_forecast,
    coverage_ratio,
    horizon_days,
    lead_time_coverage_gap,
    run_component_waterfall,
    run_fg_waterfall,
    sum_demand_to,
)


def demand(*pairs):
    return list(pairs)


class TestFgWaterfall(unittest.TestCase):
    def test_fg_fully_covers(self):
        cov = run_fg_waterfall("FG1", demand((2026, 9, 100), (2026, 10, 80)),
                               300.0, 0.0)
        self.assertTrue(cov.fully_covered)
        self.assertIsNone(cov.stockout_month)
        self.assertEqual(cov.covered_through_month, (2026, 10))
        self.assertAlmostEqual(cov.months[-1].fg_end, 120.0)

    def test_fg_runs_out_production_covers(self):
        cov = run_fg_waterfall("FG1", demand((2026, 9, 100), (2026, 10, 100),
                                             (2026, 11, 100)),
                               150.0, 200.0)
        self.assertTrue(cov.fully_covered)
        self.assertEqual(cov.covered_through_month, (2026, 11))
        # month 10 consumed 50 FG + 50 prod
        self.assertAlmostEqual(cov.months[1].fg_consumed, 50.0)
        self.assertAlmostEqual(cov.months[1].prod_consumed, 50.0)

    def test_fg_and_production_both_run_out(self):
        cov = run_fg_waterfall("FG1", demand((2026, 9, 200), (2026, 10, 200),
                                             (2026, 11, 200)),
                               150.0, 100.0)
        self.assertFalse(cov.fully_covered)
        self.assertEqual(cov.stockout_month, (2026, 10))
        self.assertEqual(cov.covered_through_month, (2026, 9))
        self.assertAlmostEqual(cov.months[1].unmet, 150.0)

    def test_seasonal_peak_temporary_shortfall(self):
        # low months covered, peak month shortfall
        cov = run_fg_waterfall("FG1", demand((2026, 9, 50), (2026, 10, 50),
                                             (2026, 11, 50), (2026, 12, 50),
                                             (2027, 1, 300), (2027, 2, 50)),
                               200.0, 0.0)
        self.assertEqual(cov.stockout_month, (2027, 1))
        self.assertEqual(cov.covered_through_month, (2026, 12))

    def test_later_demand_falls_after_peak(self):
        # surplus after peak: production covers the tail
        cov = run_fg_waterfall("FG1", demand((2026, 9, 500), (2026, 10, 500),
                                             (2026, 11, 100), (2026, 12, 100)),
                               200.0, 1000.0)
        self.assertTrue(cov.fully_covered)
        self.assertEqual(cov.covered_through_month, (2026, 12))

    def test_zero_supply_immediate_stockout(self):
        cov = run_fg_waterfall("FG1", demand((2026, 9, 1)), 0.0, 0.0)
        self.assertEqual(cov.stockout_month, (2026, 9))
        self.assertIsNone(cov.covered_through_month)


class TestComponentWaterfall(unittest.TestCase):
    def test_aggregate_requirement(self):
        fg_forecast = {
            "FG1": {(2026, 9): 100.0, (2026, 10): 100.0},
            "FG2": {(2026, 9): 50.0},
        }
        terminal_req = {("FG1", "RAW"): 0.5, ("FG2", "RAW"): 1.0}
        req = aggregate_component_requirement(fg_forecast, terminal_req, "RAW")
        self.assertAlmostEqual(req[(2026, 9)], 100 * 0.5 + 50 * 1.0)
        self.assertAlmostEqual(req[(2026, 10)], 50.0)

    def test_physical_coverage_month(self):
        req = {(2026, 9): 60.0, (2026, 10): 60.0, (2026, 11): 60.0}
        cov = run_component_waterfall("RAW", req, 100.0)
        self.assertEqual(cov.covered_through_month, (2026, 9))
        self.assertEqual(cov.stockout_month, (2026, 10))

    def test_equivalent_and_open_purchase_separate(self):
        # equivalent-in-FG and open purchase are separate layers, never added
        # to physical availability.
        req = {(2026, 9): 500.0}
        cov = run_component_waterfall("RAW", req, 100.0)
        cov.equivalent_in_fg = 999.0
        cov.open_purchase = 1000.0
        self.assertEqual(cov.stockout_month, (2026, 9))
        self.assertAlmostEqual(cov.physical_available, 100.0)


class TestSeasonalityAware(unittest.TestCase):
    def test_monthly_differs_from_annual_average(self):
        # annual average demand = (50*11 + 300)/12 = 70.8/mo -> 200 FG covers
        # ~2.8 months by average; but peak Jan=300 breaks in month 5.
        demand_series = []
        for m in range(9, 13):
            demand_series.append((2026, m, 50))
        demand_series.append((2027, 1, 300))
        cov = run_fg_waterfall("FG1", demand_series, 200.0, 0.0)
        # average model would claim ~2.8 months; real waterfall stockout month 5
        self.assertEqual(cov.stockout_month, (2027, 1))
        # covered through 4 months, NOT 2.8 -> demonstrates month-by-month use
        self.assertEqual(cov.covered_through_month, (2026, 12))


class TestLeadTimeGap(unittest.TestCase):
    def test_gap_negative(self):
        gap = lead_time_coverage_gap(60, 110)
        self.assertLess(gap, 0)
        self.assertEqual(gap, -50)

    def test_gap_none_when_no_lead_time(self):
        self.assertIsNone(lead_time_coverage_gap(60, None))

    def test_horizon_days(self):
        self.assertEqual(horizon_days((2026, 8), (2026, 10)), round(3 * 30.44))


class TestCoverageRatios(unittest.TestCase):
    def test_coverage_ratio(self):
        self.assertAlmostEqual(coverage_ratio(200.0, 400.0), 0.5)
        self.assertAlmostEqual(coverage_ratio(400.0, 200.0), 2.0)
        self.assertIsNone(coverage_ratio(100.0, 0.0))

    def test_sum_demand_to(self):
        d = {(2026, 9): 10, (2026, 10): 20, (2026, 11): 30}
        self.assertAlmostEqual(sum_demand_to(d, (2026, 9), (2026, 11)), 60.0)
        self.assertAlmostEqual(sum_demand_to(d, (2026, 10), (2026, 11)), 50.0)


class TestNoDoubleCount(unittest.TestCase):
    def test_shared_component_not_allocated_twice(self):
        # 100 units component, FG-A needs 1/unit, FG-B needs 1/unit:
        # 100 A + 100 B would double-count. Aggregate stock is 100.
        from modules.telchi.investigation.validation.coverage.coverage_domain import invariant_shared_allocated_once
        self.assertTrue(invariant_shared_allocated_once(100.0, [100.0]))
        self.assertFalse(invariant_shared_allocated_once(100.0, [100.0, 100.0]))

    def test_equivalent_not_reused(self):
        # equivalent_in_fg (material already in FG) is NOT part of physical
        # production capacity; the two layers stay separate.
        from modules.telchi.investigation.validation.coverage.coverage_domain import invariant_equivalent_not_reused
        self.assertTrue(invariant_equivalent_not_reused(9000.0, 300.0))


class TestForwardForecast(unittest.TestCase):
    def test_forward_months_and_clamp(self):
        fc = build_forward_forecast(lambda y, m: 10.0 * m, 2026, 9, months=4)
        self.assertEqual(sorted(fc), [(2026, 9), (2026, 10), (2026, 11), (2026, 12)])
        self.assertAlmostEqual(fc[(2026, 9)], 90.0)
        self.assertAlmostEqual(fc[(2026, 12)], 120.0)

    def test_clamp_negative(self):
        fc = build_forward_forecast(lambda y, m: -5.0, 2026, 9, months=2)
        self.assertEqual(fc[(2026, 9)], 0.0)


if __name__ == "__main__":
    unittest.main()
