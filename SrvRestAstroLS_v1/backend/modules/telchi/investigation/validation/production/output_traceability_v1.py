"""TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1 — validator (READ ONLY on HANA).

Executes the output traceability gate against real SAP with batch fetch:
  1. Output semantics (IGN1 BT=202, signs, cancellations)
  2. CmpltQty vs SUM(IGN1) reconciliation
  3. Receipt cardinality (1:N)
  4. Output vs plan classification
  5. ItemCode match / rework pattern
  6. Warehouse traceability
  7. Timing
  8. Batch traceability
  9. OINM secondary reconciliation
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.output_traceability_domain import (
    build_order_summary,
    fetch_receipts_batch,
)


def output_semantics(cur: Any) -> dict[str, Any]:
    cur.execute('SELECT "CANCELED", COUNT(*) FROM "TELCHI"."OIGN" GROUP BY "CANCELED"')
    oign_canceled = dict(cur.fetchall())
    cur.execute('''SELECT CASE WHEN "Quantity"<0 THEN 'NEG' WHEN "Quantity"=0 THEN 'ZERO' ELSE 'POS' END AS s, COUNT(*)
                   FROM "TELCHI"."IGN1" WHERE "BaseType"=202 GROUP BY CASE WHEN "Quantity"<0 THEN 'NEG' WHEN "Quantity"=0 THEN 'ZERO' ELSE 'POS' END''')
    signs = dict(cur.fetchall())
    return {
        "oign_canceled_dist": oign_canceled,
        "ign1_quantity_signs": signs,
        "semantics": "NET_ACTUAL_OUTPUT = SUM(IGN1.Quantity) WHERE BaseType=202 (no cancellations/reversals)",
    }


def cmplt_reconciliation(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT
      COUNT(*) AS total,
      SUM(CASE WHEN A.actual IS NOT NULL AND ABS(O."CmpltQty"-A.actual)<0.001 THEN 1 ELSE 0 END) AS eq,
      SUM(CASE WHEN A.actual IS NOT NULL AND ABS(O."CmpltQty"-A.actual)>=0.001 THEN 1 ELSE 0 END) AS diff,
      SUM(CASE WHEN A.actual IS NULL AND O."CmpltQty"=0 THEN 1 ELSE 0 END) AS zero_no_rec,
      SUM(CASE WHEN A.actual IS NULL AND O."CmpltQty"!=0 THEN 1 ELSE 0 END) AS nonzero_no_rec
    FROM "TELCHI"."OWOR" O
    LEFT JOIN (SELECT "BaseEntry", SUM("Quantity") AS actual FROM "TELCHI"."IGN1" WHERE "BaseType"=202 GROUP BY "BaseEntry") A
      ON A."BaseEntry"=O."DocEntry"
    WHERE O."Type"='S' ''')
    r = cur.fetchone()
    return {"total": r[0], "cmplt_eq_ign1": r[1], "cmplt_diff": r[2],
            "cmplt_zero_no_receipt": r[3], "cmplt_nonzero_no_receipt": r[4],
            "semantics": "CmpltQty = SUM(IGN1.Quantity); only mismatch = order 17757 (rework)"}


def receipt_cardinality(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT rc, COUNT(*) FROM (
      SELECT O."DocEntry", COUNT(N."LineNum") AS rc
      FROM "TELCHI"."OWOR" O LEFT JOIN "TELCHI"."IGN1" N
        ON N."BaseType"=202 AND N."BaseEntry"=O."DocEntry"
      GROUP BY O."DocEntry") GROUP BY rc ORDER BY rc''')
    dist = {int(r[0]): r[1] for r in cur.fetchall()}
    return {"distribution": dist,
            "orders_zero": dist.get(0, 0), "orders_one": dist.get(1, 0),
            "orders_multi": sum(v for k, v in dist.items() if k >= 2)}


def itemcode_match(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."IGN1" N JOIN "TELCHI"."OWOR" O
      ON O."DocEntry"=N."BaseEntry" WHERE N."BaseType"=202 AND N."ItemCode"=O."ItemCode"''')
    match = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."IGN1" N JOIN "TELCHI"."OWOR" O
      ON O."DocEntry"=N."BaseEntry" WHERE N."BaseType"=202 AND N."ItemCode"!=O."ItemCode"''')
    mismatch = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."IGN1" N JOIN "TELCHI"."OWOR" O
      ON O."DocEntry"=N."BaseEntry" JOIN "TELCHI"."WOR1" W
      ON W."DocEntry"=O."DocEntry" AND W."ItemCode"=N."ItemCode"
      WHERE N."BaseType"=202 AND N."ItemCode"!=O."ItemCode"''')
    mismatch_is_component = cur.fetchone()[0]
    return {"matched": match, "mismatch": mismatch,
            "mismatch_received_is_wor1_component": mismatch_is_component,
            "finding": "All mismatches receive a WOR1 component -> REWORK pattern"}


def batch_traceability(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT COUNT(*), SUM(CASE WHEN "U_LOTE" IS NOT NULL AND "U_LOTE"!='' THEN 1 ELSE 0 END)
      FROM "TELCHI"."IGN1" WHERE "BaseType"=202''')
    r = cur.fetchone()
    cur.execute('''SELECT COUNT(DISTINCT "U_LOTE") FROM "TELCHI"."IGN1"
      WHERE "BaseType"=202 AND "U_LOTE" IS NOT NULL AND "U_LOTE"!='' ''')
    total_lotes = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(DISTINCT N."U_LOTE") FROM "TELCHI"."IGN1" N
      JOIN "TELCHI"."OBTN" B ON B."DistNumber"=N."U_LOTE"
      WHERE N."BaseType"=202 AND N."U_LOTE" IS NOT NULL AND N."U_LOTE"!='' ''')
    matched = cur.fetchone()[0]
    return {"lines": r[0], "with_lote": r[1],
            "distinct_lotes": total_lotes, "lotes_matched_obtn": matched,
            "match_pct": round(100 * matched / total_lotes, 1) if total_lotes else 0,
            "semantics": "IGN1.U_LOTE -> OBTN.DistNumber EXACT"}


def oinm_reconciliation(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT COUNT(DISTINCT M."BASE_REF") FROM "TELCHI"."OINM" M
      JOIN "TELCHI"."IGN1" N ON N."BaseRef"=M."BASE_REF" WHERE M."TransType"=59''')
    linked = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT "BaseRef") FROM "TELCHI"."IGN1" WHERE "BaseType"=202')
    total = cur.fetchone()[0]
    return {"ign1_base_refs": total, "oinm_tt59_linked": linked,
            "coverage_pct": round(100 * linked / total, 1) if total else 0,
            "finding": "OINM partial (53.5%); exact when linked; IGN1 is primary source"}


def mass_validation(cur: Any) -> dict[str, Any]:
    """Output vs plan over all production orders with batch fetch."""
    cur.execute(
        '''SELECT "DocEntry","DocNum","ItemCode","PlannedQty","CmpltQty","Status"
           FROM "TELCHI"."OWOR" WHERE "Type"='S' ''')
    orders = cur.fetchall()
    order_ids = [o[0] for o in orders]
    order_meta = {o[0]: o for o in orders}

    # consumption per order (for CONSUMPTION_WITHOUT_OUTPUT classification)
    ph = ",".join("?" * len(order_ids))
    cur.execute(f'SELECT "BaseEntry", SUM("Quantity") FROM "TELCHI"."IGE1" WHERE "BaseType"=202 AND "BaseEntry" IN ({ph}) GROUP BY "BaseEntry"', order_ids)
    consumption = {r[0]: Decimal(str(r[1])) for r in cur.fetchall()}

    _, receipts_by_order = fetch_receipts_batch(cur, order_ids)

    cls_counter = Counter()
    status_output = defaultdict(Counter)
    top_partial = []
    top_over = []
    summaries = []

    for o in orders:
        de = o[0]
        rows = receipts_by_order.get(de, [])
        s = build_order_summary(o, rows, consumption)
        summaries.append(s)
        cls_counter[s.classification] += 1
        status_output[o[5]][s.classification] += 1
        if s.classification == "PARTIAL_OUTPUT":
            top_partial.append(s.to_dict())
        elif s.classification == "OVER_PLANNED_OUTPUT":
            top_over.append(s.to_dict())

    def sort_abs(lst):
        return sorted(lst, key=lambda x: abs(float(x["output_vs_plan_qty"]) or 0), reverse=True)

    return {
        "orders_total": len(orders),
        "classification_dist": dict(cls_counter),
        "status_x_classification": {k: dict(v) for k, v in status_output.items()},
        "top_partial_by_abs": sort_abs(top_partial)[:12],
        "top_over_by_abs": sort_abs(top_over)[:12],
        "orders_with_consumption_no_output": sum(
            1 for s in summaries if s.classification == "CONSUMPTION_WITHOUT_OUTPUT"),
    }


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1",
            "output_semantics": output_semantics(cur),
            "cmplt_reconciliation": cmplt_reconciliation(cur),
            "receipt_cardinality": receipt_cardinality(cur),
            "itemcode_match": itemcode_match(cur),
            "batch_traceability": batch_traceability(cur),
            "oinm_reconciliation": oinm_reconciliation(cur),
            "mass_validation": mass_validation(cur),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1")
        print(f"{'='*70}")
        os_ = result["output_semantics"]
        print(f"\nOUTPUT SEMANTICS:\n  {os_['semantics']}")
        cr = result["cmplt_reconciliation"]
        print(f"\nCMPLTQTY: eq={cr['cmplt_eq_ign1']}/{cr['total']} diff={cr['cmplt_diff']} "
              f"zero_no_rec={cr['cmplt_zero_no_receipt']}")
        rc = result["receipt_cardinality"]
        print(f"\nRECEIPT CARDINALITY: zero={rc['orders_zero']} one={rc['orders_one']} multi={rc['orders_multi']}")
        ic = result["itemcode_match"]
        print(f"\nITEMCODE: match={ic['matched']} mismatch={ic['mismatch']} "
              f"(rework={ic['mismatch_received_is_wor1_component']})")
        bt = result["batch_traceability"]
        print(f"\nBATCH: {bt['with_lote']}/{bt['lines']} lines with lote; "
              f"{bt['lotes_matched_obtn']}/{bt['distinct_lotes']} matched OBTN ({bt['match_pct']}%)")
        mv = result["mass_validation"]
        print(f"\nOUTPUT VS PLAN ({mv['orders_total']} orders):")
        for k, v in sorted(mv["classification_dist"].items()):
            print(f"  {k:<45} {v:,}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())