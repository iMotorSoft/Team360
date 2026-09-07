"""PHASE 21/22 — Credit limit vs overdue universes + exposure reconstruction.

Recomputes the CONSERVATIVE over-limit universe (prior gate method: exposure
from invoices still open TODAY dated <= sale date) and joins the EXACT as-of
reconstruction. Emits evidence/credit_limit_cases.json.

For each over-limit case:
  creditline, exposure_before (exact as-of), sale amount, exposure_after,
  excess = exposure_after - creditline (if >0), overdue_at_sale flag,
  classification reason.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"
WINDOW_START = date(2026, 1, 1)
WINDOW_END = date(2026, 9, 1)


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def to_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def main() -> int:
    conn, cur = connect()
    try:
        cases = json.loads((EVIDENCE / "revalidated_cases.json").read_text(encoding="utf-8"))
        cardcodes = sorted({c["cardcode"] for c in cases})
        ph = ",".join(["?"] * len(cardcodes))
        inv = rows(cur, f'''SELECT "DocEntry","CardCode","DocDate","DocDueDate","DocTotal","PaidToDate"
            FROM "TELCHI"."OINV" WHERE "CardCode" IN ({ph}) AND "CANCELED"='N' ''', cardcodes)
        # ALL sales in window for the universe (not only overdue-at-sale)
        window_sales = rows(cur, f'''SELECT "DocEntry","CardCode","DocDate","DocDueDate","DocTotal","PaidToDate"
            FROM "TELCHI"."OINV"
            WHERE "CardCode" IN ({ph}) AND "CANCELED"='N'
              AND "DocDate" >= '2026-01-01' AND "DocDate" <= '2026-09-01' ''', cardcodes)
        ocrd = rows(cur, f'''SELECT "CardCode","CreditLine" FROM "TELCHI"."OCRD" WHERE "CardCode" IN ({ph})''', cardcodes)
        ocrd_map = {r["cardcode"]: float(r["creditline"] or 0) for r in ocrd}
        by_cc = defaultdict(list)
        for r in inv:
            by_cc[r["cardcode"]].append(r)
        # conservative exposure (open TODAY) for each sale in window
        cl = json.loads((EVIDENCE / "classified_cases.json").read_text(encoding="utf-8"))
        cl_map = {(c["cardcode"], c["docentry"]): c for c in cl}

        conservative = []
        for s in window_sales:
            cc = s["cardcode"]
            sd = to_date(s["docdate"])
            if sd is None or sd < WINDOW_START or sd > WINDOW_END:
                continue
            limit = ocrd_map.get(cc, 0.0)
            cons_expo = sum(
                max(float(r["doctotal"]) - float(r["paidtodate"] or 0), 0.0)
                for r in by_cc.get(cc, []) if to_date(r["docdate"]) and to_date(r["docdate"]) <= sd
                and r["docentry"] != s["docentry"])
            if limit > 0 and (cons_expo > limit or cons_expo + float(s["doctotal"]) > limit):
                conservative.append({
                    "cardcode": cc, "docentry": s["docentry"],
                    "docdate": str(s["docdate"])[:10], "doctotal": round(float(s["doctotal"]), 2),
                    "conservative_exposure": round(cons_expo, 2),
                })

        exact_over = [c for c in cl if c.get("over_limit_before") or c.get("over_limit_after")]
        prior_39_keys = {(x["cardcode"], x["docentry"]) for x in conservative}
        # intersection with the 287 overdue baseline
        prior_cases = json.loads(
            (EVIDENCE.parent.parent / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
            .read_text(encoding="utf-8"))["all_overdue_sales"]
        prior287 = {(s["cardcode"], s["docentry"]) for s in prior_cases}
        out = []
        for c in conservative:
            x = cl_map.get((c["cardcode"], c["docentry"]), {})
            out.append({
                "cardcode": c["cardcode"], "docentry": c["docentry"],
                "docdate": c["docdate"], "doctotal": c["doctotal"],
                "creditline": ocrd_map.get(c["cardcode"], 0.0),
                "conservative_exposure_before": c["conservative_exposure"],
                "exact_exposure_before": x.get("exposure_before"),
                "exposure_after": round((x.get("exposure_before") or 0) + c["doctotal"], 2),
                "overdue_at_sale": x.get("overdue_at_sale"),
                "in_baseline_287": (c["cardcode"], c["docentry"]) in prior287,
                "reason_code": x.get("reason_code"), "confidence": x.get("confidence"),
                "warning": x.get("warning"),
            })
        (EVIDENCE / "credit_limit_cases.json").write_text(json.dumps({
            "conservative_over_limit_baseline": len(conservative),
            "baseline_within_287": sum(1 for o in out if o["in_baseline_287"]),
            "exact_over_limit_reconstruction": len(exact_over),
            "overdue_and_over_limit_exact": sum(1 for c in exact_over if c.get("overdue_at_sale")),
            "cases": out,
        }, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("conservative over-limit baseline:", len(conservative), "| within 287:", sum(1 for o in out if o["in_baseline_287"]))
        print("exact over-limit:", len(exact_over), "| overdue && over-limit:", sum(1 for c in exact_over if c.get("overdue_at_sale")))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())