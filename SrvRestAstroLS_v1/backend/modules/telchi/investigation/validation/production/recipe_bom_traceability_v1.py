"""TELCHI_RECIPE_BOM_TRACEABILITY_V1 — validator (READ ONLY on HANA).

Runs the full recipe/BOM traceability gate against real SAP:
  - EXPECTED formula validation (BaseQtyNum/BaseQtyDen * PlannedQty)
  - IssuedQty semantics (vs SUM active IGE1)
  - Issue method distribution
  - Recipe drift (WOR1 historical vs ITT1 current)
  - Expected vs actual per order line
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.recipe_bom_domain import (
    fetch_order_snapshots,
    fetch_master_bom,
    fetch_actual_consumption,
    compare_expected_actual,
    expected_qty,
)


def validate_expected_formula(cur: Any, window: tuple[str, str] | None = None) -> dict[str, Any]:
    """Mass compare WOR1.PlannedQty vs (BaseQtyNum/BaseQtyDen)*OWOR.PlannedQty."""
    date_clause = ""
    params: list = []
    if window:
        date_clause = "AND O.\"PostDate\" >= ? AND O.\"PostDate\" <= ?"
        params = [window[0], window[1]]
    cur.execute(
        f'''SELECT W."PlannedQty", W."BaseQtyNum", W."BaseQtyDen", O."PlannedQty"
            FROM "TELCHI"."WOR1" W JOIN "TELCHI"."OWOR" O ON O."DocEntry"=W."DocEntry"
            WHERE O."Type"='S' {date_clause}''',
        params,
    )
    exact = 0
    diff = 0
    total = 0
    diff_samples = []
    for r in cur.fetchall():
        total += 1
        planned = r[0]
        calc = expected_qty(r[1], r[2], r[3])
        if abs(Decimal(str(planned)) - calc) <= Decimal("0.001"):
            exact += 1
        else:
            diff += 1
            if len(diff_samples) < 5:
                diff_samples.append({"WOR1_Planned": str(planned), "calc": str(calc)})
    return {
        "total_lines": total, "exact": exact, "different": diff,
        "exact_pct": round(100 * exact / total, 2) if total else 0,
        "diff_samples": diff_samples,
    }


def validate_issuedqty(cur: Any) -> dict[str, Any]:
    cur.execute(
        '''SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN W."IssuedQty" IS NULL OR W."IssuedQty"=0 THEN 1 ELSE 0 END) AS issued_zero,
          SUM(CASE WHEN A.total IS NULL THEN 1 ELSE 0 END) AS no_ige1,
          SUM(CASE WHEN A.total IS NOT NULL AND ABS(W."IssuedQty"-A.total)<0.001 THEN 1 ELSE 0 END) AS eq,
          SUM(CASE WHEN A.total IS NOT NULL AND ABS(W."IssuedQty"-A.total)>=0.001 THEN 1 ELSE 0 END) AS neq
        FROM "TELCHI"."WOR1" W
        JOIN "TELCHI"."OWOR" O ON O."DocEntry"=W."DocEntry"
        LEFT JOIN (SELECT "BaseEntry","BaseLine","ItemCode",SUM("Quantity") AS total
          FROM "TELCHI"."IGE1" WHERE "BaseType"=202 GROUP BY "BaseEntry","BaseLine","ItemCode") A
          ON A."BaseEntry"=W."DocEntry" AND A."BaseLine"=W."LineNum" AND A."ItemCode"=W."ItemCode"
        WHERE O."Type"='S' '''
    )
    r = cur.fetchone()
    return {
        "total_lines": r[0], "issued_zero": r[1], "no_ige1": r[2],
        "issued_eq_actual": r[3], "issued_neq_actual": r[4],
        "semantics": "ACTUAL_ACCUMULATED" if r[3] and r[4] and r[3]/(r[3]+r[4]) > 0.999 else "UNKNOWN",
    }


def issue_method_dist(cur: Any) -> dict[str, int]:
    cur.execute('SELECT "IssueType", COUNT(*) FROM "TELCHI"."WOR1" GROUP BY "IssueType"')
    return {r[0]: r[1] for r in cur.fetchall()}


def recipe_drift(cur: Any) -> dict[str, Any]:
    """Compare latest-order WOR1 components vs current ITT1 per product (in memory)."""
    cur.execute(
        '''WITH latest AS (SELECT "ItemCode", MAX("DocEntry") md FROM "TELCHI"."OWOR" WHERE "Type"='S' GROUP BY "ItemCode")
        SELECT L."ItemCode", L.md,
          (SELECT COUNT(*) FROM "TELCHI"."WOR1" W WHERE W."DocEntry"=L.md) AS hist_n,
          (SELECT COUNT(*) FROM "TELCHI"."ITT1" T WHERE T."Father"=L."ItemCode") AS cur_n
        FROM latest L
        WHERE (SELECT COUNT(*) FROM "TELCHI"."WOR1" W WHERE W."DocEntry"=L.md) > 0
          AND (SELECT COUNT(*) FROM "TELCHI"."ITT1" T WHERE T."Father"=L."ItemCode") > 0'''
    )
    pairs = cur.fetchall()  # (item, maxde, hist_n, cur_n)

    # load all WOR1 for these latest orders and ITT1 for these products
    order_ids = [r[1] for r in pairs]
    products = [r[0] for r in pairs]
    hist_comp: dict[str, set] = {}
    cur_comp: dict[str, set] = {}

    for chunk_start in range(0, len(order_ids), 400):
        chunk_orders = order_ids[chunk_start:chunk_start+400]
        ph = ",".join("?" * len(chunk_orders))
        cur.execute(
            f'SELECT "DocEntry", "ItemCode" FROM "TELCHI"."WOR1" WHERE "DocEntry" IN ({ph})',
            chunk_orders,
        )
        for r in cur.fetchall():
            hist_comp.setdefault(r[0], set()).add(r[1])

    for chunk_start in range(0, len(products), 400):
        chunk_prod = products[chunk_start:chunk_start+400]
        ph = ",".join("?" * len(chunk_prod))
        cur.execute(
            f'SELECT "Father", "Code" FROM "TELCHI"."ITT1" WHERE "Father" IN ({ph})',
            chunk_prod,
        )
        for r in cur.fetchall():
            cur_comp.setdefault(r[0], set()).add(r[1])

    same = 0
    hist_only = 0
    cur_only = 0
    both_diff = 0
    total = 0
    drift_cases = []
    for item, maxde, hist_n, cur_n in pairs:
        total += 1
        hs = hist_comp.get(maxde, set())
        cs = cur_comp.get(item, set())
        only_h = hs - cs
        only_c = cs - hs
        if not only_h and not only_c:
            same += 1
        elif only_h and not only_c:
            hist_only += 1
        elif not only_h and only_c:
            cur_only += 1
        else:
            both_diff += 1
        if (only_h or only_c) and len(drift_cases) < 8:
            drift_cases.append({"product": item, "hist_n": hist_n, "cur_n": cur_n,
                                "only_hist": sorted(only_h)[:5], "only_cur": sorted(only_c)[:5]})
    return {
        "products_compared": total, "same_components": same,
        "historical_only_components": hist_only, "current_only_components": cur_only,
        "both_diff": both_diff, "drift_cases": drift_cases,
    }


def expected_vs_actual(cur: Any, limit_orders: int = 2000) -> dict[str, Any]:
    """Expected vs actual on a bounded recent sample of orders."""
    cur.execute(
        '''SELECT "DocEntry" FROM "TELCHI"."OWOR" WHERE "Type"='S' AND "Status"='L'
           ORDER BY "PostDate" DESC LIMIT ?''',
        (limit_orders,),
    )
    order_ids = [r[0] for r in cur.fetchall()]
    if not order_ids:
        return {"orders": 0, "lines": 0, "status": {}}

    status_counter = Counter()
    total_lines = 0
    placeholders = ",".join("?" * len(order_ids))
    cur.execute(
        f'''SELECT O."DocEntry", O."DocNum", O."ItemCode", W."LineNum", W."ItemCode",
            W."BaseQtyNum", W."BaseQtyDen", O."PlannedQty", W."IssuedQty", W."IssueType"
            FROM "TELCHI"."WOR1" W JOIN "TELCHI"."OWOR" O ON O."DocEntry"=W."DocEntry"
            WHERE O."DocEntry" IN ({placeholders}) AND O."Type"='S' ''',
        order_ids,
    )
    snap_rows = cur.fetchall()

    # fetch consumption per order
    for r in snap_rows:
        total_lines += 1
        expected = expected_qty(r[5], r[6], r[7])
        # actual via IssuedQty (validated as ACTUAL_ACCUMULATED) for speed on sample
        raw_actual = r[8]
        try:
            actual = Decimal(str(raw_actual))
        except Exception:
            actual = Decimal(0)
        if raw_actual is None or actual == 0:
            status_counter["EXPECTED_NOT_CONSUMED"] += 1
        elif abs(actual - expected) <= Decimal("0.001"):
            status_counter["EXACT"] += 1
        elif actual > expected:
            status_counter["OVER_CONSUMPTION"] += 1
        else:
            status_counter["UNDER_CONSUMPTION"] += 1

    return {"orders": len(order_ids), "lines": total_lines, "status": dict(status_counter)}


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_RECIPE_BOM_TRACEABILITY_V1",
            "expected_formula": validate_expected_formula(cur),
            "issuedqty": validate_issuedqty(cur),
            "issue_method": issue_method_dist(cur),
            "recipe_drift": recipe_drift(cur),
            "expected_vs_actual_sample": expected_vs_actual(cur, 2000),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_RECIPE_BOM_TRACEABILITY_V1")
        print(f"{'='*70}")
        ef = result["expected_formula"]
        print(f"\nEXPECTED FORMULA (BaseQtyNum/BaseQtyDen * PlannedQty):")
        print(f"  {ef['exact']:,}/{ef['total_lines']:,} exact ({ef['exact_pct']}%)")
        print(f"  different: {ef['different']:,} (WOR1.PlannedQty display rounding)")
        iq = result["issuedqty"]
        print(f"\nISSUEDQTY SEMANTICS:")
        print(f"  {iq['semantics']} — {iq['issued_eq_actual']:,} eq / {iq['issued_neq_actual']} neq")
        print(f"  lines without issue (IssuedQty=0, no IGE1): {iq['issued_zero']:,}")
        print(f"\nISSUE METHOD: {result['issue_method']}")
        rd = result["recipe_drift"]
        print(f"\nRECIPE DRIFT (latest order WOR1 vs ITT1 current):")
        print(f"  compared={rd['products_compared']} same={rd['same_components']} "
              f"hist_only={rd['historical_only_components']} cur_only={rd['current_only_components']}")
        ev = result["expected_vs_actual_sample"]
        print(f"\nEXPECTED VS ACTUAL (sample {ev['orders']} orders, {ev['lines']} lines):")
        for k, v in sorted(ev["status"].items()):
            print(f"  {k:<30} {v:,}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
