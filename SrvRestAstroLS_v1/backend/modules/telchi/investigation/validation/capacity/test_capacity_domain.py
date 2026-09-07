"""Unit tests for the max-producible-by-component domain (pure, no HANA)."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.capacity.capacity_domain import (
    FgCapacity,
    RAW_MATERIAL_WAREHOUSES,
    available_for_production,
    build_capacity,
    component_capacity,
    expand_requirement_terminal,
    invariant_limiting_is_min,
    requirement_per_fg,
    shared_component_map,
)


class TestAvailability(unittest.TestCase):
    def test_raw_warehouse_only(self):
        rows = [("RAW_A", "LAB-M1", 100.0, 10.0), ("RAW_A", "2A-SAL", 999.0, 0.0)]
        avail = available_for_production(rows)
        self.assertAlmostEqual(avail["RAW_A"], 90.0)

    def test_committed_subtracted(self):
        rows = [("RAW_A", "LAB-M1", 100.0, 30.0)]
        self.assertAlmostEqual(available_for_production(rows)["RAW_A"], 70.0)

    def test_not_in_raw_role_excluded(self):
        rows = [("RAW_A", "LAB-T1", 100.0, 0.0)]
        self.assertEqual(available_for_production(rows), {})


class TestRequirement(unittest.TestCase):
    def test_ratio(self):
        req = requirement_per_fg({("FG1", "RAW_A"): 50.0}, {"FG1": 100.0})
        self.assertAlmostEqual(req[("FG1", "RAW_A")], 0.5)

    def test_zero_produced_skipped(self):
        req = requirement_per_fg({("FG1", "RAW_A"): 50.0}, {"FG1": 0.0})
        self.assertEqual(req, {})


class TestCapacity(unittest.TestCase):
    def test_component_capacity(self):
        self.assertAlmostEqual(component_capacity(100.0, 0.5), 200.0)

    def test_infinite_when_no_requirement(self):
        self.assertEqual(component_capacity(100.0, 0.0), float("inf"))


class TestTerminalExpansion(unittest.TestCase):
    def test_semi_expanded(self):
        direct = {("FG1", "SEMI"): 1.0, ("SEMI", "RAW_X"): 0.5, ("SEMI", "RAW_Y"): 0.2}
        term = expand_requirement_terminal("FG1", direct, {"SEMI"})
        self.assertNotIn("SEMI", term)
        self.assertAlmostEqual(term["RAW_X"], 0.5)
        self.assertAlmostEqual(term["RAW_Y"], 0.2)

    def test_no_double_count(self):
        direct = {("FG1", "SEMI"): 2.0, ("SEMI", "RAW_X"): 3.0}
        term = expand_requirement_terminal("FG1", direct, {"SEMI"})
        self.assertNotIn("SEMI", term)
        self.assertAlmostEqual(term["RAW_X"], 6.0)

    def test_non_produced_kept(self):
        direct = {("FG1", "RAW_A"): 0.5}
        term = expand_requirement_terminal("FG1", direct, set())
        self.assertAlmostEqual(term["RAW_A"], 0.5)


class TestFgCapacity(unittest.TestCase):
    def setUp(self):
        self.direct = {("FG1", "RAW_A"): 0.5, ("FG1", "RAW_B"): 2.0,
                       ("FG2", "RAW_A"): 1.0}
        self.avail = {"RAW_A": 100.0, "RAW_B": 20.0}

    def test_limiting_component(self):
        cap = build_capacity("FG1", self.direct, self.avail, set())
        # RAW_A: 100/0.5=200 ; RAW_B: 20/2=10 -> limiting RAW_B, max=10
        self.assertEqual(cap.limiting_component, "RAW_B")
        self.assertAlmostEqual(cap.immediate_max, 10.0)

    def test_invariant_limiting_is_min(self):
        cap = build_capacity("FG1", self.direct, self.avail, set())
        self.assertTrue(invariant_limiting_is_min(cap))

    def test_shared_component(self):
        smap = shared_component_map(self.direct)
        self.assertEqual(smap["RAW_A"], {"FG1", "FG2"})
        self.assertEqual(smap["RAW_B"], {"FG1"})


if __name__ == "__main__":
    unittest.main()