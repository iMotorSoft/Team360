"""Production output traceability domain (pure logic + read-only SQL).

Semantics validated against real SAP (2026-08-26):
  - NET_ACTUAL_OUTPUT_QTY = SUM(IGN1.Quantity) WHERE BaseType=202
    (OIGN.CANCELED all 'N', IGN1 all positive, no reversals observed)
  - OWOR.CmpltQty == SUM(IGN1.Quantity) (19,654/20,487; only mismatch = 17757 rework)
  - ItemCode mismatch (1,252 lines, 5.9%): all are rework where received item
    is a WOR1 component (1,254 matches WOR1 component)
  - Batch: IGN1.U_LOTE -> OBTN.DistNumber EXACT (5,196/5,228 distinct lots)
  - OINM TT59 reconciliation partial (53.5% of BaseRefs), exact when linked
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


@dataclass
class ProductionOutput:
    """Atomic output receipt line (production_output contract)."""
    production_docentry: int
    production_docnum: int
    parent_item: str
    planned_qty: Decimal
    receipt_docentry: int
    receipt_docnum: int
    receipt_line: int
    output_item: str
    output_qty: Decimal
    warehouse: str | None
    doc_date: Any | None
    create_date: Any | None
    batch: str | None
    batch_expiry: Any | None
    confirmation: str = "EXACT_DOCUMENT_LINK"

    def to_dict(self) -> dict:
        return {
            "production_docentry": self.production_docentry,
            "production_docnum": self.production_docnum,
            "parent_item": self.parent_item,
            "planned_qty": str(self.planned_qty),
            "receipt_docentry": self.receipt_docentry,
            "receipt_docnum": self.receipt_docnum,
            "receipt_line": self.receipt_line,
            "output_item": self.output_item,
            "output_qty": str(self.output_qty),
            "warehouse": self.warehouse,
            "doc_date": str(self.doc_date)[:10] if self.doc_date else None,
            "create_date": str(self.create_date)[:10] if self.create_date else None,
            "batch": self.batch,
            "batch_expiry": str(self.batch_expiry)[:10] if self.batch_expiry else None,
            "confirmation": self.confirmation,
        }


@dataclass
class OrderOutputSummary:
    production_docentry: int
    production_docnum: int
    parent_item: str
    planned_qty: Decimal
    receipt_doc_count: int
    receipt_line_count: int
    first_receipt_at: Any | None
    last_receipt_at: Any | None
    gross_output_qty: Decimal
    net_actual_output_qty: Decimal
    warehouse_count: int
    warehouses: list
    output_vs_plan_qty: Decimal
    output_vs_plan_pct: float | None
    classification: str
    cmplt_qty: Decimal | None
    batches: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "production_docentry": self.production_docentry,
            "production_docnum": self.production_docnum,
            "parent_item": self.parent_item,
            "planned_qty": str(self.planned_qty),
            "receipt_doc_count": self.receipt_doc_count,
            "receipt_line_count": self.receipt_line_count,
            "first_receipt_at": str(self.first_receipt_at)[:10] if self.first_receipt_at else None,
            "last_receipt_at": str(self.last_receipt_at)[:10] if self.last_receipt_at else None,
            "gross_output_qty": str(self.gross_output_qty),
            "net_actual_output_qty": str(self.net_actual_output_qty),
            "warehouse_count": self.warehouse_count,
            "warehouses": self.warehouses,
            "output_vs_plan_qty": str(self.output_vs_plan_qty),
            "output_vs_plan_pct": self.output_vs_plan_pct,
            "classification": self.classification,
            "cmplt_qty": str(self.cmplt_qty) if self.cmplt_qty is not None else None,
            "batches": self.batches,
        }


def classify_output(
    planned: Decimal,
    actual: Decimal,
    receipt_count: int,
    warehouse_count: int,
    consumption_qty: Decimal | None,
) -> str:
    tol = Decimal("0.001")
    if actual == 0:
        if consumption_qty and consumption_qty > 0:
            return "CONSUMPTION_WITHOUT_OUTPUT"
        return "ZERO_OUTPUT"
    if receipt_count > 1:
        base = "MULTIPLE_RECEIPTS_"
    else:
        base = ""
    if abs(actual - planned) <= tol:
        return base + "EXACT_PLANNED_OUTPUT"
    if actual < planned:
        return base + "PARTIAL_OUTPUT"
    return base + "OVER_PLANNED_OUTPUT"


def fetch_receipts_batch(cur: Any, order_ids: list[int]) -> tuple[list, dict]:
    """Fetch IGN1 BT=202 lines + OIGN headers for the given orders (batch)."""
    ph = ",".join("?" * len(order_ids))
    cur.execute(
        f'''SELECT N."DocEntry", N."LineNum", N."BaseEntry", N."BaseRef", N."ItemCode",
                   N."Quantity", N."WhsCode", N."DocDate", N."U_LOTE", N."U_VENCLOTE",
                   O2."DocNum", O2."CreateDate"
            FROM "TELCHI"."IGN1" N
            JOIN "TELCHI"."OIGN" O2 ON O2."DocEntry" = N."DocEntry"
            WHERE N."BaseType"=202 AND N."BaseEntry" IN ({ph})''',
        order_ids,
    )
    rows = cur.fetchall()
    # group by BaseEntry
    by_order: dict[int, list] = {}
    for r in rows:
        by_order.setdefault(r[2], []).append(r)
    return rows, by_order


def build_order_summary(
    order: tuple,
    receipt_rows: list,
    consumption_by_order: dict[int, Decimal],
) -> OrderOutputSummary:
    de = order[0]
    planned = Decimal(str(order[3]))
    cmplt = Decimal(str(order[4])) if order[4] is not None else None

    if not receipt_rows:
        cons = consumption_by_order.get(de, Decimal(0))
        return OrderOutputSummary(
            production_docentry=de, production_docnum=order[1], parent_item=order[2],
            planned_qty=planned, receipt_doc_count=0, receipt_line_count=0,
            first_receipt_at=None, last_receipt_at=None,
            gross_output_qty=Decimal(0), net_actual_output_qty=Decimal(0),
            warehouse_count=0, warehouses=[], output_vs_plan_qty=-planned,
            output_vs_plan_pct=float(-100) if planned else None,
            classification=classify_output(planned, Decimal(0), 0, 0, cons),
            cmplt_qty=cmplt,
        )

    dates = [r[7] for r in receipt_rows if r[7] is not None]
    warehouses = sorted({r[6] for r in receipt_rows if r[6] is not None})
    total = sum((Decimal(str(r[5])) for r in receipt_rows), Decimal(0))
    doc_count = len({r[0] for r in receipt_rows})
    batches = sorted({r[8] for r in receipt_rows if r[8]})
    cons = consumption_by_order.get(de, None)

    return OrderOutputSummary(
        production_docentry=de, production_docnum=order[1], parent_item=order[2],
        planned_qty=planned, receipt_doc_count=doc_count, receipt_line_count=len(receipt_rows),
        first_receipt_at=min(dates) if dates else None,
        last_receipt_at=max(dates) if dates else None,
        gross_output_qty=total, net_actual_output_qty=total,
        warehouse_count=len(warehouses), warehouses=warehouses,
        output_vs_plan_qty=total - planned,
        output_vs_plan_pct=float((total - planned) / planned * 100) if planned else None,
        classification=classify_output(planned, total, len(receipt_rows), len(warehouses), cons),
        cmplt_qty=cmplt, batches=batches,
    )