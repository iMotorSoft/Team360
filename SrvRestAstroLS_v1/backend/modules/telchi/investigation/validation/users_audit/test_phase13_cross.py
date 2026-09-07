"""PHASE 13 unit tests — cross traceability case classification (§23 fixtures)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.users_audit.phase13_cross_traceability import classify_case


def _case(sale=True, cash=0, stock=0, acct=0):
    return {
        "sale": {"doc_entry": 1} if sale else None,
        "cash": [{"x": i} for i in range(cash)],
        "stock": [{"x": i} for i in range(stock)],
        "accounting": [{"x": i} for i in range(acct)],
    }


class TestCrossCaseClassification(unittest.TestCase):
    def test_fully_traced(self):
        self.assertEqual(classify_case(_case(cash=1, stock=1, acct=1)), "FULLY_TRACED")

    def test_sale_cash_accounting(self):
        self.assertEqual(classify_case(_case(cash=1, stock=0, acct=1)),
                         "SALE_CASH_ACCOUNTING_CONFIRMED")

    def test_sale_stock_only(self):
        self.assertEqual(classify_case(_case(cash=0, stock=1, acct=0)),
                         "SALE_STOCK_CONFIRMED")

    def test_sale_cash_only(self):
        self.assertEqual(classify_case(_case(cash=1, stock=0, acct=0)),
                         "SALE_CASH_CONFIRMED")

    def test_sale_only(self):
        self.assertEqual(classify_case(_case(cash=0, stock=0, acct=0)), "SALE_ONLY")

    def test_no_sale_unresolved(self):
        self.assertEqual(classify_case(_case(sale=False)), "UNRESOLVED")

    def test_partial_trace_not_anomalous(self):
        # missing accounting is not "anomalous", it is a partial trace
        self.assertNotEqual(classify_case(_case(cash=1, stock=1, acct=0)), "ANOMALOUS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
