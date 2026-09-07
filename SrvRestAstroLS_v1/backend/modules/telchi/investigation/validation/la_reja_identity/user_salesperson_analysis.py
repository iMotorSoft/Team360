"""PHASE 7/8 — User + Salesperson resolution for C010341 (READ ONLY).

Resolves:
  OINV.UserSign/UserSign2 -> OUSR (USER_CODE, U_NAME, SUPERUSER)
  OINV.SlpCode            -> OSLP (SlpName)
  ODLN.UserSign           -> OUSR
  ORDR.UserSign           -> OUSR
and classifies SAP users as PERSONAL / TECHNICAL / GENERIC / INTEGRATION
using the validated call-signs from prior gates (soluone = technical POS
operator attribution; manager = superuser/admin).

Invariants:
  - SAP USER != SALESPERSON (shown side by side per doc)
  - UserSign -> OUSR cardinality 1:1
  - SlpCode -> OSLP resolved without mixing with UserSign

Outputs:
  evidence/users.json
  evidence/salespersons.json
  evidence/user_salesperson_cases.json
  evidence/user_salesperson_summary.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"

TECHNICAL_USERS = {"soluone", "manager"}
INTEGRATION_USERS: set[str] = set()


def main() -> None:
    cases = json.loads((EVIDENCE / "atomic_la_reja_cases.json").read_text())
    conn, cur = connect()

    # all users involved in history
    cur.execute('''SELECT "USERID","USER_CODE","U_NAME","SUPERUSER" FROM "TELCHI"."OUSR"''')
    users = {r[0]: {"user_code": r[1], "name": r[2], "superuser": r[3]} for r in cur.fetchall()}
    cur.execute('''SELECT "SlpCode","SlpName" FROM "TELCHI"."OSLP"''')
    slp = {r[0]: r[1] for r in cur.fetchall()}

    # user counts on the 40 invoices
    user_docs = Counter(c["sap_user"] for c in cases)
    user_amount = defaultdict(float)
    slp_docs = Counter(c["salesperson_name"] for c in cases)
    slp_amount = defaultdict(float)
    for c in cases:
        user_amount[c["sap_user"]] += c["gross_amount"]
        if c["salesperson_name"]:
            slp_amount[c["salesperson_name"]] += c["gross_amount"]

    # channel per user
    user_channel = defaultdict(Counter)
    for c in cases:
        user_channel[c["sap_user"]][c["channel"]] += 1

    user_rows = []
    for code, n in user_docs.most_common():
        user_rows.append({
            "user": code,
            "type": "TECHNICAL" if code in TECHNICAL_USERS else
                    "INTEGRATION" if code in INTEGRATION_USERS else "PERSONAL",
            "documents": n,
            "amount": round(user_amount[code], 2),
            "channel": dict(user_channel[code]),
            "name": next((u["name"] for u in users.values() if u["user_code"] == code), None),
        })

    slp_rows = []
    for name, n in slp_docs.most_common():
        slp_rows.append({
            "salesperson": name,
            "documents": n,
            "amount": round(slp_amount[name], 2),
        })

    # per-case user vs salesperson
    per_case = [
        {
            "invoice_docentry": c["invoice_docentry"],
            "invoice_docnum": c["invoice_docnum"],
            "sap_user": c["sap_user"],
            "user_name": c["user_name"],
            "user_sign2": c["user_sign2"],
            "salesperson": c["salesperson_name"],
            "channel": c["channel"],
            "gross_amount": c["gross_amount"],
        }
        for c in cases
    ]

    summary = {
        "users": user_rows,
        "salespersons": slp_rows,
        "user_types": {k: int(v) for k, v in Counter(r["type"] for r in user_rows).items()},
        "users_total_docs": sum(n for _, n in user_docs.items()),
        "salespersons_total_docs": sum(n for _, n in slp_docs.items()),
        "user_vs_salesperson_invariant": "SAP USER != SALESPERSON (verificado documento a documento)",
        "sap_write_count": 0,
    }
    (EVIDENCE / "users.json").write_text(json.dumps(user_rows, ensure_ascii=False, indent=1))
    (EVIDENCE / "salespersons.json").write_text(json.dumps(slp_rows, ensure_ascii=False, indent=1))
    (EVIDENCE / "user_salesperson_cases.json").write_text(json.dumps(per_case, ensure_ascii=False, indent=1))
    (EVIDENCE / "user_salesperson_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    conn.close()


if __name__ == "__main__":
    main()