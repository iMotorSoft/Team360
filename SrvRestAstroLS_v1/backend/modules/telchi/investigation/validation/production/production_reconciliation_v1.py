"""TELCHI_PRODUCTION_RECONCILIATION_V1 — validator (READ ONLY on HANA).

Executes the production reconciliation gate against real SAP with batch fetch:
  1. Expected for plan vs expected normalized to actual output
  2. Reclassification matrix (plan -> normalized)
  3. Output completion ratio
  4. Produced component context (without expanding upstream recipes)
  5. Systematic patterns (L00099, L02475) after normalization
  6. Zero-output / rework special populations
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.production_reconciliation_domain import build_line
from modules.telchi.investigation.validation.production.output_traceability_domain import fetch_receipts_batch


def run_reconciliation(cur: Any, orders_limit: int | None = None) -> dict[str, Any]:
    """Batch reconciliation over production orders."""
    limit_sql = f" LIMIT {orders_limit}" if orders_limit else ""
    cur.execute(
        f'''SELECT "DocEntry","DocNum","ItemCode","PlannedQty","CmpltQty","Status"
            FROM "TELCHI"."OWOR" WHERE "Type"='S'{limit_sql}''')
    orders = cur.fetchall()
    order_ids = [o[0] for o in orders]

    # receipts (output)
    _, receipts_by_order = fetch_receipts_batch(cur, order_ids)

    # consumption per order line
    ph = ",".join("?" * len(order_ids))
    cur.execute(
        f'''SELECT "BaseEntry","BaseLine","ItemCode",SUM("Quantity")
            FROM "TELCHI"."IGE1" WHERE "BaseType"=202 AND "BaseEntry" IN ({ph})
            GROUP BY "BaseEntry","BaseLine","ItemCode"''', order_ids)
    cons_by_key = {(r[0], r[1], r[2]): Decimal(str(r[3])) for r in cur.fetchall()}

    # WOR1 lines
    cur.execute(
        f'''SELECT "DocEntry","LineNum","ItemCode","BaseQtyNum","BaseQtyDen","IssueType"
            FROM "TELCHI"."WOR1" WHERE "DocEntry" IN ({ph})''', order_ids)
    wor1_by_order = defaultdict(list)
    for r in cur.fetchall():
        wor1_by_order[r[0]].append(r)

    # produced components: items with actual output
    cur.execute('''SELECT DISTINCT O."ItemCode" FROM "TELCHI"."OWOR" O
      WHERE EXISTS (SELECT 1 FROM "TELCHI"."IGN1" N WHERE N."BaseType"=202 AND N."BaseEntry"=O."DocEntry")''')
    produced_items = {r[0] for r in cur.fetchall()}

    # produced component parent count
    cur.execute('''SELECT W."ItemCode", COUNT(DISTINCT O."ItemCode")
      FROM "TELCHI"."WOR1" W JOIN "TELCHI"."OWOR" O ON O."DocEntry"=W."DocEntry"
      GROUP BY W."ItemCode"''')
    parent_count = {r[0]: r[1] for r in cur.fetchall()}

    plan_cls = Counter()
    norm_cls = Counter()
    reclass = Counter()
    output_ratio_buckets = Counter()
    component_patterns: dict[str, Counter] = defaultdict(Counter)
    top_norm_over = []
    top_norm_under = []
    lines_total = 0
    produced_comp_lines = 0

    for o in orders:
        de, docnum, parent, planned, cmplt, status = o[0], o[1], o[2], o[3], o[4], o[5]
        planned = Decimal(str(planned))
        receipts = receipts_by_order.get(de, [])
        actual_out = sum((Decimal(str(r[5])) for r in receipts), Decimal(0))

        if planned > 0:
            ratio = float(actual_out / planned)
            if actual_out == 0:
                output_ratio_buckets["0"] += 1
            elif ratio < 1:
                output_ratio_buckets["0-1"] += 1
            elif abs(ratio - 1) < 0.001:
                output_ratio_buckets["1"] += 1
            else:
                output_ratio_buckets[">1"] += 1

        for w in wor1_by_order.get(de, []):
            line, comp, num, den, method = w[1], w[2], w[3], w[4], w[5]
            cons = cons_by_key.get((de, line, comp), Decimal(0))
            is_pc = comp in produced_items
            l = build_line(
                (de, docnum, parent, planned),
                (line, comp, num, den, method),
                actual_out, cons,
                is_produced_component=is_pc,
                produced_parent_count=parent_count.get(comp, 0),
            )
            lines_total += 1
            if is_pc:
                produced_comp_lines += 1
            plan_cls[l.plan_classification] += 1
            norm_cls[l.normalized_classification] += 1
            reclass[(l.plan_classification, l.normalized_classification)] += 1
            component_patterns[comp][l.normalized_classification] += 1

            d = l.to_dict()
            if l.normalized_classification == "OVER":
                top_norm_over.append(d)
            elif l.normalized_classification == "UNDER":
                top_norm_under.append(d)

    def sort_abs(lst):
        return sorted(lst, key=lambda x: abs(float(x["normalized_variance_qty"]) or 0), reverse=True)

    return {
        "orders_total": len(orders),
        "component_lines_total": lines_total,
        "produced_component_lines": produced_comp_lines,
        "plan_classification": dict(plan_cls),
        "normalized_classification": dict(norm_cls),
        "reclassification_matrix": {f"{k[0]}->{k[1]}": v for k, v in sorted(reclass.items())},
        "output_ratio_buckets": dict(output_ratio_buckets),
        "top_normalized_over": sort_abs(top_norm_over)[:12],
        "top_normalized_under": sort_abs(top_norm_under)[:12],
        "component_patterns_sample": {
            c: dict(cnt) for c, cnt in list(component_patterns.items())[:0]
        },
    }


def component_patterns_full(cur: Any) -> dict[str, Any]:
    """Normalized variance pattern for key components (L00099, L02475, L01945, L00001)."""
    cur.execute(
        '''SELECT O."DocEntry", O."DocNum", O."ItemCode", O."PlannedQty", N.out_qty,
                  W."LineNum", W."ItemCode", W."BaseQtyNum", W."BaseQtyDen", I.cons_qty
           FROM "TELCHI"."OWOR" O
           JOIN (SELECT "BaseEntry", SUM("Quantity") AS out_qty FROM "TELCHI"."IGN1" WHERE "BaseType"=202 GROUP BY "BaseEntry") N
             ON N."BaseEntry"=O."DocEntry"
           JOIN "TELCHI"."WOR1" W ON W."DocEntry"=O."DocEntry"
           LEFT JOIN (SELECT "BaseEntry","BaseLine","ItemCode",SUM("Quantity") AS cons_qty
             FROM "TELCHI"."IGE1" WHERE "BaseType"=202 GROUP BY "BaseEntry","BaseLine","ItemCode") I
             ON I."BaseEntry"=O."DocEntry" AND I."BaseLine"=W."LineNum" AND I."ItemCode"=W."ItemCode"
           WHERE O."Type"='S' AND W."ItemCode" IN ('L00099','L02475','L01945','L00001')''')
    patterns: dict[str, dict] = {}
    for r in cur.fetchall():
        comp = r[6]
        planned = Decimal(str(r[3])); out = Decimal(str(r[4]))
        num = Decimal(str(r[7])); den = Decimal(str(r[8])) if r[8] else Decimal(1)
        cons = Decimal(str(r[9])) if r[9] else Decimal(0)
        exp_norm = num / den * out
        var = cons - exp_norm
        pct = float(var / exp_norm * 100) if exp_norm != 0 else None
        patterns.setdefault(comp, {"lines": 0, "exact": 0, "over": 0, "under": 0,
                                   "over_abs_total": Decimal(0), "over_fixed_values": Counter(),
                                   "sample_over": []})
        p = patterns[comp]
        p["lines"] += 1
        if abs(var) <= Decimal("0.001"):
            p["exact"] += 1
        elif var > 0:
            p["over"] += 1
            p["over_abs_total"] += var
            p["over_fixed_values"][str(var.quantize(Decimal("1")))] += 1
            if len(p["sample_over"]) < 6:
                p["sample_over"].append({"order": r[0], "parent": r[2],
                                         "planned_out": str(r[3]), "actual_out": str(r[4]),
                                         "exp_norm": str(exp_norm), "cons": str(cons),
                                         "var": str(var), "pct": round(pct, 2) if pct else None})
        else:
            p["under"] += 1
    out = {}
    for comp, p in patterns.items():
        out[comp] = {
            "lines": p["lines"], "exact": p["exact"], "over": p["over"], "under": p["under"],
            "over_rate_pct": round(100 * p["over"] / p["lines"], 1) if p["lines"] else 0,
            "over_abs_total": str(p["over_abs_total"]),
            "over_fixed_values_top": dict(p["over_fixed_values"].most_common(8)),
            "sample_over": p["sample_over"],
        }
    return out


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_PRODUCTION_RECONCILIATION_V1",
            "reconciliation": run_reconciliation(cur),
            "component_patterns": component_patterns_full(cur),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_PRODUCTION_RECONCILIATION_V1")
        print(f"{'='*70}")
        r = result["reconciliation"]
        print(f"\nRECONCILIATION ({r['orders_total']} orders, {r['component_lines_total']} lines):")
        print(f"  PLAN classification: {r['plan_classification']}")
        print(f"  NORMALIZED classification: {r['normalized_classification']}")
        print(f"\n  RECLASSIFICATION MATRIX:")
        for k, v in sorted(r["reclassification_matrix"].items()):
            print(f"    {k:<30} {v:,}")
        print(f"\n  OUTPUT RATIO: {r['output_ratio_buckets']}")
        print(f"\nCOMPONENT PATTERNS (post-normalization):")
        for comp, p in result["component_patterns"].items():
            print(f"  {comp}: lines={p['lines']} exact={p['exact']} over={p['over']} "
                  f"under={p['under']} over_rate={p['over_rate_pct']}%")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())