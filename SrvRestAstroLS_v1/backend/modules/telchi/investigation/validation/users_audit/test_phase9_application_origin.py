"""PHASE 9 unit tests — application origin classifier (§21 fixtures).

Fixtures: SAP_DIRECT exact, DMS exact, RETAIL_ONE exact, integration,
heuristic, conflicting signals, UNKNOWN.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.users_audit.application_origin import (
    classify_origin,
    Origin,
    Confidence,
)


class TestExactMarkers(unittest.TestCase):
    def test_sap_direct_exact(self):
        c = classify_origin("SAP", "N")
        self.assertEqual(c.application_origin, Origin.SAP_DIRECT)
        self.assertEqual(c.confidence, Confidence.EXACT)

    def test_retail_one_exact(self):
        c = classify_origin("SAP", "Y")
        self.assertEqual(c.application_origin, Origin.RETAIL_ONE)
        self.assertEqual(c.confidence, Confidence.EXACT)

    def test_dms_exact(self):
        c = classify_origin("DMS", "N")
        self.assertEqual(c.application_origin, Origin.DMS)
        self.assertEqual(c.confidence, Confidence.EXACT)

    def test_dms_exact_overrides_retail(self):
        c = classify_origin("DMS", "Y")
        self.assertEqual(c.application_origin, Origin.DMS)


class TestHeuristicFallbacks(unittest.TestCase):
    def test_series_name_dms_strong(self):
        c = classify_origin(None, None, series_name="DMS24-01")
        self.assertEqual(c.application_origin, Origin.DMS)
        self.assertEqual(c.confidence, Confidence.STRONG)

    def test_technical_user_dms_heuristic(self):
        c = classify_origin(None, None, user_code="dms")
        self.assertEqual(c.application_origin, Origin.DMS)
        self.assertEqual(c.confidence, Confidence.HEURISTIC)

    def test_technical_user_soluone_heuristic(self):
        c = classify_origin(None, None, user_code="soluone")
        self.assertEqual(c.application_origin, Origin.RETAIL_ONE)
        self.assertEqual(c.confidence, Confidence.HEURISTIC)

    def test_technical_user_alianza_integration(self):
        c = classify_origin(None, None, user_code="alianza")
        self.assertEqual(c.application_origin, Origin.INTEGRATION)


class TestUnknownAndConflicts(unittest.TestCase):
    def test_unknown_no_signals(self):
        c = classify_origin(None, None)
        self.assertEqual(c.application_origin, Origin.UNKNOWN)
        self.assertEqual(c.confidence, Confidence.UNKNOWN)

    def test_conflicting_series_vs_marker(self):
        # explicit marker wins over series heuristic
        c = classify_origin("SAP", "Y", series_name="DMS24-01")
        self.assertEqual(c.application_origin, Origin.RETAIL_ONE)
        self.assertEqual(c.confidence, Confidence.EXACT)

    def test_heuristic_never_exact(self):
        c = classify_origin(None, None, user_code="dms")
        self.assertNotEqual(c.confidence, Confidence.EXACT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
