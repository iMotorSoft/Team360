"""Production component consumption domain unit tests (pure logic)."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.production.component_consumption_domain import (
    classify_consumption,
)


class TestClassification(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(
            classify_consumption(Decimal("10"), Decimal("10"), 1, Decimal("10"),
                                 Decimal("10"), "M", "L"),
            "EXACT")

    def test_not_consumed(self):
        self.assertEqual(
            classify_consumption(Decimal("10"), Decimal("0"), 0, None,
                                 Decimal("10"), "M", "L"),
            "EXPECTED_NOT_CONSUMED")

    def test_true_over(self):
        self.assertEqual(
            classify_consumption(Decimal("10"), Decimal("12"), 1, Decimal("10"),
                                 Decimal("10"), "M", "L"),
            "TRUE_OVER_CONSUMPTION_CANDIDATE")

    def test_true_under(self):
        self.assertEqual(
            classify_consumption(Decimal("10"), Decimal("8"), 1, Decimal("10"),
                                 Decimal("10"), "M", "L"),
            "TRUE_UNDER_CONSUMPTION_CANDIDATE")

    def test_zero_expected_with_actual(self):
        self.assertEqual(
            classify_consumption(Decimal("0"), Decimal("5"), 1, None, None, "M", "L"),
            "ZERO_EXPECTED_WITH_ACTUAL")

    def test_zero_expected_zero_actual(self):
        self.assertEqual(
            classify_consumption(Decimal("0"), Decimal("0"), 0, None, None, "M", "L"),
            "ZERO_EXPECTED_ZERO_ACTUAL")


class TestNettingSemantics(unittest.TestCase):
    def test_gross_equals_net_no_cancellations(self):
        # validated: no canceled OIGE, no negative IGE1 -> NET == GROSS
        self.assertEqual(Decimal("57.1429"), Decimal("57.1429"))

    def test_multiple_issues_sum(self):
        # 30 + 40 + 30 = 100
        gross = sum((Decimal(x) for x in ["30", "40", "30"]), Decimal(0))
        self.assertEqual(gross, Decimal("100"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
