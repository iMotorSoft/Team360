"""Unit tests for the material stock position domain (pure, no HANA)."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.stock.stock_domain import (
    ItemFacts,
    StockPosition,
    ITEM_FINISHED_GOOD,
    ITEM_INPUT,
    ITEM_OTHER,
    ITEM_PACKAGING,
    ITEM_RAW_MATERIAL,
    ITEM_SEMI_FINISHED,
    ITEM_SERVICE,
    ITEM_TRADED_GOOD,
    ITEM_UNRESOLVED,
    ROLE_DISTRIBUTION,
    ROLE_FINISHED_GOOD,
    ROLE_IMPORT,
    ROLE_MOBILE,
    ROLE_RAW_MATERIAL,
    ROLE_UNRESOLVED,
    WAREHOUSE_ROLES,
    classify_item,
    reconcile_ledger,
    resolve_warehouse_role,
)


class TestWarehouseRole(unittest.TestCase):
    def test_all_82_explicit(self):
        self.assertEqual(len(WAREHOUSE_ROLES), 82)

    def test_known_roles(self):
        self.assertEqual(WAREHOUSE_ROLES["LAB-M1"], ROLE_RAW_MATERIAL)
        self.assertEqual(WAREHOUSE_ROLES["LAB-T1"], ROLE_FINISHED_GOOD)
        self.assertEqual(WAREHOUSE_ROLES["ALM-IMP"], ROLE_IMPORT)
        self.assertEqual(WAREHOUSE_ROLES["LPZ-DT1"], ROLE_DISTRIBUTION)
        self.assertEqual(WAREHOUSE_ROLES["LAB-D4"], ROLE_MOBILE)

    def test_resolve_explicit(self):
        self.assertEqual(resolve_warehouse_role("LAB-M1", "x", None, None, None), ROLE_RAW_MATERIAL)

    def test_resolve_keyword_fallback(self):
        self.assertEqual(resolve_warehouse_role("ZZZ", "Almacén de Importación", "SAP", "01", "N"), ROLE_IMPORT)

    def test_resolve_dms_mobile(self):
        self.assertEqual(resolve_warehouse_role("ZZZ", "Algo", "DMS", "03", "N"), ROLE_MOBILE)

    def test_resolve_unresolved(self):
        self.assertEqual(resolve_warehouse_role("ZZZ", "Algo raro", "SAP", "03", "N"), ROLE_UNRESOLVED)


class TestItemClassification(unittest.TestCase):
    def test_finished_good(self):
        f = ItemFacts("L01001", "ALCOHOL", "I", 104, "Y", "Y", "N", is_produced=True)
        self.assertEqual(classify_item(f), ITEM_FINISHED_GOOD)

    def test_semi_finished(self):
        f = ItemFacts("L01945", "CREOLINA GRANEL", "I", 100, "Y", "N", "N", is_produced=True)
        self.assertEqual(classify_item(f), ITEM_SEMI_FINISHED)

    def test_packaging(self):
        f = ItemFacts("L03427", "FRASCO GOTERO NATURAL 30mL", "I", 130, "Y", "N", "Y")
        self.assertEqual(classify_item(f), ITEM_PACKAGING)

    def test_packaging_by_name(self):
        f = ItemFacts("L00561", "ETIQUETA AGUA OXIGENADA", "I", 100, "Y", "N", "Y",
                      is_bom_component=True)
        self.assertEqual(classify_item(f), ITEM_PACKAGING)

    def test_raw_material_component(self):
        f = ItemFacts("L01010", "SODA CAUSTICA", "I", 126, "Y", "N", "Y",
                      is_bom_component=True)
        self.assertEqual(classify_item(f), ITEM_RAW_MATERIAL)

    def test_input(self):
        f = ItemFacts("M02566", "MATERIAL X", "I", 129, "Y", "N", "Y")
        self.assertEqual(classify_item(f), ITEM_INPUT)

    def test_traded_good(self):
        f = ItemFacts("M00663", "PRODUCTO REVENTA", "I", 100, "Y", "Y", "Y")
        self.assertEqual(classify_item(f), ITEM_TRADED_GOOD)

    def test_service(self):
        f = ItemFacts("S0001", "SERVICIO", "I", 141, "N", "N", "Y")
        self.assertEqual(classify_item(f), ITEM_SERVICE)

    def test_fixed_asset(self):
        f = ItemFacts("A0001", "ACTIVO", "F", 144, "N", "N", "N")
        self.assertEqual(classify_item(f), ITEM_OTHER)

    def test_unresolved(self):
        f = ItemFacts("X0001", "RARO", "I", 999, "Y", "N", "N")
        self.assertEqual(classify_item(f), ITEM_UNRESOLVED)


class TestStockSemantics(unittest.TestCase):
    def test_available(self):
        p = StockPosition("L", "W", 100.0, 30.0, 0.0, 0.0, "N", "UNI")
        self.assertEqual(p.available_physical, 70.0)

    def test_committed_over_stock(self):
        p = StockPosition("L", "W", 10.0, 30.0, 0.0, 0.0, "N", "UNI")
        self.assertEqual(p.available_physical, -20.0)


class TestReconcile(unittest.TestCase):
    def test_exact(self):
        ok, diff, flag = reconcile_ledger(447891.0, 4804368.0, 4356477.0)
        self.assertTrue(ok)
        self.assertEqual(flag, "LEDGER_RECONCILED")
        self.assertAlmostEqual(diff, 0.0)

    def test_mismatch(self):
        ok, diff, flag = reconcile_ledger(100.0, 50.0, 0.0)
        self.assertFalse(ok)
        self.assertEqual(flag, "LEDGER_MISMATCH")


if __name__ == "__main__":
    unittest.main()