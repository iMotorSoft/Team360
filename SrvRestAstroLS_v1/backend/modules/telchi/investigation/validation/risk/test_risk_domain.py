"""Unit tests for the purchase risk engine domain (pure, no HANA).

P0 cases: BUY_NOW / BUY_SOON / WATCH / SAFE / DO_NOT_BUY / EXCESS_STOCK,
produced components, no lead time, open order covering shortfall, import and
supplier flags, safety buffer heuristic, latest-safe-order-month arithmetic.
"""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.coverage.coverage_domain import FLAG_IN_TRANSIT_UNRESOLVED, month_span
from modules.telchi.investigation.validation.risk.risk_domain import (
    DEC_BUY_NOW, DEC_BUY_SOON, DEC_DO_NOT_BUY, DEC_EXCESS_STOCK, DEC_SAFE,
    DEC_WATCH, FLAG_IMPORT_DELAY, FLAG_PRODUCTION_BLOCKED, FLAG_SUPPLIER,
    IMPORT_CLASS, MaterialRiskInput, PROCUREMENT_MIXED, PROCUREMENT_PRODUCED,
    PROCUREMENT_PURCHASED, classify_material, latest_safe_order_month,
    safety_buffer_days,
)

SNAP = (2026, 8)


def base_input(**kw) -> MaterialRiskInput:
    defaults = dict(
        component="RAW_A", physical_available=100.0, equivalent_in_fg=0.0,
        open_purchase=0.0, total_required=1000.0, stockout_month=None,
        covered_through_month=(2027, 8), lead_time_p90=30,
        procurement_mode=PROCUREMENT_PURCHASED, import_class="LOCAL_GENERAL",
        supplier_confidence="USABLE", is_shared=False, is_packaging=False,
        forecast_uncertain=False, declining_or_discontinued=False,
    )
    defaults.update(kw)
    return MaterialRiskInput(**defaults)


class TestSafetyBuffer(unittest.TestCase):
    def test_base(self):
        self.assertEqual(safety_buffer_days(False, "USABLE", False), 7)

    def test_low_sample_adds(self):
        self.assertEqual(safety_buffer_days(False, "LOW", False), 21)

    def test_shared_and_uncertain(self):
        self.assertEqual(safety_buffer_days(True, "USABLE", True), 21)


class TestLatestSafeOrder(unittest.TestCase):
    def test_shift_back(self):
        # stockout (2026,12), lead 30d + buffer 7d = 37d -> ceil(37/30.44)=2 months
        lso = latest_safe_order_month((2026, 12), 30, 7)
        self.assertEqual(lso, (2026, 10))

    def test_short_lead(self):
        # 1 day total -> ceil(1/30.44)=1 month back
        self.assertEqual(latest_safe_order_month((2027, 1), 0, 1), (2026, 12))


class TestDecisions(unittest.TestCase):
    def test_safe_no_stockout(self):
        r = classify_material(base_input(total_required=50.0), SNAP)
        self.assertEqual(r.decision, DEC_SAFE)

    def test_do_not_buy_equivalent_covers(self):
        r = classify_material(base_input(equivalent_in_fg=2000.0, total_required=1000.0), SNAP)
        self.assertEqual(r.decision, DEC_DO_NOT_BUY)

    def test_partial_equivalent_offsets_but_not_covers(self):
        # equivalent 500 + physical 100 = 600 < 1000 -> still a shortfall
        r = classify_material(base_input(equivalent_in_fg=500.0, total_required=1000.0,
                                         stockout_month=(2026, 10)), SNAP)
        self.assertEqual(r.decision, DEC_BUY_NOW)

    def test_excess_declining(self):
        r = classify_material(base_input(declining_or_discontinued=True, total_required=50.0), SNAP)
        self.assertEqual(r.decision, DEC_EXCESS_STOCK)

    def test_buy_now_expired(self):
        # stockout (2026,10), lead 30 + buffer 7 = 37d -> ceil=2 months back -> lso (2026,8)
        r = classify_material(base_input(stockout_month=(2026, 10)), SNAP)
        self.assertEqual(r.decision, DEC_BUY_NOW)
        self.assertEqual(r.latest_safe_order_month, (2026, 8))

    def test_buy_soon_window(self):
        # stockout (2026,12) -> lso (2026,10) span=2 -> BUY_SOON
        r = classify_material(base_input(stockout_month=(2026, 12)), SNAP)
        self.assertEqual(r.decision, DEC_BUY_SOON)
        self.assertEqual(r.latest_safe_order_month, (2026, 10))

    def test_watch_future(self):
        r = classify_material(base_input(stockout_month=(2027, 6)), SNAP)
        self.assertEqual(r.decision, DEC_WATCH)

    def test_watch_no_lead_time(self):
        r = classify_material(base_input(stockout_month=(2026, 11), lead_time_p90=None), SNAP)
        self.assertEqual(r.decision, DEC_WATCH)
        self.assertEqual(r.confidence, "LOW")

    def test_open_order_covers_shortfall_is_safe(self):
        r = classify_material(base_input(stockout_month=(2026, 12), open_purchase=1000.0,
                                         total_required=1000.0), SNAP)
        self.assertEqual(r.decision, DEC_SAFE)
        self.assertIn(FLAG_IN_TRANSIT_UNRESOLVED, r.flags)

    def test_open_partial_flags_transit(self):
        # open 300 + physical 100 = 400 < 1000 -> shortfall, but an order is open
        r = classify_material(base_input(stockout_month=(2026, 12), open_purchase=300.0), SNAP)
        self.assertEqual(r.decision, DEC_BUY_SOON)
        self.assertIn(FLAG_IN_TRANSIT_UNRESOLVED, r.flags)

    def test_produced_safe(self):
        r = classify_material(base_input(procurement_mode=PROCUREMENT_PRODUCED), SNAP)
        self.assertEqual(r.decision, DEC_SAFE)

    def test_mixed_treated_as_purchased(self):
        r = classify_material(base_input(procurement_mode=PROCUREMENT_MIXED,
                                         stockout_month=(2026, 10)), SNAP)
        self.assertEqual(r.decision, DEC_BUY_NOW)


class TestFlags(unittest.TestCase):
    def test_import_flag(self):
        r = classify_material(base_input(import_class=IMPORT_CLASS, stockout_month=(2026, 10)), SNAP)
        self.assertIn(FLAG_IMPORT_DELAY, r.flags)

    def test_supplier_flag_and_confidence(self):
        r = classify_material(base_input(supplier_confidence="LOW", stockout_month=(2026, 10)), SNAP)
        self.assertIn(FLAG_SUPPLIER, r.flags)
        self.assertEqual(r.confidence, "LOW")

    def test_production_blocked_packaging(self):
        r = classify_material(base_input(is_packaging=True, stockout_month=(2026, 10)), SNAP)
        self.assertIn(FLAG_PRODUCTION_BLOCKED, r.flags)

    def test_no_import_flag_for_local(self):
        r = classify_material(base_input(stockout_month=(2026, 10)), SNAP)
        self.assertNotIn(FLAG_IMPORT_DELAY, r.flags)


if __name__ == "__main__":
    unittest.main()
