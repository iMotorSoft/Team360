"""PHASE 7/8/10 — Actual credit state × sales × payments (READ ONLY).

Universe: focus customers (5 known) + currently over-limit customers +
customers with currently-overdue invoices. For every ACTIVE invoice (sale)
since 2026-01-01 we reconstruct, with conservative lower bounds:

  prior_open  = sum of still-open invoices dated <= sale date   (LOWER BOUND)
  overdue_at_sale = any still-open invoice with due date < sale date
                    (DEFINITIVE: unpaid even today, therefore unpaid then)
  over_limit_before = prior_open > CreditLine
  over_limit_after  = prior_open + DocTotal > CreditLine

Payments: OINV -> ITR1 (SrcObjTyp=13) -> ORCT (settlement).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

EVIDENCE = EVIDENCE_ROOT / "credit_control" / "evidence"
FOCUS = ["C003542", "C008090", "C003531", "C007776", "E000043"]
WINDOW_START = date(2026, 1, 1)


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def compute_sale_states(cardcode, docs, limit, window_start):
    """Reconstruct, per ACTIVE sale in window, the customer credit state with
    conservative lower bounds (see module docstring). Pure function (testable).

    docs: list of dicts with docentry/docnum/docdate/docduedate/doctotal/
          paidtodate/canceled/usersign/u_origin/u_so1_01retailone/slpcode
    """
    import bisect

    open_docs = [d for d in docs
                 if d["canceled"] == "N" and float(d["paidtodate"] or 0) < float(d["doctotal"] or 0)]
    open_docs.sort(key=lambda x: (x["docdate"], x["docentry"]))
    open_dates = [x["docdate"] for x in open_docs]
    open_balance = [float(x["doctotal"]) - float(x["paidtodate"]) for x in open_docs]
    out = []
    for d in docs:
        if d["canceled"] != "N":
            continue
        docdate = d["docdate"].date() if hasattr(d["docdate"], "date") else d["docdate"]
        if docdate < window_start:
            continue
        # strictly-earlier open invoices: exclude the sale itself (lower bound)
        idx = bisect.bisect_left(open_dates, d["docdate"])
        prior_open = sum(open_balance[:idx])
        overdue_amt = sum(
            b for x, b in zip(open_docs[:idx], open_balance[:idx])
            if x["docduedate"] < d["docdate"]
        )
        doc_total = float(d["doctotal"])
        out.append({
            "cardcode": cardcode,
            "docentry": d["docentry"],
            "docnum": d["docnum"],
            "docdate": str(d["docdate"]),
            "docduedate": str(d["docduedate"]),
            "doctotal": round(doc_total, 2),
            "paidtodate": round(float(d["paidtodate"] or 0), 2),
            "open_now": round(doc_total - float(d["paidtodate"] or 0), 2),
            "usersign": d["usersign"],
            "origin": d["u_origin"],
            "retailone": d["u_so1_01retailone"],
            "slpcode": d["slpcode"],
            "creditline": limit,
            "prior_open_bound": round(prior_open, 2),
            "overdue_at_sale": overdue_amt > 0,
            "overdue_count_at_sale": sum(
                1 for x, b in zip(open_docs[:idx], open_balance[:idx])
                if x["docduedate"] < d["docdate"] and b > 0),
            "overdue_amount_at_sale": round(overdue_amt, 2),
            "over_limit_before": limit > 0 and prior_open > limit,
            "over_limit_after": limit > 0 and (prior_open + doc_total) > limit,
        })
    return out


def main() -> int:
    conn, cur = connect()
    try:
        # universe of customers
        focus = rows(cur, 'SELECT "CardCode","CreditLine","Balance","U_SO1_01VENCREVENC" AS u_vencrevenc, "U_CANAL_VENTAS", "Block", "PaymBlock" FROM "TELCHI"."OCRD" WHERE "CardCode" IN (%s)' %
                    ",".join(["?"] * len(FOCUS)), FOCUS)
        over = rows(cur, 'SELECT "CardCode","CreditLine","Balance" FROM "TELCHI"."OCRD" WHERE "CardType"=\'C\' AND "CreditLine" > 0 AND "Balance" > "CreditLine"')
        overdue_cust = [r["cardcode"] for r in rows(cur,
            'SELECT DISTINCT "CardCode" FROM "TELCHI"."OINV" WHERE "CANCELED"=\'N\' AND "PaidToDate" < "DocTotal" AND "DocDueDate" < CURRENT_DATE')]
        # internal "control tributario" / owner accounts are excluded from the
        # commercial universe (fiscal auxiliary documents, not third-party sales)
        INTERNAL_PREFIX = ("CGCM", "CG2A", "CGCT", "CGEC", "S000")
        universe = sorted(set(
            [r["cardcode"] for r in focus] + [r["cardcode"] for r in over] + overdue_cust))
        universe = [c for c in universe if not c.startswith(INTERNAL_PREFIX)]
        ocrd = {r["cardcode"]: r for r in focus + over}
        ocrd_full = rows(cur, '''SELECT "CardCode","CreditLine","Balance" FROM "TELCHI"."OCRD" WHERE "CardCode" IN (%s)''' %
                         ",".join(["?"] * len(universe)), universe)
        ocrd = {r["cardcode"]: r for r in ocrd_full}

        # invoices of the universe
        inv = rows(cur, '''SELECT "DocEntry","DocNum","CardCode","DocDate","DocDueDate",
            "DocTotal","PaidToDate","CANCELED","UserSign","U_ORIGIN","U_SO1_01RETAILONE","SlpCode"
            FROM "TELCHI"."OINV" WHERE "CardCode" IN (%s) AND "DocDate" >= '2024-01-01'
            ORDER BY "CardCode","DocDate"''' % ",".join(["?"] * len(universe)), universe)
        print("universe customers:", len(universe), "| invoices fetched:", len(inv))

        by_cc: dict[str, list[dict]] = defaultdict(list)
        for r in inv:
            by_cc[r["cardcode"]].append(r)

        sales = []
        for cc, docs in by_cc.items():
            limit = float(ocrd.get(cc, {}).get("creditline") or 0)
            sales.extend(compute_sale_states(cc, docs, limit, WINDOW_START))

        # summarize
        total_sales = len(sales)
        by_channel = Counter()
        overdue_sales = [s for s in sales if s["overdue_at_sale"]]
        over_limit_sales = [s for s in sales if s["over_limit_before"] or s["over_limit_after"]]
        for s in sales:
            ch = "RETAIL_ONE" if (s["origin"] == "SAP" and s["retailone"] == "Y") else (
                "DMS" if s["origin"] == "DMS" else "SAP_DIRECT" if s["origin"] == "SAP" else s["origin"])
            by_channel[ch] += 1

        exec_cases = sorted(
            [s for s in sales if s["overdue_at_sale"]],
            key=lambda s: (s["cardcode"], s["docdate"]),
        )[0:400]

        (EVIDENCE / "phase78_sale_credit_state.json").write_text(
            json.dumps({
                "universe_customers": len(universe),
                "sales_in_window": total_sales,
                "channel_distribution": dict(by_channel),
                "sales_with_overdue_at_sale": len(overdue_sales),
                "sales_over_limit_before_or_after": len(over_limit_sales),
                "all_overdue_sales": [s for s in overdue_sales],
            }, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

        print("sales in window:", total_sales, "| channel:", dict(by_channel))
        print("sales while CUSTOMER HAD overdue unpaid invoice at sale date:", len(overdue_sales))
        print("sales over limit (before/after):", len(over_limit_sales))
        by_cc_overdue = Counter(s["cardcode"] for s in overdue_sales)
        print("by customer (overdue-at-sale):", dict(by_cc_overdue.most_common(10)))

        # payment trace for the first N overdue sales (ITR1->ORCT)
        trace_targets = sorted({(s["docentry"]) for s in exec_cases})
        pay = rows(cur, '''SELECT t."SrcObjAbs" AS invoice_entry, t."ReconNum",
            o."DocEntry" AS pay_entry, o."DocNum" AS pay_num, o."DocDate" AS pay_date,
            o."DocTotal" AS pay_total, o."CardCode", o."UserSign" AS pay_user
            FROM "TELCHI"."ITR1" t
            JOIN "TELCHI"."ORCT" o ON o."DocEntry" = t."ReconNum"
            WHERE t."SrcObjTyp" = '13' AND t."SrcObjAbs" IN (%s)''' %
            ",".join(["?"] * len(trace_targets)), trace_targets)
        pay_by_inv: dict[int, list] = defaultdict(list)
        for p in pay:
            pay_by_inv[p["invoice_entry"]].append(p)
        traced = []
        for s in exec_cases:
            ps = pay_by_inv.get(s["docentry"], [])
            traced.append({**s, "payments": [
                {"pay_entry": p["pay_entry"], "pay_num": p["pay_num"], "pay_date": str(p["pay_date"]),
                 "pay_total": round(float(p["pay_total"] or 0), 2), "pay_user": p["pay_user"]} for p in ps
            ]})
        (EVIDENCE / "phase78_traceable_sales.json").write_text(
            json.dumps(traced, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        paid = sum(1 for t in traced if t["payments"])
        print("overdue-at-sale sales traced:", len(traced), "| with payments:", paid)
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
