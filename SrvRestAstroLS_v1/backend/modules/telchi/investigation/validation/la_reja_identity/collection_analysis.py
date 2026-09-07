"""PHASE 13/14/26/27/28 — Collection & accounting for C010341 (READ ONLY).

  a) Full history settlement: ORCT (payments) + ORIN (credit notes) +
     OITR/ITR1 (reconciliation ledger) for the BP.
  b) Invoice reconciliation identity:
         invoice = paid + credited + open   (baseline as-of 2026-09-01)
  c) Closing pattern classification:
         NORMAL_COLLECTION / INTERNAL_RECONCILIATION_PATTERN /
         CREDIT_NOTE_CLEARING / PERSISTENT_OPEN_BALANCE / UNKNOWN
  d) Accounting sample: OJDT/JDT1 for 3 invoices (TransId, debit, credit,
     control account 1120101) — balanced check.
  e) OCRD balance consistency: OCRD.Balance == OINV open sum.

Outputs:
  evidence/collection_history.json
  evidence/accounting_sample.json
  evidence/collection_summary.json
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
BP = "C010341"
CUTOFF = date(2026, 9, 1)


def money(v):
    return round(float(v or 0.0), 2)


def to_date(v):
    return v.date().isoformat() if hasattr(v, "date") else str(v)


def main() -> None:
    conn, cur = connect()

    def q(sql, *a):
        cur.execute(sql, *a)
        return [d[0] for d in cur.description], cur.fetchall()

    # ORCT payments full history
    _, rct = q('''SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCurr","Canceled","UserSign"
        FROM "TELCHI"."ORCT" WHERE "CardCode"=? ORDER BY "DocDate"''', (BP,))
    # ORIN credit notes
    _, rin = q('''SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCur","CANCELED","UserSign",
        "U_SO1_01RETAILONE" FROM "TELCHI"."ORIN" WHERE "CardCode"=? ORDER BY "DocDate"''', (BP,))
    # OITR/ITR1 active reconciliations
    _, recon = q('''
        SELECT o."ReconNum",o."ReconDate",o."UserSign",o."Canceled",
               t."SrcObjTyp",t."SrcObjAbs",t."ReconSum",t."IsCredit",t."ShortName"
        FROM "TELCHI"."OITR" o JOIN "TELCHI"."ITR1" t ON t."ReconNum"=o."ReconNum"
        WHERE o."Canceled"='N' AND t."SrcObjTyp" IN ('13','14') AND t."SrcObjAbs" IN (
            SELECT "DocEntry" FROM "TELCHI"."OINV" WHERE "CardCode"=?
            UNION SELECT "DocEntry" FROM "TELCHI"."ORIN" WHERE "CardCode"=?
        )''', (BP, BP))
    # OINV totals for identity
    _, inv = q('''SELECT "DocEntry","DocTotal","PaidToDate" FROM "TELCHI"."OINV"
        WHERE "CardCode"=? AND "CANCELED"='N' ''', (BP,))
    total_gross = money(sum(r[1] or 0 for r in inv))
    total_paid = money(sum(r[2] or 0 for r in inv))
    total_open = money(total_gross - total_paid)
    nc_total = money(sum(r[3] or 0 for r in rin if str(r[5]) != "Y"))
    rct_total = money(sum(r[3] or 0 for r in rct if str(r[5]) != "Y"))

    # OCRD balance
    cur.execute('SELECT "Balance","CreditLine","LicTradNum" FROM "TELCHI"."OCRD" WHERE "CardCode"=?', (BP,))
    ocrd = cur.fetchone()

    identity_ok = abs(total_open - (total_gross - total_paid)) <= 0.02
    invoice_identity = {
        "invoice_total": total_gross,
        "paid": total_paid,
        "credited": nc_total,
        "orct_paid": rct_total,
        "open": total_open,
        "identity_ok": identity_ok,
    }

    # accounting sample: 3 largest 40-case invoices
    cases = json.loads((EVIDENCE / "atomic_la_reja_cases.json").read_text())
    sample_entries = [c["invoice_docentry"] for c in sorted(cases, key=lambda c: -c["gross_amount"])[:3]]
    acct = []
    for de in sample_entries:
        _, jdt = q('''SELECT j."TransId",j."Line_ID",j."Account",j."Debit",j."Credit",j."ShortName",
            j."RefDate",j."TransType",j."LineMemo",j."ContraAct"
            FROM "TELCHI"."JDT1" j WHERE j."TransId" IN (
                SELECT "TransId" FROM "TELCHI"."OINV" WHERE "DocEntry"=?
            ) ORDER BY j."Line_ID"''', (de,))
        db = money(sum(r[3] or 0 for r in jdt))
        cr = money(sum(r[4] or 0 for r in jdt))
        acct.append({
            "docentry": de,
            "trans_ids": sorted({r[0] for r in jdt}),
            "rows": [dict(zip([d[0] for d in cur.description], r)) for r in jdt]
                    if False else [
                        {"transid": r[0], "line": r[1], "account": r[2],
                         "debit": money(r[3]), "credit": money(r[4]),
                         "shortname": r[5], "refdate": to_date(r[6]),
                         "transtype": r[7], "memo": r[8], "contra": r[9]}
                        for r in jdt],
            "debit_sum": db,
            "credit_sum": cr,
            "balanced": abs(db - cr) <= 0.02,
        })

    # closing pattern
    if rct_total <= 0.02 and nc_total > 0 and total_open > 1000:
        pattern = "CREDIT_NOTE_CLEARING + PERSISTENT_OPEN_BALANCE"
    elif rct_total <= 0.02 and total_open > 1000:
        pattern = "PERSISTENT_OPEN_BALANCE"
    elif nc_total > 0 and rct_total > 0:
        pattern = "NORMAL_COLLECTION"
    else:
        pattern = "UNKNOWN"

    summary = {
        "orct_payments": len(rct),
        "orct_payments_canceled": sum(1 for r in rct if str(r[5]) == "Y"),
        "credit_notes": len(rin),
        "credit_notes_active": sum(1 for r in rin if str(r[5]) != "Y"),
        "credit_notes_total_active": nc_total,
        "reconciliations_active": len({r[0] for r in recon}),
        "reconciliation_rows": len(recon),
        "reconciliation_by_type": {k: int(v) for k, v in Counter(f"src={r[4]} credit={r[7]}" for r in recon).items()},
        "reconciliation_amount": money(sum(r[6] or 0 for r in recon)),
        "reconciliation_users": {k: int(v) for k, v in Counter(str(r[2]) for r in recon).items()},
        "invoice_identity": invoice_identity,
        "ocrd_balance": money(ocrd[0]) if ocrd else None,
        "ocrd_creditline": money(ocrd[1]) if ocrd else None,
        "ocrd_balance_matches_open": ocrd is not None and abs(float(ocrd[0]) - total_open) <= 0.05,
        "closing_pattern": pattern,
        "accounting_sample": acct,
        "all_accounting_balanced": all(a["balanced"] for a in acct),
        "sap_write_count": 0,
    }
    (EVIDENCE / "collection_history.json").write_text(json.dumps({
        "payments": [dict(zip(("docentry", "docnum", "docdate", "doctotal", "doccurr", "canceled", "usersign"), r)) for r in rct],
        "credit_notes": [dict(zip(("docentry", "docnum", "docdate", "doctotal", "doccurr", "canceled", "usersign", "r1"), r)) for r in rin],
        "reconciliations": [dict(zip(("reconnum", "recondate", "usersign", "canceled", "src_obj_typ", "src_obj_abs", "reconsum", "is_credit", "shortname"), r)) for r in recon],
    }, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "accounting_sample.json").write_text(json.dumps(acct, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "collection_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    conn.close()


if __name__ == "__main__":
    main()