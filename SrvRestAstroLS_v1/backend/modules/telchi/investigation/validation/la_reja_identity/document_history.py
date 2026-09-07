"""PHASE 2 — Full documentary history of C010341 LA REJA (READ ONLY).

Reconstructs every document family available for the Business Partner
C010341 across the full HANA history (no date cut):

  OINV/INV1  AR invoices
  ORIN/RIN1  AR credit notes
  ODLN/DLN1  deliveries
  ORDR/RDR1  sales orders
  ORCT/RCT2  incoming payments
  OITR/ITR1  settlement/ledger
  OJDT/JDT1  accounting journal (sample + aggregates)

Outputs:
  evidence/document_history_summary.json
  evidence/history_invoices.json
  evidence/history_deliveries.json
  evidence/history_orders.json
  evidence/history_credit_notes.json
  evidence/history_payments.json
  evidence/history_aggregates.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

BP = "C010341"


def q(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def to_date(v):
    return v.date().isoformat() if hasattr(v, "date") else str(v)


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    conn, cur = connect()
    summary = {}

    # ---- OINV full history (all documents, incl. canceled) ----
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocDueDate","DocTotal","PaidToDate",
               "DocCur","CANCELED","CardCode","SlpCode","UserSign","UserSign2",
               "NumAtCard","JrnlMemo","Ref1","GroupNum","Series","DiscPrcnt",
               "VatSum","Address","Address2","ObjType","U_ORIGIN","U_SO1_01RETAILONE",
               "U_SO1_01FOLIORETAIL1","U_DMS_STATE","CreateDate","UpdateDate","CtlAccount"
        FROM "TELCHI"."OINV" WHERE "CardCode"='{BP}' ORDER BY "DocDate","DocEntry"''')
    inv = [dict(zip(cols, r)) for r in rows]
    summary["invoices_total"] = len(inv)
    summary["invoices_canceled"] = sum(1 for r in inv if str(r["CANCELED"]) == "Y")
    summary["invoices_active"] = len(inv) - summary["invoices_canceled"]
    summary["gross_total_all"] = money(sum(r["DocTotal"] or 0 for r in inv))
    summary["paid_to_date_all"] = money(sum(r["PaidToDate"] or 0 for r in inv))
    summary["open_all"] = money(summary["gross_total_all"] - summary["paid_to_date_all"])
    if inv:
        summary["first_invoice_date"] = to_date(inv[0]["DocDate"])
        summary["last_invoice_date"] = to_date(inv[-1]["DocDate"])
    summary["invoices_user_signs"] = Counter(str(r["UserSign"]) for r in inv)
    summary["invoices_slp"] = Counter(str(r["SlpCode"]) for r in inv)
    summary["invoices_origin"] = Counter(str(r["U_ORIGIN"]) for r in inv)
    summary["invoices_retailone_y"] = Counter(str(r["U_SO1_01RETAILONE"]) for r in inv)
    summary["invoices_groupnum"] = Counter(str(r["GroupNum"]) for r in inv)
    summary["invoices_series"] = Counter(str(r["Series"]) for r in inv)

    # year-month series (active only)
    ym = Counter()
    for r in inv:
        if str(r["CANCELED"]) == "Y":
            continue
        ym[to_date(r["DocDate"])[:7]] += 1
    summary["invoices_by_month_counts"] = dict(sorted(ym.items()))
    ym_amount = defaultdict(float)
    for r in inv:
        if str(r["CANCELED"]) == "Y":
            continue
        ym_amount[to_date(r["DocDate"])[:7]] += float(r["DocTotal"] or 0)
    summary["invoices_by_month_amount"] = {k: money(v) for k, v in sorted(ym_amount.items())}

    # ---- ODLN deliveries ----
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocDueDate","DocTotal","DocCur","CANCELED",
               "SlpCode","UserSign","CardCode","JrnlMemo","NumAtCard","GroupNum","Series"
        FROM "TELCHI"."ODLN" WHERE "CardCode"='{BP}' ORDER BY "DocDate","DocEntry"''')
    dln = [dict(zip(cols, r)) for r in rows]
    summary["deliveries_total"] = len(dln)
    summary["deliveries_canceled"] = sum(1 for r in dln if str(r["CANCELED"]) == "Y")
    summary["deliveries_gross"] = money(sum(r["DocTotal"] or 0 for r in dln if str(r["CANCELED"]) != "Y"))
    if dln:
        summary["first_delivery_date"] = to_date(dln[0]["DocDate"])
        summary["last_delivery_date"] = to_date(dln[-1]["DocDate"])

    # ---- ORDR orders ----
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocDueDate","DocTotal","DocCur","CANCELED",
               "SlpCode","UserSign","CardCode","JrnlMemo","NumAtCard","GroupNum","Series"
        FROM "TELCHI"."ORDR" WHERE "CardCode"='{BP}' ORDER BY "DocDate","DocEntry"''')
    ords = [dict(zip(cols, r)) for r in rows]
    summary["orders_total"] = len(ords)
    summary["orders_canceled"] = sum(1 for r in ords if str(r["CANCELED"]) == "Y")
    summary["orders_gross"] = money(sum(r["DocTotal"] or 0 for r in ords if str(r["CANCELED"]) != "Y"))
    if ords:
        summary["first_order_date"] = to_date(ords[0]["DocDate"])
        summary["last_order_date"] = to_date(ords[-1]["DocDate"])

    # ---- ORIN credit notes ----
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCur","CANCELED","SlpCode",
               "UserSign","CardCode","JrnlMemo","NumAtCard"
        FROM "TELCHI"."ORIN" WHERE "CardCode"='{BP}' ORDER BY "DocDate","DocEntry"''')
    rin = [dict(zip(cols, r)) for r in rows]
    summary["credit_notes_total"] = len(rin)
    summary["credit_notes_canceled"] = sum(1 for r in rin if str(r["CANCELED"]) == "Y")
    summary["credit_notes_active"] = summary["credit_notes_total"] - summary["credit_notes_canceled"]
    summary["credit_notes_gross_active"] = money(
        sum(r["DocTotal"] or 0 for r in rin if str(r["CANCELED"]) != "Y"))
    if rin:
        summary["first_credit_note_date"] = to_date(rin[0]["DocDate"])
        summary["last_credit_note_date"] = to_date(rin[-1]["DocDate"])

    # ---- ORCT incoming payments ----
    # NOTE: ORCT uses DocCurr / Canceled (not DocCur / CANCELED as OINV-ODLN).
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCurr","Canceled","CardCode",
               "UserSign","CashSum","CheckSum","TrsfrSum","CreditSum","TransId"
        FROM "TELCHI"."ORCT" WHERE "CardCode"='{BP}' ORDER BY "DocDate","DocEntry"''')
    rct = [dict(zip(cols, r)) for r in rows]
    summary["payments_total"] = len(rct)
    summary["payments_canceled"] = sum(1 for r in rct if str(r["Canceled"]) == "Y")
    summary["payments_active"] = summary["payments_total"] - summary["payments_canceled"]
    summary["payments_gross_active"] = money(
        sum(r["DocTotal"] or 0 for r in rct if str(r["Canceled"]) != "Y"))
    if rct:
        summary["first_payment_date"] = to_date(rct[0]["DocDate"])
        summary["last_payment_date"] = to_date(rct[-1]["DocDate"])
    summary["payments_cashsum"] = money(sum(r["CashSum"] or 0 for r in rct if str(r["Canceled"]) != "Y"))
    summary["payments_checksum"] = money(sum(r["CheckSum"] or 0 for r in rct if str(r["Canceled"]) != "Y"))
    summary["payments_trsfrsum"] = money(sum(r["TrsfrSum"] or 0 for r in rct if str(r["Canceled"]) != "Y"))

    # ---- OITR + ITR1 settlement ledger (validated semantics) ----
    # Reconciliation header OITR (Canceled='N') + lines ITR1 by SrcObjTyp 13/14.
    recon_rows = q(cur, f'''
        SELECT "ReconNum","ReconDate","Canceled","InitObjTyp","InitObjAbs","UserSign"
        FROM "TELCHI"."OITR" WHERE "Canceled"='N' AND "ReconNum" IN (
            SELECT DISTINCT "ReconNum" FROM "TELCHI"."ITR1"
            WHERE "SrcObjTyp" IN ('13','14') AND "SrcObjAbs" IN (
                SELECT "DocEntry" FROM "TELCHI"."OINV" WHERE "CardCode"='{BP}'
                UNION SELECT "DocEntry" FROM "TELCHI"."ORIN" WHERE "CardCode"='{BP}'
            )
        )''')
    recon_cols, recon_rows = recon_rows
    recon_idx = {r[recon_cols.index("ReconNum")]: dict(zip(recon_cols, r)) for r in recon_rows}
    itr_cols, itr_rows = q(cur, f'''
        SELECT "ReconNum","TransId","SrcObjTyp","SrcObjAbs","ReconSum","IsCredit","ShortName"
        FROM "TELCHI"."ITR1"
        WHERE "SrcObjTyp" IN ('13','14') AND "SrcObjAbs" IN (
            SELECT "DocEntry" FROM "TELCHI"."OINV" WHERE "CardCode"='{BP}'
            UNION SELECT "DocEntry" FROM "TELCHI"."ORIN" WHERE "CardCode"='{BP}'
        )''')
    itr = [dict(zip(itr_cols, r)) for r in itr_rows]
    summary["settlement_ledger_rows"] = len(itr)
    summary["settlement_active_recons"] = len(recon_idx)
    # applied by source doc type, signed credit = settlement reduce open
    applied_by_type = Counter()
    applied_total = 0.0
    for t in itr:
        key = f"src={t['SrcObjTyp']} credit={t['IsCredit']}"
        applied_by_type[key] += float(t["ReconSum"] or 0)
        applied_total += float(t["ReconSum"] or 0)
    summary["settlement_ledger_by_basetype"] = {k: round(v, 2) for k, v in applied_by_type.items()}
    summary["settlement_applied_total"] = round(applied_total, 2)
    recon_users = Counter(str(r["UserSign"]) for r in recon_idx.values())
    summary["settlement_recon_users"] = {k: int(v) for k, v in recon_users.items()}
    summary["settlement_first_date"] = (to_date(min(r["ReconDate"] for r in recon_idx.values()))
                                        if recon_idx else None)
    summary["settlement_last_date"] = (to_date(max(r["ReconDate"] for r in recon_idx.values()))
                                        if recon_idx else None)

    # ---- OJDT accounting for this BP (sample + aggregates) ----
    cols, rows = q(cur, f'''
        SELECT "TransId","TransType","BaseRef","RefDate","Ref1","Ref2","Ref3","Memo",
               "UserSign","CreateDate"
        FROM "TELCHI"."OJDT" WHERE "TransId" IN (
            SELECT "TransId" FROM "TELCHI"."JDT1" WHERE "ShortName"='{BP}')
        ORDER BY "RefDate","TransId"''')
    ojdt = [dict(zip(cols, r)) for r in rows]
    summary["accounting_journal_headers"] = len(ojdt)
    summary["accounting_journal_trans_types"] = Counter(str(r["TransType"]) for r in ojdt)
    summary["accounting_journal_users"] = Counter(str(r["UserSign"]) for r in ojdt)
    if ojdt:
        summary["first_journal_date"] = to_date(ojdt[0]["RefDate"])
        summary["last_journal_date"] = to_date(ojdt[-1]["RefDate"])

    # JDT1 account split (main control account)
    cols, rows = q(cur, f'''
        SELECT "Account", SUM("Debit") AS DB, SUM("Credit") AS CR, COUNT(*) AS N
        FROM "TELCHI"."JDT1" WHERE "ShortName"='{BP}'
        GROUP BY "Account" ORDER BY (SUM("Debit")+SUM("Credit")) DESC''')
    jdt1 = [dict(zip(cols, r)) for r in rows]
    summary["journal_by_account"] = [
        {**r, "DB": money(r["DB"]), "CR": money(r["CR"])} for r in jdt1]

    summary["sap_write_count"] = 0

    out = {
        "bp": BP,
        "summary": summary,
        "invoices": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                      for k, v in r.items()} for r in inv],
        "deliveries": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                        for k, v in r.items()} for r in dln],
        "orders": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                    for k, v in r.items()} for r in ords],
        "credit_notes": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                          for k, v in r.items()} for r in rin],
        "payments": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                      for k, v in r.items()} for r in rct],
        "settlement_ledger": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                               for k, v in r.items()} for r in itr],
        "accounting_headers": [{k: (to_date(v) if isinstance(v, date) else money(v) if isinstance(v, float) else v)
                                for k, v in r.items()} for r in ojdt],
        "journal_by_account": summary["journal_by_account"],
    }
    (EVIDENCE / "history_invoices.json").write_text(
        json.dumps(out["invoices"], ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "history_deliveries.json").write_text(
        json.dumps(out["deliveries"], ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "history_orders.json").write_text(
        json.dumps(out["orders"], ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "history_credit_notes.json").write_text(
        json.dumps(out["credit_notes"], ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "history_payments.json").write_text(
        json.dumps(out["payments"], ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "history_aggregates.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    conn.close()


if __name__ == "__main__":
    main()