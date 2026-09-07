"""Unit tests for the FG -> material equivalence domain (pure, no HANA)."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.equivalence.equivalence_domain import (
    ComponentRatio,
    EquivalenceLine,
    FgStock,
    build_equivalence,
    classify_equivalence,
    current_bom_ratio,
    expand_terminal,
    global_equivalent_total,
    historical_ratio,
    transfer_conservation,
    uom_compatible,
    LEVEL_CURRENT_BOM,
    LEVEL_HISTORICAL_PRODUCTION,
    LEVEL_UNRESOLVED,
)


class TestRatios(unittest.TestCase):
    def test_historical_ratio(self):
        self.assertAlmostEqual(historical_ratio(50.0, 100.0), 0.5)

    def test_historical_ratio_zero_produced(self):
        self.assertIsNone(historical_ratio(50.0, 0.0))

    def test_current_bom_ratio_batch_normalized(self):
        self.assertAlmostEqual(current_bom_ratio(250.0, 1000.0), 0.25)

    def test_classify(self):
        self.assertEqual(classify_equivalence(True, True), LEVEL_HISTORICAL_PRODUCTION)
        self.assertEqual(classify_equivalence(False, True), LEVEL_CURRENT_BOM)
        self.assertEqual(classify_equivalence(False, False), LEVEL_UNRESOLVED)


class TestEquivalenceBuild(unittest.TestCase):
    def setUp(self):
        self.stocks = [
            FgStock("FG1", "LAB-T1", 100.0, "FCO", "FINISHED_GOOD"),
            FgStock("FG1", "2A-SAL", 50.0, "FCO", "BRANCH"),
            FgStock("FG2", "LAB-T1", 10.0, "FCO", "FINISHED_GOOD"),
        ]
        self.ratios = {
            ("FG1", "RAW_A"): ComponentRatio("FG1", "RAW_A", 0.25, LEVEL_HISTORICAL_PRODUCTION, "KG", "RAW_MATERIAL"),
            ("FG1", "FRASCO"): ComponentRatio("FG1", "FRASCO", 1.0, LEVEL_HISTORICAL_PRODUCTION, "PZA", "PACKAGING"),
            ("FG2", "RAW_B"): ComponentRatio("FG2", "RAW_B", 2.0, LEVEL_HISTORICAL_PRODUCTION, "KG", "RAW_MATERIAL"),
        }
        self.bom = {("FG1", "ETIQUETA"): 1.0, ("FG2", "RAW_B"): 1.5}

    def test_direct_equivalence(self):
        lines = build_equivalence(self.stocks, self.ratios, self.bom)
        total = global_equivalent_total(lines)
        # RAW_A: (100+50)*0.25 = 37.5
        self.assertAlmostEqual(total["RAW_A"], 37.5)
        # FRASCO: (100+50)*1.0 = 150
        self.assertAlmostEqual(total["FRASCO"], 150.0)
        # RAW_B: FG2 uses historical 2.0 (preferred over BOM 1.5) -> 10*2 = 20
        self.assertAlmostEqual(total["RAW_B"], 20.0)
        # ETIQUETA: only via BOM fallback -> 150*1.0
        self.assertAlmostEqual(total["ETIQUETA"], 150.0)

    def test_historical_preferred_over_bom(self):
        lines = build_equivalence(self.stocks, self.ratios, self.bom)
        raw_b = [ln for ln in lines if ln.component == "RAW_B"][0]
        self.assertEqual(raw_b.method, LEVEL_HISTORICAL_PRODUCTION)
        self.assertEqual(raw_b.qty_per_fg, 2.0)

    def test_fg_stock_sums_across_warehouses(self):
        lines = build_equivalence(self.stocks, self.ratios, self.bom)
        frasco_total = sum(ln.equivalent_qty for ln in lines if ln.component == "FRASCO")
        self.assertAlmostEqual(frasco_total, 150.0)  # both warehouses


class TestTerminalExpansion(unittest.TestCase):
    def test_semi_expanded_to_raw(self):
        ratios = {
            ("FG1", "SEMI"): ComponentRatio("FG1", "SEMI", 1.0, LEVEL_HISTORICAL_PRODUCTION, "KG", "SEMI_FINISHED"),
            ("SEMI", "RAW_X"): ComponentRatio("SEMI", "RAW_X", 0.5, LEVEL_HISTORICAL_PRODUCTION, "KG", "RAW_MATERIAL"),
            ("SEMI", "RAW_Y"): ComponentRatio("SEMI", "RAW_Y", 0.2, LEVEL_HISTORICAL_PRODUCTION, "KG", "RAW_MATERIAL"),
        }
        equiv = {"SEMI": 100.0}
        terminal, flags = expand_terminal(equiv, ratios, {"SEMI"})
        self.assertNotIn("SEMI", terminal)
        self.assertAlmostEqual(terminal["RAW_X"], 50.0)
        self.assertAlmostEqual(terminal["RAW_Y"], 20.0)

    def test_no_double_count(self):
        # semi quantity is moved, not summed with raw
        ratios = {("SEMI", "RAW_X"): ComponentRatio("SEMI", "RAW_X", 1.0, LEVEL_HISTORICAL_PRODUCTION, "KG", "RAW")}
        equiv = {"SEMI": 10.0, "RAW_X": 5.0}
        terminal, _ = expand_terminal(equiv, ratios, {"SEMI"})
        self.assertNotIn("SEMI", terminal)
        self.assertAlmostEqual(terminal["RAW_X"], 15.0)  # 5 + 10*1

    def test_unresolved_semi_kept(self):
        equiv = {"SEMI": 10.0}
        terminal, flags = expand_terminal(equiv, {}, {"SEMI"})
        self.assertIn("SEMI", terminal)
        self.assertEqual(flags.get("SEMI"), "MULTILEVEL_EXPANSION_PARTIAL")


class TestConservation(unittest.TestCase):
    def test_transfer_preserves_total(self):
        a = {"RAW_A": 37.5, "FRASCO": 150.0}
        b = {"RAW_A": 37.5, "FRASCO": 150.0}
        ok, flag = transfer_conservation(a, b)
        self.assertTrue(ok)
        self.assertEqual(flag, "TRANSFER_CONSERVED")

    def test_transfer_changes_total(self):
        a = {"RAW_A": 37.5}
        b = {"RAW_A": 38.0}
        ok, flag = transfer_conservation(a, b)
        self.assertFalse(ok)
        self.assertEqual(flag, "TRANSFER_NOT_CONSERVED")

    def test_fg_warehouse_transfer_preserves_global_equivalent(self):
        # same FG total qty, split differently across warehouses -> same global
        ratios = {("FG1", "RAW_A"): ComponentRatio("FG1", "RAW_A", 0.25, LEVEL_HISTORICAL_PRODUCTION, "KG", "RAW")}
        before = build_equivalence(
            [FgStock("FG1", "LAB-T1", 100.0, "FCO", "FINISHED_GOOD"),
             FgStock("FG1", "2A-SAL", 0.0, "FCO", "BRANCH")], ratios, {})
        after = build_equivalence(
            [FgStock("FG1", "LAB-T1", 40.0, "FCO", "FINISHED_GOOD"),
             FgStock("FG1", "2A-SAL", 60.0, "FCO", "BRANCH")], ratios, {})
        self.assertEqual(global_equivalent_total(before), global_equivalent_total(after))
        ok, flag = transfer_conservation(global_equivalent_total(before),
                                         global_equivalent_total(after))
        self.assertTrue(ok)


class TestUomGuard(unittest.TestCase):
    def test_compatible(self):
        self.assertTrue(uom_compatible(["KG", "KG"]))
        self.assertTrue(uom_compatible([]))

    def test_incompatible(self):
        self.assertFalse(uom_compatible(["KG", "L"]))


if __name__ == "__main__":
    unittest.main()