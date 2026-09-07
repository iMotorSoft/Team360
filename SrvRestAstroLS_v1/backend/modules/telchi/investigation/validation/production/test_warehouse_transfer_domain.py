"""Warehouse transfer traceability domain unit tests (pure logic)."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.validation.production.warehouse_transfer_domain import (
    WarehouseTransferLine,
    classify_whs_role,
    classify_transfer,
)


class TestWarehouseRole(unittest.TestCase):
    def test_central(self):
        self.assertEqual(classify_whs_role("CM-AMD", "Almacén Medicamentos Casa Matriz"), "CENTRAL")

    def test_finished_goods(self):
        self.assertEqual(classify_whs_role("LAB-T1", "Almacén Producto Terminado AGEMED"), "FINISHED_GOODS")

    def test_salon(self):
        self.assertEqual(classify_whs_role("2A-SAL", "Almacén Salón 2A"), "SUCURSAL_SALON")

    def test_transit(self):
        self.assertEqual(classify_whs_role("SAL-TRS", "Almacén Transitorio Salones"), "TRANSIT")

    def test_mobile(self):
        self.assertEqual(classify_whs_role("LAB-D1", "Almacen Movil 4702 GIP"), "MOBILE")

    def test_raw_material(self):
        self.assertEqual(classify_whs_role("LAB-M1", "Almacén Materia Prima"), "RAW_MATERIAL")


class TestTransferClassification(unittest.TestCase):
    def test_cross_role(self):
        self.assertEqual(classify_transfer("FINISHED_GOODS", "SUCURSAL_SALON"), "CROSS_ROLE")

    def test_via_transit(self):
        self.assertEqual(classify_transfer("CENTRAL", "TRANSIT"), "VIA_TRANSIT")
        self.assertEqual(classify_transfer("TRANSIT", "SUCURSAL_SALON"), "VIA_TRANSIT")

    def test_same_role(self):
        self.assertEqual(classify_transfer("SUCURSAL_SALON", "SUCURSAL_SALON"), "SAME_ROLE")

    def test_unresolved(self):
        self.assertEqual(classify_transfer(None, "SUCURSAL_SALON"), "ROLE_UNRESOLVED")


class TestTransferLine(unittest.TestCase):
    def test_line_construction(self):
        l = WarehouseTransferLine(
            transfer_docentry=100, transfer_docnum=260100001, transfer_line=0,
            item_code="L00056", quantity=Decimal("12"),
            origin_whscode="LAB-T1", destination_whscode="LAB-D2",
            origin_role="FINISHED_GOODS", destination_role="MOBILE",
            doc_date=None, create_date=None, user_sign=46, canceled="N", batch=None, uom=None,
        )
        d = l.to_dict()
        self.assertEqual(d["item_code"], "L00056")
        self.assertEqual(d["quantity"], "12")
        self.assertEqual(d["confirmation"], "EXACT_TRANSFER_LINE")

    def test_negative_qty_preserved(self):
        l = WarehouseTransferLine(
            transfer_docentry=230, transfer_docnum=1, transfer_line=0,
            item_code="M06806", quantity=Decimal("-998"),
            origin_whscode="2A-AMD", destination_whscode="01",
            origin_role="CENTRAL", destination_role="TRANSIT",
            doc_date=None, create_date=None, user_sign=46, canceled="N", batch=None, uom=None,
        )
        self.assertEqual(l.quantity, Decimal("-998"))


if __name__ == "__main__":
    unittest.main(verbosity=2)