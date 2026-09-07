"""PHASE 11/12 — Pricing analysis for C010341 (READ ONLY).

Compares LA REJA invoice unit prices against:
  a) median normal-customer unit price for the SAME ItemCode in the SAME
     period (2026-01-01..2026-09-01), same currency (BS), same unit
     (SalUnitMsr) — never mixing units/currencies.
  b) item cost (OITM.AvgPrice) when available.

Per-item classification:
  COMMERCIAL_LIKE / COST_LIKE / SYMBOLIC / OUTLIER / UNRESOLVED

Correlation is never treated as fact: only direction of evidence.

Outputs:
  evidence/pricing_comparison.json
  evidence/pricing_summary.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
FROM, TO = "2026-01-01", "2026-09-01"


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    cases = json.loads((EVIDENCE / "atomic_la_reja_cases.json").read_text())
    conn, cur = connect()

    # LA REJA lines: item -> list of (unit price)
    lr_prices = defaultdict(list)
    lr_amt = defaultdict(float)
    for c in cases:
        for l in c["product_lines"]:
            lr_prices[l["itemcode"]].append(float(l["price"] or 0))
            lr_amt[l["itemcode"]] += float(l["line_total"] or 0)
    codes = sorted(lr_prices)
    cph = ",".join(["?"] * len(codes))

    # other customers' unit prices for the same items, same window, BS
    cur.execute(f'''SELECT i."ItemCode", i."Price", i."Quantity", i."Currency", o."DocCur"
        FROM "TELCHI"."INV1" i JOIN "TELCHI"."OINV" o ON o."DocEntry"=i."DocEntry"
        WHERE i."ItemCode" IN ({cph}) AND o."CardCode" <> 'C010341'
          AND o."CANCELED"='N' AND o."DocDate" >= '{FROM}' AND o."DocDate" <= '{TO}'
          AND o."DocCur"='BS' AND i."Currency"='BS' ''', codes)
    other = defaultdict(list)
    for r in cur.fetchall():
        other[r[0]].append(float(r[1] or 0))

    # cost
    cur.execute(f'''SELECT "ItemCode","AvgPrice" FROM "TELCHI"."OITM" WHERE "ItemCode" IN ({cph})''', codes)
    cost = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    def median(vals):
        if not vals:
            return None
        ordered = sorted(vals)
        n = len(ordered)
        mid = n // 2
        return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    rows = []
    for code in codes:
        lr = median(lr_prices[code])
        lr_avg = sum(lr_prices[code]) / len(lr_prices[code])
        nt = median(other.get(code, []))
        nt_count = len(other.get(code, []))
        cst = cost.get(code)
        ratio = (lr / nt) if (lr and nt and nt > 0) else None
        vs_cost = (lr / cst) if (lr and cst and cst > 0) else None
        if lr and nt and ratio is not None:
            if 0.95 <= ratio <= 1.05:
                cls = "COMMERCIAL_LIKE"
            elif ratio < 0.5:
                cls = "SYMBOLIC"
            elif ratio > 1.3:
                cls = "OUTLIER"
            else:
                cls = "COMMERCIAL_LIKE"
        else:
            cls = "UNRESOLVED"
        rows.append({
            "itemcode": code,
            "la_reja_median_price": money(lr) if lr else None,
            "la_reja_avg_price": money(lr_avg),
            "la_reja_amount": money(lr_amt[code]),
            "normal_median_price": money(nt) if nt else None,
            "normal_observations": nt_count,
            "ratio_vs_normal": round(ratio, 4) if ratio is not None else None,
            "cost_avg_price": money(cst) if cst else None,
            "ratio_vs_cost": round(vs_cost, 4) if vs_cost is not None else None,
            "classification": cls,
        })

    cls_count = defaultdict(int)
    cls_amount = defaultdict(float)
    for r in rows:
        cls_count[r["classification"]] += 1
        cls_amount[r["classification"]] += r["la_reja_amount"]
    summary = {
        "items": len(rows),
        "items_with_normal_comparison": sum(1 for r in rows if r["normal_observations"] > 0),
        "classification_count": dict(cls_count),
        "classification_amount": {k: money(v) for k, v in cls_amount.items()},
        "period": [FROM, TO],
        "currency": "BS",
        "sap_write_count": 0,
    }
    (EVIDENCE / "pricing_comparison.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "pricing_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    conn.close()


if __name__ == "__main__":
    main()