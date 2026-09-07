"""TELCHI RECIPE/BOM traceability — domain builder (pure logic + read-only SQL).

Provides:
  - EXPECTED_COMPONENT_QTY formula: (BaseQtyNum/BaseQtyDen) * OWOR.PlannedQty
  - Recipe order snapshot (WOR1 historical)
  - Recipe master current (OITT/ITT1)
  - Recipe signature (deterministic, order-independent)
  - Issue method classification
  - Expected vs actual comparison
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


@dataclass(frozen=True)
class RecipeOrderSnapshot:
    """Historical recipe copied into a production order (WOR1)."""
    order_docentry: int
    order_docnum: int
    parent_item: str
    line_num: int
    component_item: str
    base_qty_num: Decimal
    base_qty_den: Decimal
    base_qty: Decimal  # display value
    expected_qty: Decimal
    issued_qty: Decimal | None
    issue_method: str
    warehouse: str | None
    uom: str | None

    @property
    def recipe_signature_input(self) -> tuple:
        # normalized: component + factor + method + warehouse (order-independent)
        factor = (self.base_qty_num / self.base_qty_den) if self.base_qty_den else Decimal(0)
        return (self.component_item, str(factor), self.issue_method, str(self.warehouse))

    @property
    def recipe_signature(self) -> str:
        payload = sorted(str(x) for x in self.recipe_signature_input)
        return hashlib.sha256("|".join(payload).encode()).hexdigest()[:16]


def expected_qty(base_qty_num, base_qty_den, planned_qty) -> Decimal:
    """EXPECTED_COMPONENT_QTY = (BaseQtyNum/BaseQtyDen) * OWOR.PlannedQty.

    Validated at scale: 129,848/140,319 exact; remainder is WOR1.PlannedQty
    display rounding. This formula uses the exact factor.
    """
    num = Decimal(str(base_qty_num)) if base_qty_num is not None else Decimal(0)
    den = Decimal(str(base_qty_den)) if base_qty_den not in (None, 0) else Decimal(1)
    planned = Decimal(str(planned_qty)) if planned_qty is not None else Decimal(0)
    factor = num / den
    return (factor * planned).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def fetch_order_snapshots(cur: Any, window: tuple[str, str] | None = None) -> list[RecipeOrderSnapshot]:
    """Fetch historical recipe snapshots (WOR1 joined OWOR) for production orders."""
    date_clause = ""
    params: list = []
    if window:
        date_clause = "AND O.\"PostDate\" >= ? AND O.\"PostDate\" <= ?"
        params = [window[0], window[1]]

    cur.execute(
        f'''SELECT O."DocEntry", O."DocNum", O."ItemCode", W."LineNum", W."ItemCode",
                  W."BaseQtyNum", W."BaseQtyDen", W."BaseQty", W."PlannedQty",
                  W."IssuedQty", W."IssueType", W."wareHouse", W."UomCode"
           FROM "TELCHI"."WOR1" W
           JOIN "TELCHI"."OWOR" O ON O."DocEntry" = W."DocEntry"
           WHERE O."Type" = 'S' {date_clause}''',
        params,
    )
    rows = []
    for r in cur.fetchall():
        rows.append(RecipeOrderSnapshot(
            order_docentry=r[0], order_docnum=r[1], parent_item=r[2], line_num=r[3],
            component_item=r[4], base_qty_num=r[5], base_qty_den=r[6], base_qty=r[7],
            expected_qty=expected_qty(r[5], r[6], r[8]),
            issued_qty=r[9], issue_method=r[10], warehouse=r[11], uom=r[12],
        ))
    return rows


def fetch_master_bom(cur: Any) -> dict[str, list[dict]]:
    """Fetch current master BOM (OITT/ITT1) keyed by parent item."""
    cur.execute(
        '''SELECT T."Father", T."Code", T."Quantity", T."IssueMthd", T."Warehouse", T."Uom"
           FROM "TELCHI"."ITT1" T'''
    )
    bom: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        bom.setdefault(r[0], []).append({
            "component": r[1], "quantity": r[2], "issue_method": r[3],
            "warehouse": r[4], "uom": r[5],
        })
    return bom


def fetch_actual_consumption(cur: Any, order_docentry: int) -> dict[tuple[int, str], Decimal]:
    """Actual consumption (IGE1 BaseType=202) per (BaseLine, ItemCode)."""
    cur.execute(
        '''SELECT "BaseLine", "ItemCode", SUM("Quantity")
           FROM "TELCHI"."IGE1" WHERE "BaseType"=202 AND "BaseEntry"=?
           GROUP BY "BaseLine", "ItemCode"''',
        (order_docentry,),
    )
    return {(r[0], r[1]): Decimal(str(r[2])) for r in cur.fetchall()}


def compare_expected_actual(
    snapshots: list[RecipeOrderSnapshot],
    consumption: dict[tuple[int, str], Decimal],
    tolerance_abs: Decimal = Decimal("0.001"),
) -> list[dict]:
    """Compare expected vs actual per order line."""
    out = []
    for s in snapshots:
        key = (s.line_num, s.component_item)
        actual = consumption.get(key)
        if actual is None:
            status = "EXPECTED_NOT_CONSUMED"
        elif abs(actual - s.expected_qty) <= tolerance_abs:
            status = "EXACT"
        elif actual > s.expected_qty:
            status = "OVER_CONSUMPTION"
        else:
            status = "UNDER_CONSUMPTION"
        out.append({
            "order_docentry": s.order_docentry, "order_docnum": s.order_docnum,
            "parent_item": s.parent_item, "line_num": s.line_num,
            "component_item": s.component_item, "expected_qty": str(s.expected_qty),
            "actual_qty": str(actual) if actual is not None else None,
            "issued_qty": str(s.issued_qty) if s.issued_qty is not None else None,
            "issue_method": s.issue_method, "warehouse": s.warehouse,
            "status": status,
        })
    return out
