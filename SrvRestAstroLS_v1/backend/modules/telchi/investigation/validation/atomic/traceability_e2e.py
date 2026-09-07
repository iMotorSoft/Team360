#!/usr/bin/env python3
"""E2E traceability runner — SALE x CASH x STOCK over real HANA data.

Gate: TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1
Window: 2023-02 (SAP era; Retail One active — U_SO1_01RETAILONE 86.2%).
Strict READ ONLY. Never aggregates as primary proof: every case is atomic
and keeps SAP lineage (OINV.DocEntry / INV1.DocEntry+LineNum / ORCT.DocEntry
/ OINM.TransNum / WhsCode).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

import pandas

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.atomic import connection as hconn
from modules.telchi.investigation.atomic.traceability import build_case, STOCK_RELATION_UNRESOLVED
from modules.telchi.investigation.atomic.semantic.payment import classify_payment_method

WINDOW = ("2023-02-01", "2023-03-01")
OUT = ROOT / "validation" / "atomic" / "traceability_e2e_report.json"


def load_sql(name: str) -> str:
    return (ROOT / "sql" / "current" / "atomic" / name).read_text(encoding="utf-8")


def fetch(cur, sql: str, params=None) -> pandas.DataFrame:
    cur.execute(sql, params or ())
    cols = [d[0] for d in (cur.description or ())]
    return pandas.DataFrame(cur.fetchall(), columns=cols)


def main() -> int:
    try:
        conn, cur = hconn.connect()
    except Exception as e:
        print("STOP_MANUAL_PODMAN_START_REQUIRED:", str(e)[:120])
        return 3

    try:
        start, end = WINDOW

        # ---- invoices (OINV) + lines (INV1)
        inv = fetch(cur, f'''
            SELECT "DocEntry","DocNum","CardCode","DocDate","DocTotal","DocCur",
                   "CANCELED","DocStatus","PaidToDate","U_SO1_01RETAILONE",
                   "U_SO1_01FOLIORETAIL1","U_ORIGIN","U_MPAGO_SIN"
            FROM TELCHI."OINV"
            WHERE "DocDate" >= ? AND "DocDate" < ?''', WINDOW)
        lines = fetch(cur, f'''
            SELECT "DocEntry","LineNum","ItemCode","Quantity","Price",
                   "DiscPrcnt","LineTotal","WhsCode","BaseType","BaseEntry"
            FROM TELCHI."INV1"
            WHERE "DocEntry" IN (SELECT "DocEntry" FROM TELCHI."OINV"
                                 WHERE "DocDate" >= ? AND "DocDate" < ?)''', WINDOW)

        # ---- settlement (ITR1/OITR active) + payments (ORCT)
        sett = fetch(cur, f'''
            SELECT ITR1."ReconNum", ITR1."SrcObjTyp", ITR1."SrcObjAbs", ITR1."ReconSum"
            FROM TELCHI."ITR1" AS ITR1
            INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
            WHERE OITR."Canceled" = 'N'
              AND OITR."ReconDate" >= ? AND OITR."ReconDate" < ?''', WINDOW)
        pay = fetch(cur, f'''
            SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCurr","Canceled",
                   "CashSum","CheckSum","TrsfrSum","CreditSum","NoDocSum","BoeSum"
            FROM TELCHI."ORCT"
            WHERE "DocEntry" IN (
                SELECT DISTINCT ITR1."SrcObjAbs" FROM TELCHI."ITR1" AS ITR1
                INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
                WHERE ITR1."SrcObjTyp" = 24 AND OITR."Canceled" = 'N'
                  AND OITR."ReconDate" >= ? AND OITR."ReconDate" < ?)''', WINDOW)

        # ---- stock (OINM -> document, DOCNUM_RESOLVE branch, window)
        stock_sql = load_sql("relation_stock_document.sql")
        n_sd = stock_sql.count(":start_date")
        stock = fetch(cur,
                      stock_sql.replace(":start_date", "?").replace(":end_date", "?"),
                      tuple(p for _ in range(n_sd) for p in WINDOW))

        # ---- warehouse lookup
        whs = fetch(cur, 'SELECT "WhsCode","WhsName" FROM TELCHI."OWHS"')
        whs_name = dict(zip(whs["WhsCode"], whs["WhsName"]))

        # ---- cost evidence (OINM TransValue/CalcPrice, READ ONLY)
        oinm_cost = fetch(cur, f'''
            SELECT "TransNum","TransValue","CalcPrice","OutQty"
            FROM TELCHI."OINM"
            WHERE "DocDate" >= ? AND "DocDate" <= ?''', WINDOW)
        cost_by_trans = {r["TransNum"]: r for _, r in oinm_cost.iterrows()}
    finally:
        cur.close()
        conn.close()

    # ---- indexes
    lines_by_inv = defaultdict(list)
    for _, r in lines.iterrows():
        lines_by_inv[r["DocEntry"]].append(r.to_dict())

    # payment per settlement: invoice <- recon <- payment
    recon_members = defaultdict(list)
    for _, r in sett.iterrows():
        recon_members[r["ReconNum"]].append(r)
    pay_by_doc = {r["DocEntry"]: r.to_dict() for _, r in pay.iterrows()}
    pay_of_invoice = defaultdict(list)
    settled_of_invoice = defaultdict(float)
    for r in recon_members.values():
        inv_members = [m for m in r if str(m["SrcObjTyp"]) == "13"]
        pay_members = [m for m in r if str(m["SrcObjTyp"]) == "24"]
        for im in inv_members:
            settled_of_invoice[im["SrcObjAbs"]] += float(im["ReconSum"] or 0)
            for pm in pay_members:
                if pay_by_doc.get(pm["SrcObjAbs"]):
                    pay_of_invoice[im["SrcObjAbs"]].append(pay_by_doc[pm["SrcObjAbs"]])

    # stock resolved per invoice
    stock_of_invoice = defaultdict(list)
    for _, r in stock.iterrows():
        if pandas.notna(r.get("from_document_id")) and r.get("from_object_type") == "AR_INVOICE":
            c = cost_by_trans.get(r["to_document_id"], {})
            stock_of_invoice[int(r["from_document_id"])].append({
                "trans_num": r["to_document_id"], "trans_type": r["trans_type"],
                "itemcode": r["item_id"], "in_qty": r["in_qty"], "out_qty": r["out_qty"],
                "warehouse_id": r["warehouse_id"], "resolved": True,
                "confidence": r["confidence"],
                "cost_total": abs(c.get("TransValue")) if c.get("TransValue") is not None else None,
                "calc_price": c.get("CalcPrice"),
            })

    # ---- build atomic cases
    cases = []
    for _, row in inv.iterrows():
        docentry = row["DocEntry"]
        case = build_case(
            invoice=row.to_dict(),
            lines=lines_by_inv.get(docentry, []),
            payments=pay_of_invoice.get(docentry, []),
            stock=stock_of_invoice.get(docentry, []),
            settled_amount=settled_of_invoice.get(docentry, 0.0),
        )
        whs_codes = case["warehouses"]
        case["warehouse_name"] = whs_name.get(whs_codes[0]) if whs_codes else None
        case["channel"] = "RETAIL_ONE" if row["U_SO1_01RETAILONE"] == "Y" else (
            "DMS" if row["U_ORIGIN"] == "DMS" else "SAP")
        cases.append(case)

    # ---- distributions
    status_dist = Counter(c["status"] for c in cases)
    conf_matrix = {k: Counter(c["confirmations"][k] for c in cases) for k in
                   ("SALE_CONFIRMED", "INVOICE_CONFIRMED", "CASH_CONFIRMED",
                    "GOODS_OUT_CONFIRMED", "WAREHOUSE_CONFIRMED",
                    "COMMERCIAL_VALUE_CONFIRMED")}
    method_dist = Counter(c["payment_method"] for c in cases)
    channel_dist = Counter(c["channel"] for c in cases)

    # ---- daily + warehouse aggregation (control only, never primary proof)
    daily = defaultdict(lambda: {"cash_sales_value": 0.0, "actual_cash": 0.0,
                                 "cases": 0, "review": 0})
    for c in cases:
        if c["status"] == "CONSISTENT" or c["status"] == "REVIEW_REQUIRED":
            day = str(c["business_date"])[:10]
            wh = c["warehouse_name"] or (c["warehouses"][0] if c["warehouses"] else "?")
            d = daily[(day, wh)]
            d["cases"] += 1
            if c["expected_cash"] is not None:
                d["cash_sales_value"] += c["expected_cash"]
            if c["actual_cash"] is not None:
                d["actual_cash"] += c["actual_cash"]
            if c["status"] == "REVIEW_REQUIRED":
                d["review"] += 1

    # ---- top unexplained differences
    diffs = []
    for c in cases:
        u = (c.get("differences") or {}).get("UNEXPLAINED_DIFFERENCE")
        if u not in (None, 0.0):
            diffs.append((abs(u), c))
    diffs.sort(key=lambda t: t[0], reverse=True)

    # ---- 25 E2E sample with full lineage
    consistent = [c for c in cases if c["status"] == "CONSISTENT"]
    sample = (consistent[:25] if len(consistent) >= 25
              else [c for c in cases if c["status"] != "SOURCE_DATA_MISSING"][:25])

    report = {
        "gate": "TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1",
        "window": list(WINDOW),
        "hanna_read_only": True,
        "cases_total": len(cases),
        "status_distribution": dict(status_dist),
        "confirmation_matrix": {k: dict(v) for k, v in conf_matrix.items()},
        "payment_method_distribution": dict(method_dist),
        "channel_distribution": dict(channel_dist),
        "daily_warehouse_aggregation": {
            f"{day} {wh}": d for (day, wh), d in sorted(daily.items())
        },
        "top_unexplained": [
            {
                "case_id": c["case_id"], "invoice_number": c["invoice_number"],
                "customer_id": c["customer_id"], "date": str(c["business_date"])[:10],
                "expected_cash": c["expected_cash"], "actual_cash": c["actual_cash"],
                "unexplained": c["differences"]["UNEXPLAINED_DIFFERENCE"],
                "method": c["payment_method"], "status": c["status"],
            } for _, c in diffs[:15]
        ],
        "e2e_sample": sample,
    }
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"E2E cases: {len(cases)}")
    print("status:", dict(status_dist))
    print("methods:", dict(method_dist))
    print("channels:", dict(channel_dist))
    print("conf:", {k: dict(v) for k, v in conf_matrix.items()})
    print("top unexplained:", len(diffs))
    print("report:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())