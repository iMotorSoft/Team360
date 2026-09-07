"""SALE x CASH x STOCK traceability case builder (TELCHI spec §19-23, T48-T50).

Pure, storage-independent. Builds one atomic case from already-resolved facts:

  invoice  (OINV header)     + lines (INV1)
  payments (ORCT, via ITR1 settlement, N:N allowed)
  stock    (OINM resolved via DOCNUM_RESOLVE/APPLOBJ)

Produces the confirmations and cash-difference classification the owner needs:
  SALE_CONFIRMED / INVOICE_CONFIRMED / CASH_CONFIRMED / GOODS_OUT_CONFIRMED /
  WAREHOUSE_CONFIRMED / COMMERCIAL_VALUE_CONFIRMED / COST_VALUE /
  TOTAL/EXPLAINED/UNEXPLAINED difference / status.

Never labels fraud. Canceled invoices preserve lifecycle and are never
CONSISTENT. Absence of stock link is STOCK_RELATION_UNRESOLVED, never NO_STOCK.
"""
from __future__ import annotations

from modules.telchi.investigation.atomic.semantic.payment import (
    CASH, MIXED, classify_payment_method, cancellation_state,
)

# ---- statuses (§23) -----------------------------------------------------------
CONSISTENT = "CONSISTENT"
PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
UNRESOLVED = "UNRESOLVED"
SOURCE_DATA_MISSING = "SOURCE_DATA_MISSING"

STOCK_RELATION_UNRESOLVED = "STOCK_RELATION_UNRESOLVED"


def goods_sale_value_from_lines(lines: list[dict]) -> dict:
    """Commercial value of goods out: qty x effective sale price per line.

    Uses the document's own line economics (Quantity, Price, DiscPrcnt,
    LineTotal) — never OINM cost as sale price (§17/§18). Accepts both raw
    SAP casing (Quantity/Price/DiscPrcnt) and normalized casing.
    """
    value = 0.0
    line_count = 0
    for ln in lines:
        qty = float(ln.get("quantity") or ln.get("Quantity") or 0)
        price = float(ln.get("price") or ln.get("Price") or 0)
        disc = float(ln.get("disc_prcnt") or ln.get("DiscPrcnt") or 0)
        line_value = qty * price * (1.0 - disc / 100.0)
        value += line_value
        line_count += 1
    return {
        "goods_sale_value": round(value, 4),
        "lines": line_count,
        "basis": "QUANTITY_X_PRICE_X_DISCOUNT",
    }


def expected_cash_for_case(payment_method: str, goods_sale_value: float) -> float | None:
    """Expected cash: only meaningful for 100% cash sales (§19).

    Mixed/transfer/card sales have no single expected cash figure against the
    physical cash register; the payment mix itself explains the difference.
    """
    if payment_method == CASH:
        return round(goods_sale_value, 4)
    return None


def build_case(invoice: dict | None, lines: list[dict],
               payments: list[dict], stock: list[dict],
               settled_amount: float | None = None,
               warehouse_name: str | None = None,
               tolerance: float = 0.01) -> dict:
    """Build the atomic traceability case for one invoice.

    All inputs are raw fact rows (physical SAP column names for classifier).
    settled_amount: ITR1.ReconSum sum for SrcObjTyp=13 (active recons) —
    the amount APPLIED to this invoice (DEC-017, 100% PaidToDate match).
    Payments are N:N via reconciliation; never attribute a full payment to a
    single invoice.
    """
    if invoice is None:
        return {
            "case_id": None,
            "status": SOURCE_DATA_MISSING,
            "confirmations": {},
            "differences": None,
            "explanation": ["INVOICE_MISSING"],
        }

    docentry = invoice.get("DocEntry")
    canceled = cancellation_state(invoice.get("CANCELED"))

    # ---- invoice / sale confirmation
    sale_confirmed = docentry is not None
    invoice_confirmed = invoice.get("DocStatus") in ("O", "C")

    # ---- lines / commercial value
    value = goods_sale_value_from_lines(lines)
    commercial_value_confirmed = value["lines"] > 0

    # ---- payment method via linked payments (N:N)
    active_payments = [p for p in payments if cancellation_state(p.get("Canceled")) == "VALID"]
    payment_methods = {classify_payment_method(p) for p in active_payments}
    cash_confirmed = len(active_payments) > 0
    method = "MIXED" if len(payment_methods) > 1 else (
        next(iter(payment_methods)) if payment_methods else "UNKNOWN")

    # ---- cash applied to THIS invoice (settlement authority, N:N safe)
    applied = round(float(settled_amount or 0), 4) if settled_amount else 0.0

    # ---- stock (OINM resolved to this invoice)
    goods_out = [m for m in stock if m.get("resolved")]
    goods_out_confirmed = len(goods_out) > 0
    stock_status = "GOODS_OUT_CONFIRMED" if goods_out_confirmed else STOCK_RELATION_UNRESOLVED
    warehouses = sorted({m.get("warehouse_id") for m in goods_out if m.get("warehouse_id")})
    warehouse_confirmed = len(warehouses) > 0

    # ---- cost value (independent dimension, §18); OINM.TransValue is signed
    # (negative for goods-out), the cost value itself is positive
    cost_value = round(sum(
        abs(float(m.get("cost_total") or 0)) for m in goods_out if (m.get("out_qty") or 0) > 0
    ), 4)

    # ---- differences (§21): only meaningful for cash-classified sales
    # expected_cash = gross commercial amount (DocTotal, VAT included): that is
    # what the cash register should have received. goods_sale_value (net lines)
    # is the commercial value of the goods out — a separate dimension.
    # A partial application is EXPLAINED (remaining balance of the payment
    # lifecycle); only over-application is truly unexplained (§22/§23).
    invoice_total = float(invoice.get("DocTotal") or 0)
    total_diff = None
    explained = 0.0
    unexplained = None
    if method == CASH:
        total_diff = round(invoice_total - applied, 4)
        if abs(total_diff) <= tolerance:
            explained = total_diff
            unexplained = 0.0
        elif applied < invoice_total - tolerance:
            explained = total_diff  # remaining balance, explained by lifecycle
            unexplained = 0.0
        else:
            explained = 0.0
            unexplained = total_diff

    # ---- status (§23); canceled never CONSISTENT (§31/§43)
    if canceled != "VALID":
        status = REVIEW_REQUIRED
        explanation = ["INVOICE_CANCELED_LIFECYCLE_PRESERVED"]
    elif not sale_confirmed or not invoice_confirmed:
        status = UNRESOLVED
        explanation = ["INVOICE_STATE_UNRESOLVED"]
    elif not cash_confirmed:
        status = PARTIALLY_RECONCILED
        explanation = ["CASH_MISSING"]
    elif method == CASH and not goods_out_confirmed:
        status = PARTIALLY_RECONCILED
        explanation = [STOCK_RELATION_UNRESOLVED]
    elif method == CASH and unexplained == 0 and explained == 0:
        status = CONSISTENT
        explanation = ["MATCHED"]
    elif method == CASH and unexplained == 0:
        status = PARTIALLY_RECONCILED
        explanation = ["PARTIAL_CASH_PAYMENT", f"REMAINING={total_diff}"]
    elif method == CASH:
        status = REVIEW_REQUIRED
        explanation = ["CASH_OVER_APPLIED", f"UNEXPLAINED={unexplained}"]
    elif method in ("CARD", "TRANSFER", "CHECK", "ON_ACCOUNT", "BILL_EXCHANGE"):
        status = PARTIALLY_RECONCILED
        explanation = ["PAYMENT_METHOD_NON_CASH", f"METHOD={method}"]
    elif method == MIXED:
        status = PARTIALLY_RECONCILED
        explanation = ["PAYMENT_METHOD_MIXED"]
    else:
        status = UNRESOLVED
        explanation = ["PAYMENT_METHOD_UNKNOWN"]

    return {
        "case_id": docentry,
        "invoice_number": invoice.get("DocNum"),
        "customer_id": invoice.get("CardCode"),
        "business_date": invoice.get("DocDate"),
        "currency": invoice.get("DocCur"),
        "canceled": canceled,
        "payment_method": method,
        "confirmations": {
            "SALE_CONFIRMED": sale_confirmed,
            "INVOICE_CONFIRMED": invoice_confirmed,
            "CASH_CONFIRMED": cash_confirmed,
            "GOODS_OUT_CONFIRMED": goods_out_confirmed,
            "WAREHOUSE_CONFIRMED": warehouse_confirmed,
            "COMMERCIAL_VALUE_CONFIRMED": commercial_value_confirmed,
        },
        "goods_sale_value": value["goods_sale_value"],
        "goods_cost_value": cost_value,
        "applied_amount": applied,
        "expected_cash": round(invoice_total, 4) if method == CASH else None,
        "actual_cash": applied if method == CASH else None,
        "differences": {
            "TOTAL_DIFFERENCE": total_diff,
            "EXPLAINED_DIFFERENCE": explained,
            "UNEXPLAINED_DIFFERENCE": unexplained,
        },
        "warehouses": warehouses,
        "warehouse_name": warehouse_name,
        "status": status,
        "explanation": explanation,
        "lineage": {
            "SAP_INVOICE": {"table": "OINV", "pk": docentry},
            "SAP_INVOICE_LINES": [{"table": "INV1", "pk": (docentry, ln.get("LineNum"))} for ln in lines],
            "PAYMENTS": [{"table": "ORCT", "pk": p.get("DocEntry")} for p in active_payments],
            "STOCK_MOVEMENTS": [{"table": "OINM", "pk": m.get("trans_num")} for m in goods_out],
            "WAREHOUSE": warehouses,
        },
    }