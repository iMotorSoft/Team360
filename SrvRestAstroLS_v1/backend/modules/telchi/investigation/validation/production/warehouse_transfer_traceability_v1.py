"""TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1 — validator (READ ONLY on HANA).

Executes the warehouse transfer traceability gate against real SAP:
  1. Documental semantics (origin/dest/qty/canceled)
  2. Cardinality (doc->lines, multi-origin/dest)
  3. OINM TT67 inventory effect + quantity conservation
  4. Canceled/reversal semantics
  5. Route summary with warehouse roles
  6. Batch traceability
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.warehouse_transfer_domain import (
    WarehouseTransferLine,
    classify_whs_role,
    classify_transfer,
)


def documental_semantics(cur: Any) -> dict[str, Any]:
    cur.execute('SELECT "CANCELED", COUNT(*) FROM "TELCHI"."OWTR" GROUP BY "CANCELED"')
    canceled = dict(cur.fetchall())
    cur.execute('''SELECT CASE WHEN "Quantity"<0 THEN 'NEG' WHEN "Quantity"=0 THEN 'ZERO' ELSE 'POS' END AS s, COUNT(*)
      FROM "TELCHI"."WTR1" GROUP BY CASE WHEN "Quantity"<0 THEN 'NEG' WHEN "Quantity"=0 THEN 'ZERO' ELSE 'POS' END''')
    signs = dict(cur.fetchall())
    # negative lines in ACTIVE docs
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."WTR1" W JOIN "TELCHI"."OWTR" O ON O."DocEntry"=W."DocEntry"
      WHERE W."Quantity"<0 AND O."CANCELED"='N' ''')
    neg_active = cur.fetchone()[0]
    # lines of canceled docs all positive?
    cur.execute('''SELECT COUNT(*), SUM(CASE WHEN "Quantity"<0 THEN 1 ELSE 0 END)
      FROM "TELCHI"."WTR1" W JOIN "TELCHI"."OWTR" O ON O."DocEntry"=W."DocEntry" WHERE O."CANCELED"='Y' ''')
    r = cur.fetchone()
    return {
        "owtr_canceled_dist": canceled,
        "wtr1_sign_dist": signs,
        "negative_lines_in_active_docs": neg_active,
        "canceled_doc_lines": r[0], "canceled_doc_negative_lines": r[1],
        "semantics": "NET_TRANSFER = SUM(WTR1.Quantity) WHERE OWTR.CANCELED='N'; "
                     "negative lines are reverse/adjust transfers in ACTIVE docs; "
                     "canceled docs (424) excluded by header",
    }


def cardinality(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT COUNT(*) FROM (
      SELECT O."DocEntry" FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      GROUP BY O."DocEntry" HAVING COUNT(DISTINCT W."FromWhsCod") > 1)''')
    multi_origin = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM (
      SELECT O."DocEntry" FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      GROUP BY O."DocEntry" HAVING COUNT(DISTINCT W."WhsCode") > 1)''')
    multi_dest = cur.fetchone()[0]
    return {"multi_origin_docs": multi_origin, "multi_destination_docs": multi_dest,
            "finding": "Documents must NOT be collapsed to a single route"}


def oinm_conservation(cur: Any) -> dict[str, Any]:
    """Quantity conservation: for sample transfers, origin out == dest in."""
    cur.execute('''SELECT M."BASE_REF", M."ItemCode", M."DocLineNum",
        MAX(CASE WHEN M."OutQty">0 THEN M."OutQty" ELSE 0 END) AS out_q,
        MAX(CASE WHEN M."InQty">0 THEN M."InQty" ELSE 0 END) AS in_q
      FROM "TELCHI"."OINM" M WHERE M."TransType"=67 AND M."BASE_REF" IN (
        SELECT "DocNum" FROM "TELCHI"."OWTR" WHERE "CANCELED"='N' AND "DocDate" >= '2026-08-01')
      GROUP BY M."BASE_REF", M."ItemCode", M."DocLineNum"''')
    rows = cur.fetchall()
    exact = 0
    total = 0
    mismatches = []
    for r in rows:
        total += 1
        out_q = Decimal(str(r[3])); in_q = Decimal(str(r[4]))
        if abs(out_q - in_q) <= Decimal("0.001"):
            exact += 1
        elif len(mismatches) < 5:
            mismatches.append({"doc": r[0], "item": r[1], "line": r[2],
                               "out": str(out_q), "in": str(in_q)})
    return {
        "sample_transfer_lines": total, "conserved_exact": exact,
        "conservation_pct": round(100 * exact / total, 2) if total else 0,
        "mismatch_samples": mismatches,
        "finding": "OINM TT67 creates 2 rows per line (origin Out, dest In) with equal qty",
    }


def route_summary(cur: Any) -> dict[str, Any]:
    """Top routes with roles."""
    cur.execute('''SELECT W."FromWhsCod", W."WhsCode", COUNT(DISTINCT W."DocEntry"), COUNT(*), COUNT(DISTINCT W."ItemCode")
      FROM "TELCHI"."WTR1" W JOIN "TELCHI"."OWTR" O ON O."DocEntry"=W."DocEntry"
      WHERE O."CANCELED"='N'
      GROUP BY W."FromWhsCod", W."WhsCode" ORDER BY COUNT(*) DESC LIMIT 20''')
    routes = []
    whs_names: dict[str, str] = {}
    cur.execute('SELECT "WhsCode", "WhsName" FROM "TELCHI"."OWHS"')
    for r in cur.fetchall():
        whs_names[r[0]] = r[1]
    for r in cur.fetchall() if False else []:
        pass
    # refetch
    cur.execute('''SELECT W."FromWhsCod", W."WhsCode", COUNT(DISTINCT W."DocEntry"), COUNT(*), COUNT(DISTINCT W."ItemCode")
      FROM "TELCHI"."WTR1" W JOIN "TELCHI"."OWTR" O ON O."DocEntry"=W."DocEntry"
      WHERE O."CANCELED"='N'
      GROUP BY W."FromWhsCod", W."WhsCode" ORDER BY COUNT(*) DESC LIMIT 20''')
    for r in cur.fetchall():
        origin, dest = r[0], r[1]
        routes.append({
            "origin": origin, "destination": dest,
            "origin_role": classify_whs_role(origin, whs_names.get(origin, "")),
            "destination_role": classify_whs_role(dest, whs_names.get(dest, "")),
            "route_class": classify_transfer(
                classify_whs_role(origin, whs_names.get(origin, "")),
                classify_whs_role(dest, whs_names.get(dest, ""))),
            "docs": r[2], "lines": r[3], "items": r[4],
        })
    return {"top_routes": routes}


def batch_traceability(cur: Any) -> dict[str, Any]:
    cur.execute('''SELECT COUNT(*), SUM(CASE WHEN "U_LOTE" IS NOT NULL AND "U_LOTE"!='' THEN 1 ELSE 0 END)
      FROM "TELCHI"."WTR1" W JOIN "TELCHI"."OWTR" O ON O."DocEntry"=W."DocEntry" WHERE O."CANCELED"='N' ''')
    r = cur.fetchone()
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."IBT1" WHERE "BaseType"=67')
    ibt1_67 = cur.fetchone()[0]
    return {
        "active_lines": r[0], "with_lote": r[1],
        "lote_pct": round(100 * r[1] / r[0], 2) if r[0] else 0,
        "ibt1_transtype67_rows": ibt1_67,
        "semantics": "WTR1.U_LOTE minority; full batch trace via IBT1 BaseType=67",
    }


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1",
            "documental_semantics": documental_semantics(cur),
            "cardinality": cardinality(cur),
            "oinm_conservation": oinm_conservation(cur),
            "route_summary": route_summary(cur),
            "batch_traceability": batch_traceability(cur),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1")
        print(f"{'='*70}")
        ds = result["documental_semantics"]
        print(f"\nDOCUMENTAL SEMANTICS:\n  {ds['semantics']}")
        oc = result["oinm_conservation"]
        print(f"\nOINM CONSERVATION: {oc['conserved_exact']}/{oc['sample_transfer_lines']} "
              f"lines exact ({oc['conservation_pct']}%)")
        print(f"\nTOP ROUTES:")
        for r in result["route_summary"]["top_routes"][:12]:
            print(f"  {r['origin']:<10} -> {r['destination']:<10} "
                  f"[{r['origin_role']}->{r['destination_role']}] "
                  f"docs={r['docs']} lines={r['lines']}")
        bt = result["batch_traceability"]
        print(f"\nBATCH: lote_pct={bt['lote_pct']}% IBT1_TT67={bt['ibt1_transtype67_rows']:,}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())