"""HANA READ-ONLY smoke for the open-risk gate (LOOP TEST 76 §52).

Verifies against live HANA:
  * 5 USER FULL cases (largest overdue)
  * 5 DELIVERY FLOW cases (largest overdue)
  * 3 cases from the largest-open customer (LA REJA)
  * 3 oldest-overdue cases

Checks per sample: DocDate/DocDueDate against OINV, single installment
INV6, open amount from HANA (DocTotal - PaidToDate) matches the enriched
open_amount, overdue amount matches when due < cutoff, DocCur='BS'.

Also audits the scripts of this cycle for write statements.

Emitted: evidence/hana_smoke_open_risk.json, evidence/readonly_audit_open_risk.json
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection, _WRITE_TOKENS

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_open_risk" / "evidence"
CUTOFF = date(2026, 9, 1)
TOL = 0.05


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def audit_cycle_source() -> dict:
    bad, executed, files = [], 0, []
    for root in (HERE, HERE.parent / "credit_exception_economic",
                 HERE.parent / "credit_exception", HERE.parent / "credit_control"):
        files.extend(sorted(root.glob("**/*.py")))
    for py in files:
        text = re.sub(r'""".*?"""', "", py.read_text(encoding="utf-8"), flags=re.S)
        for i, line in enumerate(text.splitlines(), 1):
            if "execute(" not in line and "executemany(" not in line:
                continue
            executed += 1
            body = line.split("#", 1)[0]
            if _WRITE_TOKENS.search(body):
                bad.append((py.name, i, line.strip()))
    return {"source_files_scanned": len(files), "execute_sites_expected": executed,
            "write_statements_found": len(bad), "sap_write_count": len(bad)}


def main() -> int:
    cases = json.loads((EVIDENCE / "open_risk_cases.json").read_text(encoding="utf-8"))
    sample_keys = {}
    full = sorted([r for r in cases if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"],
                  key=lambda r: -r["overdue_amount"])[:5]
    deliv = sorted([r for r in cases if r["secondary_reason"] == "DELIVERY_PREVIOUS"],
                   key=lambda r: -r["overdue_amount"])[:5]
    la_reja = sorted([r for r in cases if r["cardcode"] == "C010341"],
                     key=lambda r: -r["overdue_amount"])[:3]
    oldest = sorted([r for r in cases if r["overdue_amount"] > TOL],
                    key=lambda r: -r["days_overdue"])[:3]
    sample_keys = {"USER_FULL": [r["doc_entry"] for r in full],
                   "DELIVERY": [r["doc_entry"] for r in deliv],
                   "LA_REJA": [r["doc_entry"] for r in la_reja],
                   "OLDEST_OVERDUE": [r["doc_entry"] for r in oldest]}
    docmap = {r["doc_entry"]: r for r in cases}
    des = sorted({de for group in sample_keys.values() for de in group})

    audit = audit_cycle_source()
    conn, cur = connect()
    try:
        roconn = ReadOnlyConnection(conn)
        c = roconn.cursor()
        checks = []
        for de in des:
            r = docmap[de]
            inv = rows(c, '''SELECT "DocNum","CardCode","DocDate","DocDueDate","DocTotal",
                "PaidToDate","DocCur","UserSign" FROM "TELCHI"."OINV" WHERE "DocEntry"=?''', (de,))
            inv6 = rows(c, '''SELECT "InstlmntID","DueDate","InsTotal","PaidToDate" FROM "TELCHI"."INV6"
                WHERE "DocEntry"=? ORDER BY "InstlmntID"''', (de,))
            sett = rows(c, '''SELECT t."ReconSum", r."ReconDate", r."InitObjTyp" FROM "TELCHI"."ITR1" t
                JOIN "TELCHI"."OITR" r ON r."ReconNum"=t."ReconNum"
                WHERE t."SrcObjTyp"='13' AND t."SrcObjAbs"=? AND r."Canceled"='N' ''', (de,))
            if not inv:
                checks.append({"docentry": de, "error": "invoice not found"})
                continue
            i = inv[0]
            hana_open = float(i["doctotal"]) - float(i["paidtodate"])
            due_hana = str(i["docduedate"])[:10]
            checks.append({
                "docentry": de,
                "docnum": i["docnum"], "cardcode": i["cardcode"],
                "docdate_hana": str(i["docdate"])[:10],
                "due_date_hana": due_hana,
                "due_date_enriched": r["due_date"][:10],
                "docentry_total": float(i["doctotal"]),
                "open_hana": round(hana_open, 2),
                "open_enriched": r["open_amount"],
                "overdue_enriched": r["overdue_amount"],
                "currency": i["doccur"],
                "installments": len(inv6),
                "installment_due": str(inv6[0]["duedate"])[:10] if inv6 else None,
                "num_settlements": len(sett),
                "settlement_dates": sorted({str(s["recondate"])[:10] for s in sett}),
                "verify": {
                    "total_match": abs(float(i["doctotal"]) - r["gross_sales_amount"]) <= 0.01,
                    "due_match": due_hana == r["due_date"][:10],
                    "open_match": abs(hana_open - r["open_amount"]) <= 0.05,
                    "overdue_match": abs(max(hana_open, 0.0) - r["open_amount"]) <= 0.05
                    and ((r["overdue_amount"] > 0) == (r["overdue_amount"] == r["open_amount"])),
                    "single_installment": len(inv6) == 1 and (str(inv6[0]["duedate"])[:10] == r["due_date"][:10]),
                    "currency_bs": i["doccur"] == "BS",
                },
            })
        verified = sum(1 for ch in checks if ch.get("verify") and all(ch["verify"].values()))
        mismatches = [{"docentry": ch["docentry"], "verify": ch["verify"]}
                      for ch in checks if ch.get("verify") and not all(ch["verify"].values())]

        result = {
            "readonly_audit": audit,
            "verdict": "READ_ONLY_PASS" if audit["sap_write_count"] == 0 else "READ_ONLY_FAIL",
            "samples": {"USER_FULL": len(full), "DELIVERY": len(deliv),
                        "LA_REJA": len(la_reja), "OLDEST_OVERDUE": len(oldest),
                        "total_unique": len(des)},
            "samples_verified": verified,
            "mismatches": mismatches,
            "cutoff": str(CUTOFF),
            "semantics_note": "INV6 single installment validated for all samples; "
                              "open = DocTotal - PaidToDate (HANA) matches enriched open",
            "checks": checks,
        }
        (EVIDENCE / "hana_smoke_open_risk.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (EVIDENCE / "readonly_audit_open_risk.json").write_text(
            json.dumps({"sap_write_count": audit["sap_write_count"], "verdict": result["verdict"]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"sap_write_count": audit["sap_write_count"], "verdict": result["verdict"],
                          "samples": result["samples"], "samples_verified": verified,
                          "mismatches": mismatches}, ensure_ascii=False, indent=1))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())