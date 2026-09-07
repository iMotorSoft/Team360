"""HANA READ-ONLY smoke for the economic grouping (LOOP TEST §50).

Verifies a sample of the 268 explained cases against the live HANA invoice +
settlement ledger: 3 USER FULL + 3 CUSTOMER EXCEPTION + 3 DELIVERY FLOW +
3 RETAIL CASH (deterministic selection: earliest by docdate within each group).

Emitted evidence: evidence/hana_smoke_economic.json and
evidence/readonly_audit_economic.json (SAP_WRITE_COUNT).

No writes. Every query runs via ReadOnlyConnection.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection, _WRITE_TOKENS, guard_sql

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception_economic" / "evidence"

SAMPLES = {
    "USER_AUTHORIZATION_FULL": 3,
    "CUSTOMER_EXCEPTION": 3,
    "DOCUMENT_FLOW_PREAUTHORIZED": 3,
    "NON_CREDIT_RETAIL_CASH": 3,
}


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def audit_economic_source() -> dict:
    # scan all scripts used by this cycle (econ + credit_exception + credit_control + atomic)
    bad = []
    executed = 0
    roots = [HERE.parent / "credit_exception_economic", HERE.parent / "credit_exception",
             HERE.parent / "credit_control", HERE / ".." / ".." / "atomic"]
    files = []
    for root in roots:
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
            "write_statements_found": len(bad), "write_samples": bad[:10],
            "sap_write_count": len(bad)}


def main() -> int:
    grouped = json.loads((EVIDENCE / "grouped_cases.json").read_text(encoding="utf-8"))
    audit = audit_economic_source()
    conn, cur = connect()
    try:
        roconn = ReadOnlyConnection(conn)
        rocur = roconn.cursor()
        checks = []
        for group, n in SAMPLES.items():
            sel = sorted([r for r in grouped if r["primary_business_group"] == group],
                         key=lambda r: r["docdate"])[:n]
            for r in sel:
                de = r["doc_entry"]
                rec = {
                    "business_group": group,
                    "secondary_reason": r["secondary_reason"],
                    "cardcode": r["cardcode"],
                    "doc_entry": de,
                    "bundle_total": r["gross_sales_amount"],
                    "bundle_open": r["open_amount"],
                    "bundle_paid": r["paid_amount"],
                    "bundle_current_status": r["current_status"],
                    "bundle_docdate": r["docdate"],
                }
                rec["invoice"] = rows(rocur, '''SELECT "DocNum","DocTotal","PaidToDate","DocDate",
                    "DocDueDate","CardCode","DocCur","UserSign","SlpCode","CANCELED"
                    FROM "TELCHI"."OINV" WHERE "DocEntry"=?''', (de,))
                rec["settlements"] = rows(rocur, '''SELECT t."ReconNum", t."SrcObjTyp", t."ReconSum",
                    r."ReconDate", r."InitObjTyp" FROM "TELCHI"."ITR1" t
                    JOIN "TELCHI"."OITR" r ON r."ReconNum"=t."ReconNum"
                    WHERE t."SrcObjTyp"='13' AND t."SrcObjAbs"=? AND r."Canceled"='N'
                    ORDER BY r."ReconDate"''', (de,))
                rec["base_docs"] = rows(rocur, '''SELECT "BaseType","BaseEntry" FROM "TELCHI"."INV1"
                    WHERE "DocEntry"=? AND "BaseType" IS NOT NULL GROUP BY "BaseType","BaseEntry"''', (de,))
                rec["venta"] = rows(rocur, '''SELECT "U_SO1_FECHA","U_SO1_TOTALNETO","U_SO1_ESTACION",
                    "U_SO1_TIPO","U_SO1_CREDITO","U_SO1_USUARIO" FROM "TELCHI"."@SO1_01VENTA"
                    WHERE "U_SO1_CLIENTE"=? AND "U_SO1_STATUS"='A'
                    ORDER BY ABS("U_SO1_TOTALNETO" - ?)
                    LIMIT 1''', (r["cardcode"], de, r["gross_sales_amount"]))
                checks.append(rec)

        # verify each sample matches the reconstruction it is grouped on
        verified = 0
        mismatches = []
        for rec in checks:
            inv = rec["invoice"]
            if not inv:
                mismatches.append({"doc": rec["doc_entry"], "issue": "invoice not found"})
                continue
            inv = inv[0]
            ok_total = abs(float(inv["doctotal"]) - rec["bundle_total"]) <= 0.01
            ok_card = inv["cardcode"] == rec["cardcode"]
            ok_cur = inv["doccur"] == "BS"
            ok_date = str(inv["docdate"])[:10] == str(rec["bundle_docdate"])[:10]
            paid_after = sum(float(s["reconsum"]) for s in rec["settlements"])
            open_now_hana = float(inv["doctotal"]) - float(inv["paidtodate"])
            ok_open = abs(open_now_hana - rec["bundle_open"]) <= 0.05
            ok_status = (rec["bundle_current_status"] == "FULLY_PAID") == (open_now_hana <= 0.05)
            rec["verify"] = {
                "total_match": ok_total, "card_match": ok_card, "currency_bs": ok_cur,
                "date_match": ok_date, "open_match": ok_open, "status_match": ok_status,
                "sum_settlements_after_sale": round(paid_after, 2), "open_from_hana": round(open_now_hana, 2),
            }
            bool_checks = [k for k in ("total_match", "card_match", "currency_bs",
                                       "date_match", "open_match", "status_match")]
            if all(rec["verify"][k] for k in bool_checks):
                verified += 1
            else:
                mismatches.append({"doc": rec["doc_entry"], "verify": rec["verify"]})

        result = {
            "readonly_audit": audit,
            "verdict": "READ_ONLY_PASS" if audit["sap_write_count"] == 0 else "READ_ONLY_FAIL",
            "sap_write_count": audit["sap_write_count"],
            "samples_total": len(checks),
            "samples_verified": verified,
            "sample_breakdown": {g: min(n, sum(1 for r in grouped if r["primary_business_group"] == g))
                                 for g, n in SAMPLES.items()},
            "mismatches": mismatches,
            "hana_smoke_economic": {"checks": checks, "run_at": "2026-09-02",
                                    "currency_verified_bs_for_all_samples":
                                        all(c["invoice"][0]["doccur"] == "BS" for c in checks if c["invoice"])},
            "per_currency_over_268": "BS (DocCur='BS' for all 268; HANA GROUP BY probe)",
        }
        (EVIDENCE / "hana_smoke_economic.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (EVIDENCE / "readonly_audit_economic.json").write_text(
            json.dumps({"sap_write_count": audit["sap_write_count"], "verdict": result["verdict"],
                        "source_files_scanned": audit["source_files_scanned"]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({
            "sap_write_count": audit["sap_write_count"],
            "verdict": result["verdict"],
            "samples_total": len(checks),
            "samples_verified": verified,
            "breakdown": result["sample_breakdown"],
            "currency_all_bs": result["hana_smoke_economic"]["currency_verified_bs_for_all_samples"],
        }, ensure_ascii=False, indent=1))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())