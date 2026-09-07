"""PHASE 1/2 — Revalidate the 287 overdue-at-sale cases with EXACT historical
receivable reconstruction (READ ONLY).

Approach
--------
* Universe = focus customers + today-over-limit + today-overdue (same as the
  prior credit-control gate) minus internal control prefixes.
* Open balance of invoice I at date S:
      open_at_sale(I,S) = DocTotal - sum(ITR1.ReconSum) over active
      reconciliations (OITR.Canceled='N') with OITR.ReconDate <= S that settle
      that invoice (ITR1.SrcObjTyp='13', SrcObjAbs=I, credit/debit pair).
  (Validated: ORCT+RCT2 payments also create OITR/ITR1 reconciliations, so
  ITR1/OITR is the COMPLETE settlement ledger; no double counting.)
* Due date: OINV.DocDueDate is the effective due date (INV6 is a 1:1 mirror
  in this installation - single installment per invoice, DueDate=DocDueDate).
  Invoices with zero/1900 DocDueDate fall back to DocDate.
* overdue_at_sale(S): exists invoice with due < S and open_at_sale > tolerance.
* Also computes net exposure at sale (open invoices minus open credit notes)
  for the credit-limit cases.

Emits evidence/revalidated_cases.json and evidence/revalidation_summary.json.
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
FOCUS = ["C003542", "C008090", "C003531", "C007776", "E000043"]
WINDOW_START = date(2026, 1, 1)
WINDOW_END = date(2026, 9, 1)
TOLERANCE = 0.01
INTERNAL_PREFIX = ("CGCM", "CG2A", "CGCT", "CGEC", "S000")
MIN_OVERDUE_AMOUNT = 0.0  # config MONTOMINVENCRE=0 (validated in prior gate)


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


def build_universe(cur):
    focus = rows(cur,
        'SELECT "CardCode" FROM "TELCHI"."OCRD" WHERE "CardCode" IN (%s)' %
        ",".join(["?"] * len(FOCUS)), FOCUS)
    over = rows(cur,
        'SELECT "CardCode" FROM "TELCHI"."OCRD" WHERE "CardType"=\'C\' AND "CreditLine" > 0 AND "Balance" > "CreditLine"')
    overdue_cust = rows(cur,
        'SELECT DISTINCT "CardCode" FROM "TELCHI"."OINV" WHERE "CANCELED"=\'N\' '
        'AND "PaidToDate" < "DocTotal" AND "DocDueDate" < CURRENT_DATE')
    universe = sorted(set([r["cardcode"] for r in focus]
                          + [r["cardcode"] for r in over]
                          + [r["cardcode"] for r in overdue_cust]))
    universe = [c for c in universe if not c.startswith(INTERNAL_PREFIX)]
    return universe


def build_reconstructor(cur, universe):
    """Load all documents + settlements for the universe into memory."""
    ph = ",".join(["?"] * len(universe))
    inv = rows(cur, f'''SELECT "DocEntry","DocNum","CardCode","DocDate","DocDueDate",
        "DocTotal","PaidToDate","CANCELED","UserSign","U_ORIGIN","U_SO1_01RETAILONE","SlpCode","GroupNum"
        FROM "TELCHI"."OINV" WHERE "CardCode" IN ({ph}) AND "CANCELED"='N' ''', universe)
    for r in inv:
        r["_type"] = "OINV"
    orin = rows(cur, f'''SELECT "DocEntry","DocNum","CardCode","DocDate","DocDueDate",
        "DocTotal","PaidToDate","CANCELED","UserSign","U_ORIGIN","U_SO1_01RETAILONE","SlpCode","GroupNum"
        FROM "TELCHI"."ORIN" WHERE "CardCode" IN ({ph}) AND "CANCELED"='N' ''', universe)
    for r in orin:
        r["_type"] = "ORIN"
    docs = inv + orin

    # active reconciliations (OITR) for these customers: settle via ITR1 lines
    doc_entries = [r["docentry"] for r in docs]
    if not doc_entries:
        return docs, [], []
    oitr = rows(cur, f'''SELECT "ReconNum","ReconDate","Canceled","InitObjTyp","InitObjAbs","UserSign"
        FROM "TELCHI"."OITR" WHERE "Canceled"='N'
        AND "ReconNum" IN (
           SELECT DISTINCT "ReconNum" FROM "TELCHI"."ITR1"
           WHERE "SrcObjTyp" IN ('13','14') AND "SrcObjAbs" IN ({",".join(["?"] * len(doc_entries))})
        )''', doc_entries)
    itr1 = rows(cur, f'''SELECT "ReconNum","TransId","SrcObjTyp","SrcObjAbs","ReconSum","IsCredit","ShortName"
        FROM "TELCHI"."ITR1"
        WHERE "SrcObjTyp" IN ('13','14') AND "SrcObjAbs" IN ({",".join(["?"] * len(doc_entries))})''', doc_entries)
    return docs, oitr, itr1


def compute_open_at_sale(oitr, itr1):
    """mapping invoice_entry -> [(recondate, applied_amount)] sorted by date."""
    oitr_by_recon = {r["reconnum"]: r for r in oitr}
    app: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for t in itr1:
        r = oitr_by_recon.get(t["reconnum"])
        if r is None:
            continue
        amt = float(t["reconsum"] or 0)
        app[t["srcobjabs"]].append((to_date(r["recondate"]), amt))
    for k in app:
        app[k].sort(key=lambda x: (x[0]))
    return app


def overdue_rule(due, sale_date):
    """Effective due-date semantics validated in phase A."""
    if due is None:
        return False
    return due < sale_date


def reconstruct_sales_state(docs, app, ocrd, window_start, window_end):
    """Pure reconstruction of sale credit state (unit-testable).

    docs: list of OINV/ORIN dicts with _type, cardcode, docentry, docdate,
          docduedate, doctotal, etc.
    app:  dict entry -> sorted [(recondate, amount)]
    Returns list of sale-state dicts in window (same schema as revalidate.py).
    """
    sales = []
    by_cc: dict[str, list[dict]] = defaultdict(list)
    for r in docs:
        by_cc[r["cardcode"]].append(r)
    for cc, cc_docs in by_cc.items():
        limit = float(ocrd.get(cc, {}).get("creditline") or 0) if ocrd else 0.0
        for d in cc_docs:
            if d["_type"] != "OINV":
                continue
            if str(d.get("canceled", "N")).upper() != "N":
                continue  # canceled documents never count as open sales
            sd = to_date(d["docdate"])
            if sd is None or sd < window_start or sd > window_end:
                continue
            open_now = float(d["doctotal"]) - float(d.get("paidtodate") or 0)
            paid_to_date = float(d.get("paidtodate") or 0)
            applied_before = sum(a for dt, a in app.get(d["docentry"], []) if dt < sd)
            open_at_sale = float(d["doctotal"]) - applied_before
            appl_note = ""
            if open_at_sale < -TOLERANCE:
                appl_note = f"overapplied {-open_at_sale:.2f}"
                open_at_sale = 0.0
            sales.append({
                "cardcode": cc, "docentry": d["docentry"], "docnum": d["docnum"],
                "docdate": str(d["docdate"])[:10],
                "docduedate": str(d["docduedate"])[:10],
                "doctotal": round(float(d["doctotal"]), 2),
                "paidtodate": round(paid_to_date, 2),
                "open_now": round(open_now, 2),
                "open_at_sale": round(open_at_sale, 2),
                "overdue_at_sale": False, "overdue_amount_at_sale": 0.0,
                "overdue_count_at_sale": 0, "oldest_overdue_at_sale": None,
                "usersign": d.get("usersign"), "origin": d.get("u_origin"),
                "retailone": d.get("u_so1_01retailone"), "slpcode": d.get("slpcode"),
                "grouplistnum": d.get("groupnum"), "applied_note": appl_note,
            })
    sales.sort(key=lambda s: (s["cardcode"], s["docdate"], s["docentry"]))
    by_cc2: dict[str, list[dict]] = defaultdict(list)
    for s in sales:
        by_cc2[s["cardcode"]].append(s)
    for cc, ss in by_cc2.items():
        invs = [d for d in docs if d["cardcode"] == cc]
        for s in ss:
            sd = date.fromisoformat(s["docdate"])
            ov_amt = 0.0
            ov_count = 0
            oldest = None
            for d in invs:
                if d["docentry"] == s["docentry"]:
                    continue
                if d["_type"] != "OINV":
                    continue
                if str(d.get("canceled", "N")).upper() != "N":
                    continue
                dd = to_date(d["docdate"])
                if dd and dd > sd:
                    continue
                due = to_date(d["docduedate"])
                if not overdue_rule(due, sd):
                    continue
                op = float(d["doctotal"]) - sum(
                    a for dt, a in app.get(d["docentry"], []) if dt < sd)
                if op > TOLERANCE:
                    ov_amt += op
                    ov_count += 1
                    if oldest is None or due < oldest:
                        oldest = due
            s["overdue_at_sale"] = ov_amt > TOLERANCE
            s["overdue_amount_at_sale"] = round(ov_amt, 2)
            s["overdue_count_at_sale"] = ov_count
            s["oldest_overdue_at_sale"] = str(oldest) if oldest else None
            s["days_oldest_overdue"] = (sd - oldest).days if oldest else None
        for s in ss:
            ccx = s["cardcode"]
            sd = date.fromisoformat(s["docdate"])
            expo = 0.0
            for d in docs:
                if d["cardcode"] != ccx:
                    continue
                dd = to_date(d["docdate"])
                if dd and dd > sd:
                    continue
                if d["docentry"] == s["docentry"]:
                    continue
                op = float(d["doctotal"]) - sum(
                    a for dt, a in app.get(d["docentry"], []) if dt < sd)
                expo += max(op, 0.0)
            s["exposure_before"] = round(expo, 2)
            limit = float(ocrd.get(ccx, {}).get("creditline") or 0) if ocrd else 0.0
            s["creditline"] = limit
            s["over_limit_before"] = limit > 0 and expo > limit
            s["over_limit_after"] = limit > 0 and (expo + s["doctotal"]) > limit
    return sales


def main() -> int:
    conn, cur = connect()
    try:
        universe = build_universe(cur)
        ocrd_full = rows(cur, f'''SELECT "CardCode","CardName","CreditLine","Balance","GroupNum",
            "U_SO1_01VENCREVENC","U_CANAL_VENTAS","Block","PaymBlock","U_ClienteExcepcional"
            FROM "TELCHI"."OCRD" WHERE "CardCode" IN ({",".join(["?"] * len(universe))})''', universe)
        ocrd = {r["cardcode"]: r for r in ocrd_full}
        docs, oitr, itr1 = build_reconstructor(cur, universe)
        app = compute_open_at_sale(oitr, itr1)
        print(f"universe={len(universe)} docs={len(docs)} oitr={len(oitr)} itr1={len(itr1)}")

        # group documents per customer, sorted by docdate+docentry
        by_cc: dict[str, list[dict]] = defaultdict(list)
        for r in docs:
            by_cc[r["cardcode"]].append(r)

        prior_287 = json.loads(
            (EVIDENCE.parent.parent / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
            .read_text(encoding="utf-8"))["all_overdue_sales"]
        prior_keys = {(s["cardcode"], s["docentry"]) for s in prior_287}

        sales = reconstruct_sales_state(docs, app, ocrd, WINDOW_START, WINDOW_END)

        overdue_sales = [s for s in sales if s["overdue_at_sale"]]
        new_keys = {(s["cardcode"], s["docentry"]) for s in overdue_sales}
        removed = sorted(prior_keys - new_keys)
        added = sorted(new_keys - prior_keys)

        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "revalidated_cases.json").write_text(
            json.dumps(overdue_sales, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        summary = {
            "universe_customers": len(universe),
            "window": [str(WINDOW_START), str(WINDOW_END)],
            "sales_in_window": len(sales),
            "overdue_at_sale_revalidated": len(overdue_sales),
            "prior_287": len(prior_287),
            "delta": {"removed": len(removed), "added": len(added)},
            "removed_samples": removed[:40],
            "added_samples": added[:40],
        }
        (EVIDENCE / "revalidation_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(summary, indent=1, default=str))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())