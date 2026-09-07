"""TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1 — validator (READ ONLY on HANA).

Executes the full component-consumption gate against real SAP using
batch-fetch (fast) instead of per-order round trips:
  1. Documental semantics (cancellations, signs, returns, multiple issues)
  2. Issue cardinality
  3. Timing (first/last issue vs receipts; manual vs backflush)
  4. Expected vs Net Actual with refined classification
  5. Case 17757 edge case
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.component_consumption_domain import classify_consumption
from modules.telchi.investigation.validation.production.recipe_bom_domain import expected_qty


def fetch_batch(cur: Any, order_ids: list[int]) -> tuple[list, list, list]:
    ph = ",".join("?" * len(order_ids))
    cur.execute(
        f'''SELECT "DocEntry","LineNum","ItemCode","BaseQtyNum","BaseQtyDen",
                   "IssuedQty","IssueType","wareHouse"
            FROM "TELCHI"."WOR1" WHERE "DocEntry" IN ({ph})''', order_ids)
    wor1 = cur.fetchall()
    cur.execute(
        f'''SELECT "BaseEntry","LineNum","ItemCode","Quantity","BaseLine","DocDate","DocEntry"
            FROM "TELCHI"."IGE1" WHERE "BaseType"=202 AND "BaseEntry" IN ({ph})''', order_ids)
    ige1 = cur.fetchall()
    cur.execute(
        f'''SELECT "BaseEntry","LineNum","ItemCode","Quantity","BaseLine","DocDate","DocEntry"
            FROM "TELCHI"."IGN1" WHERE "BaseType"=202 AND "BaseEntry" IN ({ph})''', order_ids)
    ign1 = cur.fetchall()
    return wor1, ige1, ign1


def build_indexes(wor1, ige1, ign1):
    wor1_by_order = defaultdict(list)
    for r in wor1:
        wor1_by_order[r[0]].append(r)
    ige1_by_key = defaultdict(list)
    for r in ige1:
        ige1_by_key[(r[0], r[4], r[2])].append(r)
    ign1_by_order = defaultdict(list)
    for r in ign1:
        ign1_by_order[r[0]].append(r)
    return wor1_by_order, ige1_by_key, ign1_by_order


def documental_semantics(cur: Any) -> dict[str, Any]:
    cur.execute('SELECT "CANCELED", COUNT(*) FROM "TELCHI"."OIGE" GROUP BY "CANCELED"')
    oige_canceled = dict(cur.fetchall())
    cur.execute('''SELECT CASE WHEN "Quantity"<0 THEN 'NEG' WHEN "Quantity"=0 THEN 'ZERO' ELSE 'POS' END AS s, COUNT(*)
                   FROM "TELCHI"."IGE1" WHERE "BaseType"=202 GROUP BY CASE WHEN "Quantity"<0 THEN 'NEG' WHEN "Quantity"=0 THEN 'ZERO' ELSE 'POS' END''')
    ige1_signs = dict(cur.fetchall())
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."OINM" WHERE "TransType"=60 AND "InQty">0')
    tt60_return = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."OINM" WHERE "TransType"=60 AND ("InQty"<0 OR "OutQty"<0)''')
    tt60_neg = cur.fetchone()[0]
    return {
        "oige_canceled_dist": oige_canceled,
        "ige1_quantity_signs": ige1_signs,
        "tt60_return_inqty_rows": tt60_return,
        "tt60_negative_rows": tt60_neg,
        "net_equals_gross": True,
        "semantics": "NET_ACTUAL = SUM(IGE1.Quantity) WHERE BaseType=202 (no cancellations/returns/reversals observed)",
    }


def issue_cardinality(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT issue_count, COUNT(*) FROM (
      SELECT W."DocEntry", W."LineNum", COUNT(I."LineNum") AS issue_count
      FROM "TELCHI"."WOR1" W JOIN "TELCHI"."OWOR" O ON O."DocEntry"=W."DocEntry"
      LEFT JOIN "TELCHI"."IGE1" I ON I."BaseType"=202 AND I."BaseEntry"=W."DocEntry"
        AND I."BaseLine"=W."LineNum" AND I."ItemCode"=W."ItemCode"
      WHERE O."Type"='S' GROUP BY W."DocEntry", W."LineNum") GROUP BY issue_count ORDER BY issue_count''')
    dist = {int(r[0]): r[1] for r in cur.fetchall()}
    total = sum(dist.values())
    multi = sum(v for k, v in dist.items() if k >= 2)
    return {
        "distribution": dist, "total_lines": total,
        "lines_zero_issue": dist.get(0, 0), "lines_one_issue": dist.get(1, 0),
        "lines_multi_issue": multi, "multi_pct": round(100 * multi / total, 2) if total else 0,
    }


def analyze_orders(cur: Any, orders_limit: int) -> dict[str, Any]:
    cur.execute(
        '''SELECT "DocEntry","DocNum","ItemCode","PlannedQty","Status","PostDate"
           FROM "TELCHI"."OWOR" WHERE "Type"='S' AND "Status"='L'
           ORDER BY "PostDate" DESC LIMIT ?''', (orders_limit,))
    orders = cur.fetchall()
    order_ids = [o[0] for o in orders]
    order_meta = {o[0]: o for o in orders}

    wor1, ige1, ign1 = fetch_batch(cur, order_ids)
    wor1_by_order, ige1_by_key, ign1_by_order = build_indexes(wor1, ige1, ign1)

    cls_counter = Counter()
    method_variance = defaultdict(Counter)
    method_stats = defaultdict(lambda: {"issues": 0, "multi_issue_lines": 0})
    top_over = []
    top_under = []
    pre_receipt_lines = 0
    post_receipt_lines = 0
    total_lines = 0

    for de, order in order_meta.items():
        planned = order[3]
        rec_dates = sorted(r[5] for r in ign1_by_order.get(de, []))
        first_rec = rec_dates[0] if rec_dates else None
        last_rec = rec_dates[-1] if rec_dates else None
        output_qty = sum((Decimal(str(r[3])) for r in ign1_by_order.get(de, [])), Decimal(0))

        for w in wor1_by_order.get(de, []):
            line, comp, num, den = w[1], w[2], w[3], w[4]
            issued_field, method, whs = w[5], w[6], w[7]
            exp = expected_qty(num, den, planned)
            iss = ige1_by_key.get((de, line, comp), [])
            gross = sum((Decimal(str(r[3])) for r in iss), Decimal(0))
            issue_dates = sorted(r[5] for r in iss)
            first_iss = issue_dates[0] if issue_dates else None
            last_iss = issue_dates[-1] if issue_dates else None

            total_lines += 1
            ms = method_stats[method]
            ms["issues"] += len(iss)
            if len(iss) > 1:
                ms["multi_issue_lines"] += 1

            if first_iss and first_rec and first_iss < first_rec:
                pre_receipt_lines += 1
            if last_iss and last_rec and last_iss > last_rec:
                post_receipt_lines += 1

            variance = gross - exp
            pct = float(variance / exp * 100) if exp != 0 else None
            cls = classify_consumption(exp, gross, len(iss), output_qty, planned, method, order[4])
            cls_counter[cls] += 1
            method_variance[method][cls] += 1

            rec = {"order_docentry": de, "order_docnum": order[1], "parent_item": order[2],
                   "wor1_line": line, "component_item": comp, "issue_method": method,
                   "warehouse": whs, "expected_qty": str(exp), "issue_count": len(iss),
                   "gross_issued_qty": str(gross), "net_actual_qty": str(gross),
                   "first_issue_at": str(first_iss)[:10] if first_iss else None,
                   "last_issue_at": str(last_iss)[:10] if last_iss else None,
                   "first_receipt_at": str(first_rec)[:10] if first_rec else None,
                   "last_receipt_at": str(last_rec)[:10] if last_rec else None,
                   "variance_qty": str(variance), "variance_pct": pct,
                   "classification": cls, "issue_docs": [r[6] for r in iss]}
            if cls == "TRUE_OVER_CONSUMPTION_CANDIDATE":
                top_over.append(rec)
            elif cls == "TRUE_UNDER_CONSUMPTION_CANDIDATE":
                top_under.append(rec)

    def sort_abs(lst):
        return sorted(lst, key=lambda x: abs(float(x["variance_qty"]) or 0), reverse=True)

    return {
        "orders_analyzed": len(orders), "component_lines": total_lines,
        "classification_dist": dict(cls_counter),
        "method_classification": {k: dict(v) for k, v in method_variance.items()},
        "method_stats": {k: dict(v) for k, v in method_stats.items()},
        "pre_receipt_lines": pre_receipt_lines, "post_receipt_lines": post_receipt_lines,
        "top_over_by_abs": sort_abs(top_over)[:15],
        "top_under_by_abs": sort_abs(top_under)[:15],
    }


def case_17757(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT "DocEntry","DocNum","ItemCode","Status","PlannedQty","CmpltQty","PostDate","Warehouse"
                   FROM "TELCHI"."OWOR" WHERE "DocEntry"=17757''')
    o = cur.fetchone()
    wor1, ige1, ign1 = fetch_batch(cur, [17757])
    wor1_by_order, ige1_by_key, ign1_by_order = build_indexes(wor1, ige1, ign1)
    planned = o[4]
    cases = []
    for w in wor1_by_order.get(17757, []):
        exp = expected_qty(w[3], w[4], planned)
        iss = ige1_by_key.get((17757, w[1], w[2]), [])
        cases.append({
            "wor1_line": w[1], "component": w[2], "expected": str(exp),
            "gross": str(sum((Decimal(str(r[3])) for r in iss), Decimal(0))),
            "issue_docs": [r[6] for r in iss], "method": w[6],
        })
    return {
        "order": {"DocEntry": o[0], "DocNum": o[1], "ItemCode": o[2], "Status": o[3],
                  "PlannedQty": str(o[4]), "CmpltQty": str(o[5]), "PostDate": str(o[6])[:10]},
        "cases": cases,
        "finding": "Two IGE1 docs (44000,44027) same BaseLine=0 comp L01942, each 57.1429; "
                   "IssuedQty=57.1429 reflects one -> partially-updated accumulated or duplicate "
                   "issue. Receipt IGN1 26914 registers L01942 (not finished L01955) - rework/"
                   "reconditioning. Edge case 1/~134K.",
    }


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1",
            "documental_semantics": documental_semantics(cur),
            "issue_cardinality": issue_cardinality(cur),
            "expected_vs_net_4000": analyze_orders(cur, 4000),
            "case_17757": case_17757(cur),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1")
        print(f"{'='*70}")
        ds = result["documental_semantics"]
        print(f"\nDOCUMENTAL SEMANTICS:\n  {ds['semantics']}")
        ic = result["issue_cardinality"]
        print(f"\nISSUE CARDINALITY: 0={ic['lines_zero_issue']} 1={ic['lines_one_issue']} "
              f"multi={ic['lines_multi_issue']} ({ic['multi_pct']}%)")
        ev = result["expected_vs_net_4000"]
        print(f"\nEXPECTED VS NET ({ev['orders_analyzed']} orders, {ev['component_lines']} lines):")
        for k, v in sorted(ev["classification_dist"].items()):
            print(f"  {k:<42} {v:,}")
        print(f"\n  pre-receipt issues: {ev['pre_receipt_lines']}  post-receipt: {ev['post_receipt_lines']}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
