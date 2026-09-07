"""Unit tests for the purchase lead time domain (pure, no HANA)."""
from __future__ import annotations

import unittest
from datetime import date

from modules.telchi.investigation.validation.lead_time.lead_time_domain import (
    FLAG_NO_HISTORY,
    LeadTimeEvent,
    ReceiptEvent,
    STATUS_FULL,
    STATUS_OPEN,
    STATUS_PARTIAL,
    classify_procurement_mode,
    invariant_first_le_full,
    invariant_negative_controlled,
    sample_confidence,
    summarize,
)


def ev(order_days_ago: int, receipts):
    return LeadTimeEvent(
        po_entry=1, po_line=0, item_code="X", ordered_qty=100.0,
        order_date=date(2026, 8, 1), card_code="PL1", card_name="S",
        tipo_compra="LF", doc_cur="BS", doc_status="C",
        receipts=receipts)


def rec(day: int, qty: float):
    return ReceiptEvent(rec_entry=1, rec_line=0, rec_qty=qty,
                        rec_date=date(2026, 8, day), rec_whs="LAB-M1")


class TestFirstAndFull(unittest.TestCase):
    def test_single_full_receipt(self):
        e = ev(0, [rec(10, 100.0)])
        self.assertEqual(e.first_lead_days, 9)
        self.assertEqual(e.full_lead_days, 9)
        self.assertEqual(e.status, STATUS_FULL)

    def test_partial_then_full(self):
        e = ev(0, [rec(5, 40.0), rec(12, 60.0)])
        self.assertEqual(e.first_lead_days, 4)
        self.assertEqual(e.full_lead_days, 11)  # full on day 12
        self.assertEqual(e.status, STATUS_FULL)

    def test_partial_never_full(self):
        e = ev(0, [rec(5, 40.0)])
        self.assertEqual(e.first_lead_days, 4)
        self.assertIsNone(e.full_lead_days)
        self.assertEqual(e.status, STATUS_PARTIAL)

    def test_open_no_receipt(self):
        e = LeadTimeEvent(1, 0, "X", 100.0, date(2026, 8, 1), "PL1", "S", "LF", "BS", "O", [])
        self.assertEqual(e.status, STATUS_OPEN)
        self.assertIsNone(e.first_lead_days)

    def test_first_le_full(self):
        e = ev(0, [rec(5, 40.0), rec(12, 60.0)])
        self.assertTrue(invariant_first_le_full(e.first_lead_days, e.full_lead_days))


class TestStats(unittest.TestCase):
    def test_summarize(self):
        s = summarize([10, 20, 30, 40, 50])
        self.assertEqual(s["n"], 5)
        self.assertEqual(s["median"], 30)
        self.assertEqual(s["p90"], 50)
        self.assertEqual(s["min"], 10)
        self.assertEqual(s["max"], 50)

    def test_summarize_empty(self):
        self.assertEqual(summarize([]), {"n": 0})

    def test_sample_confidence(self):
        self.assertEqual(sample_confidence(0), FLAG_NO_HISTORY)
        self.assertEqual(sample_confidence(1), "VERY_LOW")
        self.assertEqual(sample_confidence(3), "LOW")
        self.assertEqual(sample_confidence(10), "USABLE")


class TestProcurementMode(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(classify_procurement_mode(True, False), "PURCHASED")
        self.assertEqual(classify_procurement_mode(False, True), "PRODUCED")
        self.assertEqual(classify_procurement_mode(True, True), "MIXED")
        self.assertEqual(classify_procurement_mode(False, False), "NO_PURCHASE_HISTORY")


if __name__ == "__main__":
    unittest.main()