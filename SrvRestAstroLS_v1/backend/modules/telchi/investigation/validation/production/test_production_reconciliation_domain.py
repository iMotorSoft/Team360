"""Production reconciliation domain unit tests (pure logic)."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.production.production_reconciliation_domain import (
    build_line,
    classify_variance,
    ReconciliationLine,
)


def _line(planned, actual_out, num, den, cons, method="M"):
    order = (1, 1001, "P", Decimal(str(planned)))
    wor1 = (0, "C", Decimal(str(num)), Decimal(str(den)), method)
    return build_line(order, wor1, Decimal(str(actual_out)), Decimal(str(cons)),
                      False, 0)


class TestClassifyVariance(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(classify_variance(Decimal("10"), Decimal("10"), Decimal("0.001")), "EXACT")

    def test_over(self):
        self.assertEqual(classify_variance(Decimal("10"), Decimal("12"), Decimal("0.001")), "OVER")

    def test_under(self):
        self.assertEqual(classify_variance(Decimal("10"), Decimal("8"), Decimal("0.001")), "UNDER")

    def test_expected_zero_both_zero(self):
        self.assertEqual(classify_variance(Decimal("0"), Decimal("0"), Decimal("0.001")),
                         "EXPECTED_ZERO_ACTUAL_ZERO")

    def test_expected_zero_actual_positive(self):
        self.assertEqual(classify_variance(Decimal("0"), Decimal("5"), Decimal("0.001")),
                         "EXPECTED_ZERO_ACTUAL_POSITIVE")

    def test_expected_not_consumed(self):
        self.assertEqual(classify_variance(Decimal("10"), Decimal("0"), Decimal("0.001")),
                         "EXPECTED_NOT_CONSUMED")


class TestNormalizedReconciliation(unittest.TestCase):
    def test_fundamental_example(self):
        # planned=1000, actual=800, ratio=2, consumed=1620
        # expected_plan=2000, expected_normalized=1600
        l = _line(1000, 800, 2, 1, 1620)
        self.assertEqual(l.expected_for_plan, Decimal("2000"))
        self.assertEqual(l.expected_for_actual_output, Decimal("1600"))
        self.assertEqual(l.plan_classification, "UNDER")
        self.assertEqual(l.normalized_classification, "OVER")
        self.assertAlmostEqual(l.normalized_variance_pct, 1.25, places=2)

    def test_partial_output_exact_after_normalization(self):
        # planned expected=200, actual output expected=160, consumed=160
        l = _line(100, 80, 2, 1, 160)
        self.assertEqual(l.plan_classification, "UNDER")
        self.assertEqual(l.normalized_classification, "EXACT")

    def test_over_output_increases_expected(self):
        # planned=100, actual=120, ratio=2 -> expected_norm=240
        l = _line(100, 120, 2, 1, 240)
        self.assertEqual(l.expected_for_actual_output, Decimal("240"))
        self.assertEqual(l.normalized_classification, "EXACT")
        self.assertEqual(l.output_completion_ratio, 1.2)

    def test_zero_output(self):
        l = _line(100, 0, 2, 1, 0)
        self.assertEqual(l.expected_for_actual_output, Decimal("0"))
        self.assertEqual(l.normalized_classification, "EXPECTED_ZERO_ACTUAL_ZERO")

    def test_zero_output_with_consumption(self):
        l = _line(100, 0, 2, 1, 50)
        self.assertEqual(l.normalized_classification, "EXPECTED_ZERO_ACTUAL_POSITIVE")

    def test_decimal_factor(self):
        # num=1 den=275 planned=500 actual=500 consumed=1.8182
        l = _line(500, 500, 1, 275, Decimal("1.818182"))
        self.assertAlmostEqual(float(l.expected_for_plan), 1.818182, places=5)
        self.assertEqual(l.normalized_classification, "EXACT")

    def test_rework_flag(self):
        # parent == component
        order = (1, 1001, "X", Decimal("10"))
        wor1 = (0, "X", Decimal("1"), Decimal("1"), "M")
        l = build_line(order, wor1, Decimal("10"), Decimal("10"), False, 0)
        self.assertTrue(l.is_rework)


if __name__ == "__main__":
    unittest.main(verbosity=2)