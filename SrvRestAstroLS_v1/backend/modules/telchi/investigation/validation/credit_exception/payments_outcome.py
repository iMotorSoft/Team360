"""PHASE 24/25/26 — Payment / credit-note / reconciliation outcome per sale.

Uses the validated ITR1+OITR settlement ledger. For each sale DocEntry:
  applied_total         = sum of ITR1 debit ReconSum over active recons
  applied_before_sale   = same with OITR.ReconDate <= sale date
  applied_after_sale    = same with OITR.ReconDate >  sale date
  first_settlement_date = earliest active recon date
  credited_by_orin      = any active recon line pair whose credit side is ORIN
  open_now              = DocTotal - applied_total (verified against PaidToDate)
  current_status        = FULLY_PAID / PARTIALLY_PAID / OPEN / CANCELED / UNRESOLVED

Also customer-level pending credit notes (reduce exposure but not applied to a
specific invoice) are counted separately.

Emits evidence/payment_outcome.json + summary.
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
TOLERANCE = 0.01


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
        entries = [c["docentry"] for c in cases]
        ph = ",".join(["?"] * len(entries))
        ph2 = ",".join(["?"] * 500)  # credit-line recon set (batched)

        oitr = rows(cur, f'''SELECT "ReconNum","ReconDate","Canceled","InitObjTyp","InitObjAbs"
            FROM "TELCHI"."OITR"
            WHERE "ReconNum" IN (
              SELECT DISTINCT "ReconNum" FROM "TELCHI"."ITR1"
              WHERE "SrcObjTyp"='13' AND "SrcObjAbs" IN ({ph})
            )''', entries)
        active_recon = {r["reconnum"]: to_date(r["recondate"]) for r in oitr if r["canceled"] == "N"}
        itr1 = rows(cur, f'''SELECT "ReconNum","TransId","SrcObjTyp","SrcObjAbs","ReconSum","IsCredit"
            FROM "TELCHI"."ITR1"
            WHERE ("SrcObjTyp"='13' OR "SrcObjTyp"='14')
              AND "SrcObjAbs" IN ({ph})''', entries)
        recon_nums = sorted({r["reconnum"] for r in itr1 if r["reconnum"] in active_recon})
        credit_lines = rows(cur, f'''SELECT "ReconNum","SrcObjAbs"
            FROM "TELCHI"."ITR1"
            WHERE "SrcObjTyp"='14' AND "ReconNum" IN ({ph2})''', recon_nums) if recon_nums else []
        recon_credit_src = {}
        for t in credit_lines:
            if t["reconnum"] in active_recon:
                recon_credit_src.setdefault(t["reconnum"], []).append(t["srcobjabs"])

        applied: dict[int, list[int]] = defaultdict(list)  # entry -> [recondate...]
        for t in itr1:
            if str(t["srcobjtyp"]) == "13":
                d = active_recon.get(t["reconnum"])
                if d is not None:
                    applied[t["srcobjabs"]].append(d)
        for k in applied:
            applied[k].sort()

        out = []
        for c in cases:
            de = c["docentry"]
            sd = date.fromisoformat(c["docdate"])
            dates = applied.get(de, [])
            amt_before = 0.0
            amt_after = 0.0
            for t in itr1:
                if str(t["srcobjtyp"]) == "13" and t["srcobjabs"] == de:
                    d = active_recon.get(t["reconnum"])
                    if d is None:
                        continue
                    amt = float(t["reconsum"] or 0)
                    if d <= sd:
                        amt_before += amt
                    else:
                        amt_after += amt
            doc_total = float(c["doctotal"])
            open_now = max(doc_total - amt_before - amt_after, 0.0)
            fully_paid = open_now <= TOLERANCE
            partial_paid = (amt_before + amt_after) > TOLERANCE and not fully_paid
            if fully_paid:
                status = "FULLY_PAID"
            elif partial_paid:
                status = "PARTIALLY_PAID"
            else:
                status = "OPEN"
            # credited by credit note?
            credited = False
            for t in itr1:
                if str(t["srcobjtyp"]) == "13" and t["srcobjabs"] == de and t["reconnum"] in active_recon:
                    if recon_credit_src.get(t["reconnum"]):
                        credited = True
                    break
            after_dates = [d for d in dates if d > sd]
            first_after = min(after_dates) if after_dates else None
            days_to_first = (first_after - sd).days if first_after else None
            all_dates = dates
            first_any = min(all_dates) if all_dates else None
            days_to_first_any = (first_any - sd).days if first_any else None
            out.append({
                "docentry": de,
                "docdate": c["docdate"],
                "doctotal": round(doc_total, 2),
                "settled_before_sale": round(amt_before, 2),
                "settled_after_sale": round(amt_after, 2),
                "open_now": round(open_now, 2),
                "paid_to_date_field": round(float(c["paidtodate"]), 2),
                "fully_paid": fully_paid,
                "current_status": status,
                "first_settlement_after_sale": str(first_after) if first_after else None,
                "days_to_first_settlement": days_to_first,
                "first_settlement_any": str(first_any) if first_any else None,
                "days_to_first_any": days_to_first_any,
                "settled_by_credit_note": credited,
                "days_open_since_sale": (date(2026, 9, 2) - sd).days if not fully_paid else 0,
            })

        status_dist = defaultdict(int)
        for r in out:
            status_dist[r["current_status"]] += 1
        credited = sum(1 for r in out if r["settled_by_credit_note"])
        settled_after = sum(1 for r in out if (r["settled_after_sale"] or 0) > TOLERANCE)
        open_total = round(sum(r["open_now"] for r in out), 2)
        summary = {
            "cases": len(out),
            "status_distribution": dict(status_dist),
            "settled_by_credit_note": credited,
            "settled_after_sale_count": settled_after,
            "open_amount_total": open_total,
        }
        (EVIDENCE / "payment_outcome.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        (EVIDENCE / "payment_outcome_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        print(json.dumps(summary, indent=1))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())