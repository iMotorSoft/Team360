"""PHASE 10 — Sale → payment trace via OITR/ORCT (READ ONLY).

Correct SAP B1 chain used:
  OINV.DocEntry --ITR1(SrcObjTyp=13, SrcObjAbs)--> OITR.ReconNum
      --OITR(InitObjTyp=24, InitObjAbs=ORCT.DocEntry)--> ORCT payment

Reconciliations may cover multiple invoices; ITR1.ReconSum is the applied
amount for the specific invoice.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

EVIDENCE = EVIDENCE_ROOT / "credit_control" / "evidence"


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> int:
    conn, cur = connect()
    try:
        sales = json.loads(
            (EVIDENCE / "phase78_sale_credit_state.json").read_text(encoding="utf-8"))
        target_entries = sorted({s["docentry"] for s in sales["all_overdue_sales"]})
        placeholders = ",".join(["?"] * len(target_entries))
        pay = rows(cur, f'''SELECT i."SrcObjAbs" AS invoice_entry, i."ReconNum", i."ReconSum" AS applied,
            o."DocEntry" AS pay_entry, o."DocNum" AS pay_num, o."DocDate" AS pay_date,
            o."DocTotal" AS pay_total, o."CardCode", o."UserSign" AS pay_user, o."Canceled" AS pay_canceled,
            r."ReconDate" AS recon_date
            FROM "TELCHI"."ITR1" i
            JOIN "TELCHI"."OITR" r ON r."ReconNum" = i."ReconNum" AND r."InitObjTyp" = '24'
            JOIN "TELCHI"."ORCT" o ON o."DocEntry" = r."InitObjAbs"
            WHERE i."SrcObjTyp" = '13' AND i."SrcObjAbs" IN ({placeholders})''', target_entries)
        pay_by_inv = defaultdict(list)
        for p in pay:
            pay_by_inv[p["invoice_entry"]].append(p)
        traced = []
        for s in sales["all_overdue_sales"]:
            ps = pay_by_inv.get(s["docentry"], [])
            traced.append({
                **s,
                "payments": [
                    {"pay_entry": p["pay_entry"], "pay_num": p["pay_num"],
                     "pay_date": str(p["pay_date"]), "pay_total": round(float(p["pay_total"] or 0), 2),
                     "pay_user": p["pay_user"], "pay_canceled": p["pay_canceled"],
                     "recon_date": str(p["recon_date"]), "applied": round(float(p["applied"] or 0), 2)}
                    for p in ps
                ],
            })
        (EVIDENCE / "phase10_sale_payments.json").write_text(
            json.dumps(traced, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        paid = [t for t in traced if t["payments"]]
        open_total = sum(1 for t in traced if not t["payments"] and t["open_now"] > 0)
        print("overdue-at-sale sales:", len(traced), "| with payment trace:", len(paid),
              "| still open now:", open_total)
        n_pay_ops = sum(len(t["payments"]) for t in traced)
        print("total payment ops traced:", n_pay_ops)
        # examples with payments
        for t in paid[:8]:
            print("  ", t["cardcode"], t["docentry"], t["docdate"], t["doctotal"],
                  "pays:", [(p["pay_entry"], str(p["pay_date"])[:10], p["applied"]) for p in t["payments"]])
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
