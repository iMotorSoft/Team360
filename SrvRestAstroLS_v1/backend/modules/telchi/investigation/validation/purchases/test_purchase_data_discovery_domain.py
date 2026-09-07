"""Unit tests for the purchase data discovery domain (pure, no HANA)."""
from __future__ import annotations

import unittest
from datetime import date

from modules.telchi.investigation.validation.purchases.purchase_domain import (
    OpenPurchasePosition,
    PurchaseHeader,
    PurchaseLine,
    classify_import_supplier,
    classify_tipo_compra,
    days_between,
    invariant_chain_linked,
    invariant_open_qty_non_negative,
    invariant_receipt_after_invoice,
    lead_time_buckets,
    percentiles,
)


class TestClassifyTipoCompra(unittest.TestCase):
    def test_lf_local_general(self):
        self.assertEqual(classify_tipo_compra("LF"), "LOCAL_GENERAL")

    def test_lp_local_packaging(self):
        self.assertEqual(classify_tipo_compra("LP"), "LOCAL_PACKAGING")

    def test_imp_import(self):
        self.assertEqual(classify_tipo_compra("IMP"), "IMPORT_OR_LOGISTICS")

    def test_serv_and_saa(self):
        self.assertEqual(classify_tipo_compra("SERV"), "SERVICE")
        self.assertEqual(classify_tipo_compra("SAA"), "INTERNAL")

    def test_unknown_and_none(self):
        self.assertEqual(classify_tipo_compra("XYZ"), "UNKNOWN")
        self.assertEqual(classify_tipo_compra(None), "UNKNOWN")
        self.assertEqual(classify_tipo_compra(""), "UNKNOWN")

    def test_case_insensitive(self):
        self.assertEqual(classify_tipo_compra("imp"), "IMPORT_OR_LOGISTICS")


class TestImportSupplier(unittest.TestCase):
    def test_imp_tipo_is_evidence(self):
        self.assertEqual(classify_import_supplier("PL000001", "IMP"), "IMPORT_EVIDENCE")

    def test_foreign_prefix(self):
        self.assertEqual(classify_import_supplier("PE000002", "LF"), "FOREIGN_SUPPLIER_CODE")

    def test_local(self):
        self.assertEqual(classify_import_supplier("PL000007", "LF"), "LOCAL_EVIDENCE")


class TestHeaderSemantics(unittest.TestCase):
    def test_active_vs_canceled(self):
        h = PurchaseHeader(1, 100, "N", "C", date(2026, 8, 1), "PL1", "S1", "BS", 100.0, "LF")
        self.assertTrue(h.is_active)
        self.assertFalse(h.is_open)
        c = PurchaseHeader(2, 101, "Y", "C", None, "PL1", "S1", "BS", 0.0, "LF")
        self.assertFalse(c.is_active)

    def test_open_status(self):
        h = PurchaseHeader(3, 102, "N", "O", date(2026, 8, 1), "PL1", "S1", "USD", 100.0, "IMP")
        self.assertTrue(h.is_open)


class TestLineSemantics(unittest.TestCase):
    def test_fully_open(self):
        ln = PurchaseLine(1, 0, "L0001", 1000.0, 1000.0, 22, "262001", 0, "SAA-M1")
        self.assertTrue(ln.is_fully_open)
        self.assertFalse(ln.is_closed)

    def test_closed(self):
        ln = PurchaseLine(1, 0, "L0001", 1000.0, 0.0, 22, "262001", 0, "SAA-M1")
        self.assertTrue(ln.is_closed)

    def test_open_amount_clamps(self):
        ln = PurchaseLine(1, 0, "L0001", 1000.0, -5.0, 22, "262001", 0, "SAA-M1")
        self.assertEqual(ln.open_amount, 0.0)


class TestTiming(unittest.TestCase):
    def test_days_between(self):
        self.assertEqual(days_between(date(2026, 8, 1), date(2026, 8, 15)), 14)
        self.assertEqual(days_between(date(2026, 8, 15), date(2026, 8, 1)), -14)
        self.assertIsNone(days_between(None, date(2026, 8, 1)))

    def test_buckets(self):
        days = [-5, 0, 3, 10, 40, 70, 100, 200]
        buckets = lead_time_buckets(days)
        self.assertEqual(buckets["NEGATIVE"], 1)
        self.assertEqual(buckets["0"], 1)
        self.assertEqual(buckets["7"], 1)
        self.assertEqual(buckets["30"], 1)
        self.assertEqual(buckets["60"], 1)
        self.assertEqual(buckets["90"], 1)
        self.assertEqual(buckets["180"], 1)
        self.assertEqual(buckets["181+"], 1)

    def test_percentiles(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        p = percentiles(vals)
        self.assertEqual(p[0.5], 5)
        self.assertEqual(p[0.9], 9)

    def test_percentiles_empty_and_negative_filtered(self):
        self.assertEqual(percentiles([]), {})
        self.assertEqual(percentiles([-10, -5]), {})


class TestInvariants(unittest.TestCase):
    def test_chain_linked(self):
        ok, flag = invariant_chain_linked(100, 100)
        self.assertTrue(ok)
        self.assertEqual(flag, "CHAIN_LINKED")
        ok, flag = invariant_chain_linked(100, 99)
        self.assertFalse(ok)
        self.assertEqual(flag, "CHAIN_LINK_MISSING")

    def test_open_qty_non_negative(self):
        ok, flag = invariant_open_qty_non_negative(0)
        self.assertTrue(ok)
        ok, flag = invariant_open_qty_non_negative(3)
        self.assertFalse(ok)
        self.assertEqual(flag, "OPEN_QTY_NEGATIVE_FOUND")

    def test_receipt_after_invoice(self):
        ok, flag = invariant_receipt_after_invoice(0, 100)
        self.assertTrue(ok)
        ok, flag = invariant_receipt_after_invoice(32, 18977, tolerance_pct=0.5)
        self.assertTrue(ok)  # 0.17% < 0.5% -> documented anomaly, invariant holds
        ok, flag = invariant_receipt_after_invoice(10, 100, tolerance_pct=0.5)
        self.assertFalse(ok)
        self.assertEqual(flag, "RECEIPT_BEFORE_INVOICE_ABOVE_TOLERANCE")


class TestOpenPosition(unittest.TestCase):
    def test_position_build(self):
        pos = OpenPurchasePosition(
            25906, 262001570, date(2026, 5, 15), "PE000002",
            "HAINAN ZHONGXIN", "USD", 128945.0, "IMP")
        pos.lines.append(PurchaseLine(25906, 0, "L01010", 108000.0, 108000.0,
                                      22, "262001570", 0, "SAA-M1"))
        self.assertEqual(pos.import_class, "IMPORT_OR_LOGISTICS")
        self.assertEqual(pos.total_open_qty(), 108000.0)
        d = pos.to_dict()
        self.assertEqual(d["import_class"], "IMPORT_OR_LOGISTICS")
        self.assertEqual(d["lines"][0]["openqty"], 108000.0)


if __name__ == "__main__":
    unittest.main()