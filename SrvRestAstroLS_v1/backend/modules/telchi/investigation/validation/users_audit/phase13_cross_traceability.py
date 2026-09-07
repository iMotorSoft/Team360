"""PHASE 13 — Cross Sales/Cash/Stock/Accounting traceability (READ ONLY).

Reconstructs full atomic business-traceability cases per SAP user:
  SAP USER -> SALE -> CASH -> STOCK -> ACCOUNTING

Uses the validated semantics from prior gates:
  - Settlement: ITR1.SrcObjTyp=13/24, SrcObjAbs=DocEntry, ReconNum
  - Stock: OINM.BASE_REF = DocNum (DOCNUM_RESOLVE), or ApplObj>0
  - Accounting: ORCT.TransId -> OJDT.TransId -> JDT1 (debit/credit)

Produces AtomicUserBusinessTraceabilityCase with DocEntry/DocNum evidence.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

from modules.telchi.investigation.atomic.connection import connect


def find_complete_cases(cursor: Any, user_id: int, window: tuple[str, str], limit: int = 20) -> list[dict[str, Any]]:
    """Find invoices for a user that have settlement AND stock in the window."""
    cursor.execute(
        '''SELECT O."DocEntry", O."DocNum", O."DocTotal", O."DocDate", O."CardCode",
                  O."CardName", O."SlpCode", O."CANCELED", O."Series", O."U_ORIGIN",
                  (SELECT COUNT(*) FROM "TELCHI"."ITR1" L WHERE L."SrcObjTyp"=13 AND L."SrcObjAbs"=O."DocEntry") AS settle_cnt,
                  (SELECT COUNT(*) FROM "TELCHI"."OINM" M WHERE M."BASE_REF"=O."DocNum") AS stock_cnt
           FROM "TELCHI"."OINV" O
           WHERE O."UserSign"=? AND O."CANCELED"='N'
             AND O."DocDate" >= ? AND O."DocDate" <= ?
             AND (SELECT COUNT(*) FROM "TELCHI"."ITR1" L WHERE L."SrcObjTyp"=13 AND L."SrcObjAbs"=O."DocEntry") > 0
             AND (SELECT COUNT(*) FROM "TELCHI"."OINM" M WHERE M."BASE_REF"=O."DocNum") > 0
           ORDER BY O."DocDate" DESC
           LIMIT ?''',
        (user_id, window[0], window[1], limit),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def get_settlement(cursor: Any, doc_entry: int) -> list[dict[str, Any]]:
    cursor.execute(
        '''SELECT L."ReconNum", L."SrcObjTyp", L."SrcObjAbs", L."ReconSum",
                  R."ReconDate", R."Canceled", R."Total", R."ReconType"
           FROM "TELCHI"."ITR1" L JOIN "TELCHI"."OITR" R ON R."ReconNum"=L."ReconNum"
           WHERE L."SrcObjTyp"=13 AND L."SrcObjAbs"=?''',
        (doc_entry,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def get_payment_from_recon(cursor: Any, recon_num: int) -> list[dict[str, Any]]:
    cursor.execute(
        '''SELECT L."SrcObjTyp", L."SrcObjAbs", L."ReconSum",
                  P."DocEntry", P."DocNum", P."DocDate", P."DocTotal", P."Canceled", P."TransId", P."UserSign"
           FROM "TELCHI"."ITR1" L
           LEFT JOIN "TELCHI"."ORCT" P ON P."DocEntry" = L."SrcObjAbs"
           WHERE L."ReconNum"=? AND L."SrcObjTyp"=24''',
        (recon_num,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def get_stock(cursor: Any, doc_num: str) -> list[dict[str, Any]]:
    cursor.execute(
        '''SELECT "TransNum", "TransType", "ItemCode", "InQty", "OutQty",
                  "Warehouse", "UserSign", "DocDate", "BASE_REF", "DocLineNum"
           FROM "TELCHI"."OINM" WHERE "BASE_REF"=?''',
        (doc_num,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def get_accounting(cursor: Any, trans_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        '''SELECT J."TransId", J."TransType", J."UserSign", J."Memo",
                  D."Account", D."Debit", D."Credit", D."Line_ID", D."ContraAct"
           FROM "TELCHI"."OJDT" J LEFT JOIN "TELCHI"."JDT1" D ON D."TransId"=J."TransId"
           WHERE J."TransId"=?''',
        (trans_id,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def build_case(cursor: Any, user_id: int, user_code: str, invoice: dict[str, Any]) -> dict[str, Any]:
    de = invoice["DocEntry"]
    doc_num = str(invoice["DocNum"])

    settlements = get_settlement(cursor, de)
    payments = []
    for s in settlements:
        payments.extend(get_payment_from_recon(cursor, s["ReconNum"]))

    stock = get_stock(cursor, doc_num)

    # accounting via first payment TransId
    accounting = []
    trans_ids = [p["TransId"] for p in payments if p.get("TransId")]
    for tid in trans_ids[:3]:
        accounting.extend(get_accounting(cursor, tid))

    return {
        "user": user_code,
        "sale": {
            "obj_type": 13,
            "doc_entry": de,
            "doc_num": invoice["DocNum"],
            "amount": str(invoice["DocTotal"]),
            "date": str(invoice["DocDate"])[:10],
            "card_code": invoice["CardCode"],
            "slp_code": invoice["SlpCode"],
            "origin": invoice["U_ORIGIN"],
            "series": invoice["Series"],
        },
        "cash": [
            {
                "payment_doc_entry": p.get("DocEntry"),
                "payment_doc_num": p.get("DocNum"),
                "applied_amount": str(p.get("ReconSum")),
                "canceled": p.get("Canceled"),
                "trans_id": p.get("TransId"),
                "payment_user": p.get("UserSign"),
            }
            for p in payments if p.get("DocEntry") is not None
        ],
        "stock": [
            {
                "document": s["TransNum"],
                "item": s["ItemCode"],
                "in_qty": str(s["InQty"]),
                "out_qty": str(s["OutQty"]),
                "warehouse": s["Warehouse"],
                "user": s["UserSign"],
            }
            for s in stock
        ],
        "accounting": [
            {
                "trans_id": a["TransId"],
                "account": a["Account"],
                "debit": str(a["Debit"]),
                "credit": str(a["Credit"]),
                "user": a["UserSign"],
            }
            for a in accounting if a.get("Account") is not None
        ],
        "settlement_count": len(settlements),
    }


def classify_case(case: dict[str, Any]) -> str:
    has_sale = case["sale"] is not None
    has_cash = len(case["cash"]) > 0
    has_stock = len(case["stock"]) > 0
    has_acct = len(case["accounting"]) > 0
    if has_sale and has_cash and has_stock and has_acct:
        return "FULLY_TRACED"
    if has_sale and has_cash and has_acct:
        return "SALE_CASH_ACCOUNTING_CONFIRMED"
    if has_sale and has_stock:
        return "SALE_STOCK_CONFIRMED"
    if has_sale and has_cash:
        return "SALE_CASH_CONFIRMED"
    if has_sale:
        return "SALE_ONLY"
    return "UNRESOLVED"


def main() -> int:
    conn, cur = connect()
    try:
        # priority user: eroman
        cur.execute('SELECT "USERID", "USER_CODE" FROM "TELCHI"."OUSR" WHERE "USER_CODE"=\'eroman\'')
        eroman = cur.fetchone()
        eroman_id, eroman_code = eroman[0], eroman[1]

        window = ("2023-02-01", "2023-02-28")
        cases = find_complete_cases(cur, eroman_id, window, limit=10)

        built = []
        for inv in cases:
            case = build_case(cur, eroman_id, eroman_code, inv)
            case["status"] = classify_case(case)
            built.append(case)

        # user-span check: which stages did eroman personally touch?
        results = {
            "phase": "CROSS_TRACEABILITY",
            "user": eroman_code,
            "window": window,
            "total_complete_cases": len(built),
            "status_distribution": defaultdict(int),
            "cases": built,
        }
        for c in built:
            results["status_distribution"][c["status"]] += 1

        print(json.dumps(results, indent=2, default=str))
        print(f"\nPHASE 13 — eroman cross-traceability ({window[0]}..{window[1]})")
        print(f"  Complete cases found: {len(built)}")
        for st, n in sorted(results["status_distribution"].items()):
            print(f"    {st:<32} {n}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
