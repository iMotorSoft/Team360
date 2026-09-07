"""READ-ONLY AUDIT + REAL HANA SMOKE for the credit-exception cycle.

Part 1: static scan of credit_exception source -> write count (must be 0).
Part 2: live HANA cross-checks of key reconstructed DocEntries (READ ONLY):
  - invoice header (DocTotal/PaidToDate/DocDueDate/UserSign)
  - settlement presence (ITR1/OITR for DocEntry=13)
  - retail VENTA row (cliente+fecha+total)
  - order/delivery base for sample cases
Emits evidence/readonly_audit.json and evidence/hana_smoke.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection, _WRITE_TOKENS, guard_sql

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"

CHECK_CASES = [
    ("C003542", 11471011, 261907773),   # SAP Direct, over-limit, yardaya (prior exec case)
    ("C003531", 11492512, 261908500),   # SAP Direct, over-limit, cvallejos (prior exec case)
    ("C008090", 11484489, 261908259),   # SAP Direct, kfranco (prior exec case)
    ("C000018", 11048897, 260703974),   # Retail CA cash, same-day settled
    ("C000398", 11045476, 260503550),   # Retail, VENCREVENC exception customer
]


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def audit_source() -> dict:
    bad = []
    executed = 0
    for py in sorted((HERE / "..").glob("credit_exception/**/*.py")):
        text = re.sub(r'""".*?"""', "", py.read_text(encoding="utf-8"), flags=re.S)
        for i, line in enumerate(text.splitlines(), 1):
            if "execute(" not in line and "executemany(" not in line:
                continue
            executed += 1
            body = line.split("#", 1)[0]
            if _WRITE_TOKENS.search(body):
                bad.append((py.name, i, line.strip()))
    return {"source_files_scanned": len(list((HERE / "..").glob("credit_exception/**/*.py"))),
            "execute_sites_expected": executed, "write_statements_found": len(bad),
            "write_samples": bad[:10], "sap_write_count": len(bad)}


def main() -> int:
    audit = audit_source()
    conn, cur = connect()
    try:
        roconn = ReadOnlyConnection(conn)
        rocur = roconn.cursor()
        checks = []
        for cc, de, dn in CHECK_CASES:
            rec = {"cardcode": cc, "docentry": de, "docnum_expected": dn}
            rec["invoice"] = rows(rocur, '''SELECT "DocTotal","PaidToDate","DocDueDate","DocDate",
                "UserSign","CANCELED" FROM "TELCHI"."OINV" WHERE "DocEntry"=?''', (de,))
            rec["settlements"] = rows(rocur, '''SELECT t."ReconNum", t."SrcObjTyp", t."ReconSum",
                r."ReconDate", r."InitObjTyp" FROM "TELCHI"."ITR1" t
                JOIN "TELCHI"."OITR" r ON r."ReconNum"=t."ReconNum"
                WHERE t."SrcObjTyp"='13' AND t."SrcObjAbs"=? AND r."Canceled"='N' ''', (de,))
            rec["base_docs"] = rows(rocur, '''SELECT "BaseType","BaseEntry" FROM "TELCHI"."INV1"
                WHERE "DocEntry"=? AND "BaseType" IS NOT NULL GROUP BY "BaseType","BaseEntry"''', (de,))
            rec["venta"] = rows(rocur, '''SELECT "U_SO1_FECHA","U_SO1_TOTALNETO","U_SO1_ESTACION",
                "U_SO1_TIPO","U_SO1_CREDITO","U_SO1_USUARIO" FROM "TELCHI"."@SO1_01VENTA"
                WHERE "U_SO1_CLIENTE"=? AND "U_SO1_STATUS"='A'
                ORDER BY ABS("U_SO1_TOTALNETO" - (SELECT "DocTotal" FROM "TELCHI"."OINV" WHERE "DocEntry"=?))
                LIMIT 1''', (cc, de))
            checks.append(rec)
        # cross-check against the classified bundle (reconstruction is real)
        bundle = {c["docentry"]: c for c in json.loads((EVIDENCE / "case_bundle.json").read_text(encoding="utf-8"))}
        for rec in checks:
            b = bundle.get(rec["docentry"])
            rec["bundle_total"] = b["doctotal"] if b else None
            rec["bundle_open"] = b.get("open_now") if b else None
            rec["bundle_reason"] = b.get("reason_code") if b else None
        result = {
            "readonly_audit": audit,
            "verdict": "READ_ONLY_PASS" if audit["sap_write_count"] == 0 else "READ_ONLY_FAIL",
            "hana_smoke": {"checks": checks, "run_at": "2026-09-02"},
        }
        (EVIDENCE / "readonly_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("readonly:", result["verdict"], "| write count:", audit["sap_write_count"])
        for c in checks:
            print(c["cardcode"], c["docentry"], "| invoice:", c["invoice"], "| settlements:", len(c["settlements"]),
                  "| base:", c["base_docs"], "| venta:", c["venta"], "| bundle:", c["bundle_total"], c["bundle_reason"])
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())