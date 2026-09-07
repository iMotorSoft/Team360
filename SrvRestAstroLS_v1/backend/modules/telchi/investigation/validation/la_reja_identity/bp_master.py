"""PHASE 1/7/8 — Business Partner master + related parties for C010341 (READ ONLY).

  OCRD row (all relevant fields), CRD1 addresses, OCPR contacts,
  OCRG group (119 Socios), NIT comparison vs related parties (S0001..S0007,
  E000248), profile classifications (CardType/GroupCode/ListNum/SlpCode/
  Currency/CreditLine/Balance/UserSign/Create-Update dates, blocked status).
Outputs:
  evidence/bp_master.json
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
BP = "C010341"


def s(v):
    if v is None:
        return None
    if hasattr(v, "date"):
        return v.date().isoformat()
    if isinstance(v, (int, float)):
        return float(v)
    return str(v)


def main() -> None:
    conn, cur = connect()

    cur.execute('SELECT * FROM "TELCHI"."OCRD" WHERE "CardCode"=?', (BP,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    ocrd = {c: s(v) for c, v in zip(cols, row) if v not in (None, "")}

    keep = {}
    for k in ("CardCode", "CardName", "CardFName", "CardType", "GroupCode", "CmpPrivate",
              "LicTradNum", "Currency", "CreditLine", "Balance", "DNotesBal", "GroupNum",
              "ListNum", "SlpCode", "ShipToDef", "BillToDef", "PaymBlock", "validFor",
              "frozenFor", "Country", "CreateDate", "UpdateDate", "DataSource", "UserSign",
              "U_ORIGIN", "U_TIPDOC", "U_SO1_01VENCREVENC", "U_SO1_01AUTORIZARCOM",
              "U_ClienteExcepcional", "U_CONSIGNACION", "U_SO1_01ADDENDA", "U_ESTCLIENTE",
              "U_CATCLIENTE", "U_TIPOCLIENTE", "U_VendedorTB", "U_CANAL_VENTAS",
              "U_SUB_CANAL_VENTAS"):
        if k in ocrd:
            keep[k] = ocrd[k]
    keep["_all_populated_udfs"] = {k: v for k, v in ocrd.items() if k.startswith("U_")}

    # CRD1 addresses
    cur.execute('SELECT * FROM "TELCHI"."CRD1" WHERE "CardCode"=?', (BP,))
    ccols = [d[0] for d in cur.description]
    crd1 = [{c: s(v) for c, v in zip(ccols, r) if v not in (None, "")}
            for r in cur.fetchall()]

    # OCPR contacts
    cur.execute('SELECT * FROM "TELCHI"."OCPR" WHERE "CardCode"=?', (BP,))
    pcols = [d[0] for d in cur.description]
    ocpr = [{c: s(v) for c, v in zip(pcols, r) if v not in (None, "")}
            for r in cur.fetchall()]

    # OCRG group
    cur.execute('SELECT "GroupCode","GroupName","GroupType","Locked" FROM "TELCHI"."OCRG" WHERE "GroupCode"=119')
    ocrg = cur.fetchone()
    ocrg = {"groupcode": ocrg[0], "groupname": ocrg[1], "grouptype": ocrg[2], "locked": ocrg[3]} if ocrg else None

    # related parties (same group / family)
    cur.execute('''SELECT "CardCode","CardName","LicTradNum","GroupCode","Balance" FROM "TELCHI"."OCRD"
        WHERE "CardCode" IN ('S0001','S0002','S0003','S0004','S0005','S0006','S0007','E000248','C010341')''')
    related = [dict(zip(("cardcode", "cardname", "lic_trad_num", "groupcode", "balance"), r))
               for r in cur.fetchall()]

    # shares NIT with owner
    same_nit = [r for r in related if r["lic_trad_num"] == keep.get("LicTradNum") and r["cardcode"] != BP]
    # group members count
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."OCRD" WHERE "GroupCode"=119')
    group_members = cur.fetchone()[0]

    # OCRD notes/remark
    summary = {
        "bp": keep,
        "addresses": crd1,
        "contacts": ocpr,
        "group": ocrg,
        "group_members_total": group_members,
        "related_parties_same_nit": same_nit,
        "related_parties_group_119": related,
        "contact_persons": len(ocpr),
        "address_count": len(crd1),
        "nit_note": ("C010341 comparte NIT 1468238 con S0001 ROBERTO ABRAHAN TELCHI ASBUN "
                     "(propietario/inversionista grupo Socios) — señal fuerte de parte relacionada") if same_nit else None,
        "sap_write_count": 0,
    }
    (EVIDENCE / "bp_master.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "related_parties_group_119"},
                     ensure_ascii=False, indent=1, default=str))
    conn.close()


if __name__ == "__main__":
    main()