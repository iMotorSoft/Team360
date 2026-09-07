"""Production output traceability domain unit tests (pure logic)."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.production.output_traceability_domain import (
    classify_output,
    OrderOutputSummary,
    build_order_summary,
)


class TestOutputClassification(unittest.TestCase):
    def test_exact_planned(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("100"), 1, 1, None),
            "EXACT_PLANNED_OUTPUT")

    def test_partial(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("80"), 1, 1, None),
            "PARTIAL_OUTPUT")

    def test_over_planned(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("120"), 1, 1, None),
            "OVER_PLANNED_OUTPUT")

    def test_zero_output(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("0"), 0, 0, Decimal("0")),
            "ZERO_OUTPUT")

    def test_consumption_without_output(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("0"), 0, 0, Decimal("50")),
            "CONSUMPTION_WITHOUT_OUTPUT")

    def test_multiple_receipts_exact(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("100"), 3, 1, None),
            "MULTIPLE_RECEIPTS_EXACT_PLANNED_OUTPUT")

    def test_multi_warehouse_partial(self):
        self.assertEqual(
            classify_output(Decimal("100"), Decimal("70"), 2, 2, None),
            "MULTIPLE_RECEIPTS_PARTIAL_OUTPUT")


class TestOrderSummary(unittest.TestCase):
    def _order(self):
        return (1, 1001, "P1", Decimal("100"), Decimal("100"))

    def test_no_receipts(self):
        s = build_order_summary(self._order(), [], {})
        self.assertEqual(s.net_actual_output_qty, Decimal("0"))
        self.assertEqual(s.classification, "ZERO_OUTPUT")

    def test_single_receipt(self):
        rows = [(50, 0, 1, "REF1", "P1", Decimal("100"), "SAA-T1", None, "L1", None, 5001, None)]
        s = build_order_summary(self._order(), rows, {})
        self.assertEqual(s.net_actual_output_qty, Decimal("100"))
        self.assertEqual(s.receipt_doc_count, 1)
        self.assertEqual(s.warehouses, ["SAA-T1"])
        self.assertEqual(s.batches, ["L1"])

    def test_multiple_receipts_preserved(self):
        rows = [
            (50, 0, 1, "REF1", "P1", Decimal("30"), "SAA-T1", None, "L1", None, 5001, None),
            (51, 0, 1, "REF2", "P1", Decimal("70"), "SAA-T1", None, "L1", None, 5002, None),
        ]
        s = build_order_summary(self._order(), rows, {})
        self.assertEqual(s.net_actual_output_qty, Decimal("100"))
        self.assertEqual(s.receipt_doc_count, 2)
        self.assertEqual(s.classification, "MULTIPLE_RECEIPTS_EXACT_PLANNED_OUTPUT")

    def test_multi_warehouse(self):
        rows = [
            (50, 0, 1, "REF1", "P1", Decimal("30"), "SAA-T1", None, None, None, 5001, None),
            (51, 0, 1, "REF2", "P1", Decimal("40"), "LAB-P1", None, None, None, 5002, None),
        ]
        s = build_order_summary(self._order(), rows, {})
        self.assertEqual(s.warehouse_count, 2)
        self.assertEqual(s.warehouses, ["LAB-P1", "SAA-T1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)