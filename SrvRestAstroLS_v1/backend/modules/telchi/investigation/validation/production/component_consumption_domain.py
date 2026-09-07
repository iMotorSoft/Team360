"""Production component consumption domain (pure logic + read-only SQL).

Semantics validated against real SAP (2026-08-26):
  - NET_ACTUAL_CONSUMPTION = SUM(IGE1.Quantity) WHERE BaseType=202
    (no cancellations: OIGE.CANCELED all 'N'; no negative qty; no returns
     pattern in population — the single TT60 InQty>0 row is a 2022 migration
     artifact with invalid BASE_REF)
  - GROSS == NET in this installation
  - Multiple issues per WOR1 line exist (0.5% lines have 2-4 issues)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.recipe_bom_domain import expected_qty


@dataclass
class ConsumptionCase:
    order_docentry: int
    order_docnum: int
    parent_item: str
    wor1_line: int
    component_item: str
    issue_method: str
    warehouse: str | None
    expected_qty: Decimal
    issue_count: int
    gross_issued_qty: Decimal
    net_actual_qty: Decimal
    first_issue_at: Any | None
    last_issue_at: Any | None
    first_receipt_at: Any | None
    last_receipt_at: Any | None
    variance_qty: Decimal
    variance_pct: float | None
    classification: str
    confirmation: str = "EXACT_DOCUMENT_LINK"
    issue_docs: list = None

    def to_dict(self) -> dict:
        return {
            "order_docentry": self.order_docentry,
            "order_docnum": self.order_docnum,
            "parent_item": self.parent_item,
            "wor1_line": self.wor1_line,
            "component_item": self.component_item,
            "issue_method": self.issue_method,
            "warehouse": self.warehouse,
            "expected_qty": str(self.expected_qty),
            "issue_count": self.issue_count,
            "gross_issued_qty": str(self.gross_issued_qty),
            "net_actual_qty": str(self.net_actual_qty),
            "first_issue_at": str(self.first_issue_at)[:10] if self.first_issue_at else None,
            "last_issue_at": str(self.last_issue_at)[:10] if self.last_issue_at else None,
            "first_receipt_at": str(self.first_receipt_at)[:10] if self.first_receipt_at else None,
            "last_receipt_at": str(self.last_receipt_at)[:10] if self.last_receipt_at else None,
            "variance_qty": str(self.variance_qty),
            "variance_pct": self.variance_pct,
            "classification": self.classification,
            "confirmation": self.confirmation,
            "issue_docs": self.issue_docs or [],
        }


def classify_consumption(
    expected: Decimal,
    net: Decimal,
    issue_count: int,
    output_qty: Decimal | None,
    expected_planned: Decimal | None,
    method: str,
    order_status: str,
) -> str:
    """Refined classification of a component consumption case."""
    tol = Decimal("0.001")
    if expected == 0:
        if net > 0:
            return "ZERO_EXPECTED_WITH_ACTUAL"
        return "ZERO_EXPECTED_ZERO_ACTUAL"
    if net == 0:
        if expected_planned is not None and expected_planned == 0:
            return "NOT_CONSUMED_PLANNED_ZERO"
        return "EXPECTED_NOT_CONSUMED"
    if abs(net - expected) <= tol:
        return "EXACT"
    # material variance
    if output_qty is not None and expected_planned is not None:
        # if output partial, normalize expected to actual output for context
        if output_qty == 0:
            return "PARTIAL_ZERO_OUTPUT_WITH_ISSUE"
    if net > expected:
        return "TRUE_OVER_CONSUMPTION_CANDIDATE"
    return "TRUE_UNDER_CONSUMPTION_CANDIDATE"


def fetch_order_consumption(
    cur: Any,
    order_docentry: int,
    parent_item: str,
    planned_qty: Decimal,
    order_status: str,
) -> list[ConsumptionCase]:
    """Build consumption cases for a single production order."""
    cur.execute(
        '''SELECT W."LineNum", W."ItemCode", W."BaseQtyNum", W."BaseQtyDen",
                  W."IssuedQty", W."IssueType", W."wareHouse"
           FROM "TELCHI"."WOR1" W WHERE W."DocEntry"=? ORDER BY W."LineNum"''',
        (order_docentry,),
    )
    wor1 = cur.fetchall()

    cur.execute(
        '''SELECT "LineNum", "ItemCode", "Quantity", "BaseLine", "DocDate", "DocEntry"
           FROM "TELCHI"."IGE1" WHERE "BaseType"=202 AND "BaseEntry"=?
           ORDER BY "DocDate"''',
        (order_docentry,),
    )
    issues = cur.fetchall()

    cur.execute(
        '''SELECT "LineNum", "ItemCode", "Quantity", "BaseLine", "DocDate", "DocEntry"
           FROM "TELCHI"."IGN1" WHERE "BaseType"=202 AND "BaseEntry"=?
           ORDER BY "DocDate"''',
        (order_docentry,),
    )
    receipts = cur.fetchall()

    # group issues by (BaseLine, ItemCode)
    issue_by_key: dict[tuple, list] = {}
    for r in issues:
        key = (r[3], r[1])
        issue_by_key.setdefault(key, []).append(r)

    receipt_dates = sorted(r[4] for r in receipts)
    first_receipt = receipt_dates[0] if receipt_dates else None
    last_receipt = receipt_dates[-1] if receipt_dates else None
    output_qty = sum((Decimal(str(r[2])) for r in receipts), Decimal(0))

    cases = []
    for w in wor1:
        line, comp, num, den = w[0], w[1], w[2], w[3]
        issued_field, method, whs = w[4], w[5], w[6]
        exp = expected_qty(num, den, planned_qty)
        iss = issue_by_key.get((line, comp), [])
        gross = sum((Decimal(str(r[2])) for r in iss), Decimal(0))
        issue_dates = sorted(r[4] for r in iss)
        first_issue = issue_dates[0] if issue_dates else None
        last_issue = issue_dates[-1] if issue_dates else None

        variance = gross - exp
        pct = float(variance / exp * 100) if exp != 0 else None

        cls = classify_consumption(exp, gross, len(iss), output_qty, planned_qty, method, order_status)

        cases.append(ConsumptionCase(
            order_docentry=order_docentry,
            order_docnum=0,
            parent_item=parent_item,
            wor1_line=line,
            component_item=comp,
            issue_method=method,
            warehouse=whs,
            expected_qty=exp,
            issue_count=len(iss),
            gross_issued_qty=gross,
            net_actual_qty=gross,
            first_issue_at=first_issue,
            last_issue_at=last_issue,
            first_receipt_at=first_receipt,
            last_receipt_at=last_receipt,
            variance_qty=variance,
            variance_pct=pct,
            classification=cls,
            issue_docs=[r[5] for r in iss],
        ))
    return cases
