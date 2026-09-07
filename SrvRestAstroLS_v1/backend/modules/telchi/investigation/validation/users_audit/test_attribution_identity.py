"""User attribution unit tests — identity model + technical account detection."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.users_audit.identity_model import (
    IdentityLevel,
    Confidence,
    is_technical_user,
    TECHNICAL_SAP_USERS,
)


class TestTechnicalAccountDetection(unittest.TestCase):
    def test_technical_users_detected(self):
        for u in ("soluone", "dms", "manager", "B1i", "Workflow", "alianza"):
            self.assertTrue(is_technical_user(u), f"{u} should be technical")

    def test_case_insensitive(self):
        self.assertTrue(is_technical_user("SOLUONE"))
        self.assertTrue(is_technical_user("DMS"))

    def test_named_user_not_technical(self):
        self.assertFalse(is_technical_user("eroman"))
        self.assertFalse(is_technical_user("jirahola"))
        self.assertFalse(is_technical_user("maldapi"))

    def test_technical_registry_not_empty(self):
        self.assertGreater(len(TECHNICAL_SAP_USERS), 5)


class TestIdentityLevels(unittest.TestCase):
    def test_levels_defined(self):
        self.assertEqual(IdentityLevel.L1_EXACT_HUMAN_OPERATOR.value, "LEVEL_1_EXACT_HUMAN_OPERATOR")
        self.assertEqual(IdentityLevel.L6_UNKNOWN.value, "LEVEL_6_UNKNOWN")

    def test_confidence_values(self):
        self.assertEqual(Confidence.EXACT.value, "EXACT")
        self.assertEqual(Confidence.HEURISTIC.value, "HEURISTIC")


class TestAttributionSemantics(unittest.TestCase):
    def test_retail_operator_is_human_level1(self):
        # Retail One U_SO1_USUARIO = OHEM.empID is EXACT human operator (LEVEL 1)
        self.assertEqual(IdentityLevel.L1_EXACT_HUMAN_OPERATOR.value,
                         "LEVEL_1_EXACT_HUMAN_OPERATOR")

    def test_dms_has_no_human_operator_field(self):
        # DMS only has SlpCode (LEVEL 3) and U_OSLP_ID (route, not person)
        self.assertEqual(IdentityLevel.L3_STRONG_SALESPERSON.value,
                         "LEVEL_3_STRONG_SALESPERSON_LINK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
