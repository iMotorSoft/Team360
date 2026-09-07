"""Warehouse transfer traceability domain (pure logic + read-only SQL).

Semantics validated against real SAP (2026-08-26):
  - WTR1.FromWhsCod = origin warehouse, WTR1.WhsCode = destination
  - WTR1.Quantity = transferred quantity (positive = forward, negative =
    reverse/adjustment documents in ACTIVE docs; CANCELED docs excluded by header)
  - OWTR.CANCELED='Y' -> exclude (424 docs, 5,832 lines all positive)
  - OINM TT67 BASE_REF = OWTR.DocNum; 2 rows per line (origin out, dest in,
    equal quantities) -> QUANTITY_CONSERVATION exact
  - Batch: WTR1.U_LOTE (minority 0.2%) + IBT1 BaseType=67 (full batch trace)
  - PHYSICAL_DISPATCH_SEMANTICS = ACCOUNTING_ONLY (SAP posts both sides in
    one event; does not prove physical arrival)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class WarehouseTransferLine:
    """Atomic warehouse transfer line (OWTR.DocEntry + WTR1.LineNum)."""
    transfer_docentry: int
    transfer_docnum: int
    transfer_line: int
    item_code: str
    quantity: Decimal
    origin_whscode: str | None
    destination_whscode: str | None
    origin_role: str | None
    destination_role: str | None
    doc_date: Any | None
    create_date: Any | None
    user_sign: int | None
    canceled: str
    batch: str | None
    uom: str | None
    confirmation: str = "EXACT_TRANSFER_LINE"

    def to_dict(self) -> dict:
        return {
            "transfer_docentry": self.transfer_docentry,
            "transfer_docnum": self.transfer_docnum,
            "transfer_line": self.transfer_line,
            "item_code": self.item_code,
            "quantity": str(self.quantity),
            "origin_whscode": self.origin_whscode,
            "destination_whscode": self.destination_whscode,
            "origin_role": self.origin_role,
            "destination_role": self.destination_role,
            "doc_date": str(self.doc_date)[:10] if self.doc_date else None,
            "create_date": str(self.create_date)[:10] if self.create_date else None,
            "user_sign": self.user_sign,
            "canceled": self.canceled,
            "batch": self.batch,
            "uom": self.uom,
            "confirmation": self.confirmation,
        }


# Warehouse roles from discovery (OWHS master, 82 warehouses)
def classify_whs_role(code: str, name: str) -> str:
    n = (name or "").upper()
    c = (code or "").upper()
    if "MATERIA PRIMA" in n or c.endswith("-M1") or "GRANEL" in n:
        return "RAW_MATERIAL"
    if "PRODUCTO TERMINADO" in n or ("-T" in c and ("LAB" in c or "SAA" in c or "MAG" in c or "LPZ" in c)):
        return "FINISHED_GOODS"
    if "PROCESO" in n or "PRODUCTOS EN PROCESO" in n or c.endswith("-P1") or c.endswith("-P2"):
        return "LABORATORIO_PROCESS"
    if "DESPACHO" in n or "PICKING" in n:
        return "DISPATCH"
    if "MOVIL" in n or "RUTA" in n:
        return "MOBILE"
    if "TRANSITO" in n or "TRAN" in c or "TRS" in c:
        return "TRANSIT"
    if "SALON" in n or "SAL" in c:
        return "SUCURSAL_SALON"
    if "DISTRIBUCION" in n or "TERBOL" in n:
        return "DISTRIBUTION_TERBOL"
    if "DMS" in c:
        return "DMS"
    if "MEDICAMENTOS" in n or "MATRIZ" in n or "AMD" in c:
        return "CENTRAL"
    return "OTHER"


def classify_transfer(
    origin_role: str | None,
    destination_role: str | None,
) -> str:
    if origin_role is None or destination_role is None:
        return "ROLE_UNRESOLVED"
    if origin_role == destination_role:
        return "SAME_ROLE"
    if origin_role in ("TRANSIT",) or destination_role in ("TRANSIT",):
        return "VIA_TRANSIT"
    return "CROSS_ROLE"