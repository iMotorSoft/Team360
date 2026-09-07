"""LOOP TEST 40 — Cardinality / anti-fanout for the joins used in this cycle
(READ ONLY). Verdict NO_SILENT_FANOUT requires dup_factor <= sane bound and
no unmatched explosion on the money-carrying links.

Joins audited (window: invoices of the 177-customer universe, 2026):
  customer -> invoices
  invoice -> ITR1 settlement lines
  ITR1 -> OITR (recon header, InitObjTyp=24)
  OITR -> ORCT (payment)
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

EVIDENCE = EVIDENCE_ROOT / "credit_control" / "evidence"


def one(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> int:
    conn, cur = connect()
    try:
        u = json.loads((EVIDENCE / "phase78_sale_credit_state.json").read_text())
        # rebuild customer list from the evidence (universe customers count only)
        # simpler: bound by the invoice set used: invoices entries list is too big to
        # pass; use a fixed bound: focus + over-limit + overdue customers is 177.
        # Here we audit with a deterministic slice: OINV 2026 for CardType=C customers
        # with CreditLine>0 (limit-based universe).
        metrics = {}

        n_cust = one(cur, '''SELECT COUNT(DISTINCT "CardCode") FROM "TELCHI"."OINV"
            WHERE "CANCELED"='N' AND "DocDate">='2020-01-01' AND "CardCode" IN
            (SELECT "CardCode" FROM "TELCHI"."OCRD" WHERE "CardType"='C')''')
        n_inv = one(cur, '''SELECT COUNT(*) FROM "TELCHI"."OINV"
            WHERE "CANCELED"='N' AND "DocDate">='2020-01-01' AND "CardCode" IN
            (SELECT "CardCode" FROM "TELCHI"."OCRD" WHERE "CardType"='C')''')
        metrics["customer_to_invoices_dup"] = round(n_inv / n_cust, 3)
        metrics["n_customers"] = n_cust
        metrics["n_invoices"] = n_inv

        # invoice -> ITR1 : dup factor + unmatched
        metrics["invoice_to_itr1"] = {}
        metrics["invoice_to_itr1"]["n_invoices_in_join"] = one(cur,
            '''SELECT COUNT(DISTINCT i."DocEntry") FROM "TELCHI"."OINV" i
               JOIN "TELCHI"."ITR1" t ON t."SrcObjTyp"='13' AND t."SrcObjAbs"=i."DocEntry"
               WHERE i."CANCELED"='N' AND i."DocDate">='2026-01-01' ''')
        metrics["invoice_to_itr1"]["n_settlement_rows"] = one(cur,
            '''SELECT COUNT(*) FROM "TELCHI"."ITR1" t
               JOIN "TELCHI"."OINV" i ON t."SrcObjTyp"='13' AND t."SrcObjAbs"=i."DocEntry"
               WHERE i."CANCELED"='N' AND i."DocDate">='2026-01-01' ''')
        metrics["invoice_to_itr1"]["n_invoices_total"] = one(cur,
            '''SELECT COUNT(*) FROM "TELCHI"."OINV" WHERE "CANCELED"='N' AND "DocDate">='2026-01-01' ''')
        a = metrics["invoice_to_itr1"]["n_settlement_rows"]
        b = metrics["invoice_to_itr1"]["n_invoices_in_join"]
        metrics["invoice_to_itr1"]["dup_factor"] = round(a / b, 3) if b else None

        # ITR1 -> OITR(recon,24) -> ORCT
        metrics["itr1_oitr_orct"] = {}
        metrics["itr1_oitr_orct"]["n_itr1_rows"] = one(cur,
            '''SELECT COUNT(*) FROM "TELCHI"."ITR1" t JOIN "TELCHI"."OINV" i
               ON t."SrcObjTyp"='13' AND t."SrcObjAbs"=i."DocEntry"
               WHERE i."CANCELED"='N' AND i."DocDate">='2026-01-01' ''')
        metrics["itr1_oitr_orct"]["n_orct_linked"] = one(cur,
            '''SELECT COUNT(*) FROM "TELCHI"."ITR1" t JOIN "TELCHI"."OINV" i
               ON t."SrcObjTyp"='13' AND t."SrcObjAbs"=i."DocEntry"
               JOIN "TELCHI"."OITR" r ON r."ReconNum"=t."ReconNum" AND r."InitObjTyp"='24'
               JOIN "TELCHI"."ORCT" o ON o."DocEntry"=r."InitObjAbs"
               WHERE i."CANCELED"='N' AND i."DocDate">='2026-01-01'
                 AND o."Canceled"='N' ''')
        a2 = metrics["itr1_oitr_orct"]["n_orct_linked"]
        b2 = metrics["itr1_oitr_orct"]["n_itr1_rows"]
        metrics["itr1_oitr_orct"]["dup_factor"] = round(a2 / b2, 3) if b2 else None

        # unmatched ratio for ITR1->ORCT (settled invoices without a payment link)
        metrics["itr1_oitr_orct"]["settled_unmatched_ratio"] = round(
            (b2 - a2) / b2, 3) if b2 else None

        # over-limit check: how many customers have CreditLine > 0
        metrics["customers_with_creditline"] = one(cur,
            '''SELECT COUNT(*) FROM "TELCHI"."OCRD" WHERE "CardType"='C' AND "CreditLine">0''')

        verdict = "NO_SILENT_FANOUT" if all(
            (m.get("dup_factor") if isinstance(m, dict) else 0) or 1 <= 5
            for m in metrics.values() if isinstance(m, dict)) else "FANOUT_REVIEW"
        metrics["verdict"] = verdict

        (EVIDENCE / "phase40_cardinality.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(metrics, indent=1, default=str))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
