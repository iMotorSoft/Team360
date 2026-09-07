"""Recipe/BOM domain unit tests (pure logic, no DB).

Covers: expected formula, signature order-independence, drift classification,
issue method, compare expected/actual.
"""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.production.recipe_bom_domain import (
    RecipeOrderSnapshot,
    expected_qty,
    compare_expected_actual,
)


class TestExpectedFormula(unittest.TestCase):
    def test_exact_integer_factor(self):
        # L01945: num/den factor, planned 50 -> 1500
        self.assertEqual(expected_qty(30, 1, 50), Decimal("1500"))

    def test_decimal_factor(self):
        # num=0.001029 den=0.001 planned=1000 -> 1029
        self.assertEqual(expected_qty(Decimal("0.001029"), Decimal("0.001"), 1000),
                         Decimal("1029"))

    def test_fraction(self):
        # num=1 den=275 planned=500 -> 1.818182
        self.assertAlmostEqual(float(expected_qty(1, 275, 500)), 1.818182, places=5)

    def test_zero_den_safe(self):
        self.assertEqual(expected_qty(5, 0, 10), Decimal("50"))

    def test_zero_planned(self):
        self.assertEqual(expected_qty(3, 1, 0), Decimal("0"))


def _snap(order=1, line=0, comp="C1", num=1, den=1, planned=10, method="M", whs="W"):
    return RecipeOrderSnapshot(
        order_docentry=order, order_docnum=1000+order, parent_item="P",
        line_num=line, component_item=comp,
        base_qty_num=Decimal(str(num)), base_qty_den=Decimal(str(den)),
        base_qty=Decimal(str(num))/Decimal(str(den)), expected_qty=expected_qty(num, den, planned),
        issued_qty=None, issue_method=method, warehouse=whs, uom=None,
    )


class TestRecipeSignature(unittest.TestCase):
    def test_order_independent(self):
        a = _snap(1, 0, "C1", 1, 1, 10)
        b = _snap(2, 5, "C1", 1, 1, 10)
        self.assertEqual(a.recipe_signature, b.recipe_signature)

    def test_component_changes_signature(self):
        a = _snap(1, 0, "C1", 1, 1, 10)
        b = _snap(1, 0, "C2", 1, 1, 10)
        self.assertNotEqual(a.recipe_signature, b.recipe_signature)

    def test_qty_changes_signature(self):
        a = _snap(1, 0, "C1", 1, 1, 10)
        b = _snap(1, 0, "C1", 2, 1, 10)
        self.assertNotEqual(a.recipe_signature, b.recipe_signature)


class TestCompareExpectedActual(unittest.TestCase):
    def test_exact_match(self):
        s = [_snap(1, 0, "C1", 1, 1, 10)]
        cons = {(0, "C1"): Decimal("10")}
        r = compare_expected_actual(s, cons)[0]
        self.assertEqual(r["status"], "EXACT")

    def test_not_consumed(self):
        s = [_snap(1, 0, "C1", 1, 1, 10)]
        r = compare_expected_actual(s, {})[0]
        self.assertEqual(r["status"], "EXPECTED_NOT_CONSUMED")

    def test_over_consumption(self):
        s = [_snap(1, 0, "C1", 1, 1, 10)]
        cons = {(0, "C1"): Decimal("12")}
        r = compare_expected_actual(s, cons)[0]
        self.assertEqual(r["status"], "OVER_CONSUMPTION")

    def test_under_consumption(self):
        s = [_snap(1, 0, "C1", 1, 1, 10)]
        cons = {(0, "C1"): Decimal("8")}
        r = compare_expected_actual(s, cons)[0]
        self.assertEqual(r["status"], "UNDER_CONSUMPTION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
