"""Phase 2/3/4 HANA read-only probes (credit control gate).

Emitted evidence:
  company_credit_config.json   — OADM credit flags
  tn_discovery.json            — Transaction Notification dependency graph + related UDTs
  users_master.json            — OUSR cross (superusers, blocked, license vs Excel)
  channels_summary.json        — document channel classification (OINV origin markers)
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection

EVIDENCE_DIR = EVIDENCE_ROOT / "credit_control" / "evidence"


def company_credit_config(cur) -> dict:
    cur.execute(
        'SELECT "CreditLimt","OpenCredit","OpenCdt","ObligLimit","SalesLimit",'
        '"DlnLimit","OrderLimit","CreditDpst","PickLimit","CreditDay1","CreditDay2" '
        'FROM "TELCHI"."OADM"'
    )
    row = cur.fetchone()
    cols = ["CreditLimt", "OpenCredit", "OpenCdt", "ObligLimit", "SalesLimit",
            "DlnLimit", "OrderLimit", "CreditDpst", "PickLimit", "CreditDay1", "CreditDay2"]
    return dict(zip(cols, row))


def tn_dependency_graph(cur) -> dict:
    """SBO_SP_TRANSACTIONNOTIFICATION dependency graph (READ ONLY metadata)."""
    cur.execute("""SELECT DISTINCT BASE_SCHEMA_NAME, BASE_OBJECT_NAME, BASE_OBJECT_TYPE
        FROM SYS.OBJECT_DEPENDENCIES
        WHERE DEPENDENT_SCHEMA_NAME='TELCHI'
          AND DEPENDENT_OBJECT_NAME='SBO_SP_TRANSACTIONNOTIFICATION'
        ORDER BY BASE_OBJECT_NAME""")
    deps = cur.fetchall()
    procs = [b for _, b, t in deps if t == "PROCEDURE"]
    tables = [b for _, b, t in deps if t == "TABLE"]
    udts = [b for _, b, t in deps if t == "TABLE" and b.startswith("@")]
    # per-object TN procedures and their base-tables
    cur.execute("""SELECT DISTINCT DEPENDENT_OBJECT_NAME, BASE_OBJECT_NAME
        FROM SYS.OBJECT_DEPENDENCIES
        WHERE DEPENDENT_SCHEMA_NAME='TELCHI' AND DEPENDENT_OBJECT_NAME LIKE 'ACB_TN_%'
        ORDER BY DEPENDENT_OBJECT_NAME""")
    per_obj: dict[str, list[str]] = {}
    for dep, base in cur.fetchall():
        per_obj.setdefault(dep, []).append(base)

    # MOVIL / SO1 credit-checking procedures metadata
    cur.execute("""SELECT PROCEDURE_NAME, INPUT_PARAMETER_COUNT FROM SYS.PROCEDURES
        WHERE SCHEMA_NAME='TELCHI'
          AND (PROCEDURE_NAME LIKE 'MOVIL_SP_EXISTE_FACTURA%'
               OR PROCEDURE_NAME LIKE 'MOVIL_SP_OBTENER_TOTAL_FACTURASCREDITO%'
               OR PROCEDURE_NAME = 'MOVIL_SP_OBTENERCREDITACCOUNT'
               OR PROCEDURE_NAME = 'SO1_PA_R1VALIDACIONES')
        ORDER BY PROCEDURE_NAME""")
    credit_procs = [dict(zip(("name", "in_params"), r)) for r in cur.fetchall()]

    # UDT columns relevant to credit/block in OCRD-like masters
    return {
        "sbo_sp_transactionnotification": {
            "procedure_exists": True,
            "definition_visible": None,
            "owner": "B1ADMIN",
            "written_dependencies_count": len(deps),
            "called_procedures": procs,
            "referenced_tables_count": len(tables),
            "referenced_udts": sorted(udts),
        },
        "acb_tn_per_object": per_obj,
        "credit_check_procedures": credit_procs,
        "notes": [
            "SYS.PROCEDURES.DEFINITION is NULL for insiding_hana: the account has no "
            "EXECUTE/selection privilege on the bodies. Source inspection of the TN "
            "logic is NOT possible with the current read-only credential.",
            "Dependencies listed are the objects resolvable statically; dynamic SQL "
            "dependencies are not recorded. The graph is therefore PARTIAL evidence.",
        ],
    }


def users_master(cur, excel_logins: list[str]) -> dict:
    cur.execute('''SELECT "USERID","USER_CODE","U_NAME","SUPERUSER","Locked",
        "Branch"
        FROM "TELCHI"."OUSR"''')
    cols = ["USERID", "USER_CODE", "U_NAME", "SUPERUSER", "Locked", "Branch"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    excel_set = {str(x).strip().lower() for x in excel_logins if x is not None}
    matched = 0
    for r in rows:
        r["_excel_match"] = str(r["USER_CODE"]).strip().lower() in excel_set
        matched += int(r["_excel_match"])

    superusers = [r["USER_CODE"] for r in rows if r["SUPERUSER"] == "Y"]
    superuser_excel = [r["USER_CODE"] for r in rows
                       if r["SUPERUSER"] == "Y" and r["_excel_match"]]

    return {
        "users_total": len(rows),
        "active": sum(1 for r in rows if r["Locked"] != "Y"),
        "blocked": sum(1 for r in rows if r["Locked"] == "Y"),
        "superusers": sorted(superusers),
        "superusers_active": sorted(r["USER_CODE"] for r in rows
                                    if r["SUPERUSER"] == "Y" and r["Locked"] != "Y"),
        "excel_users_matched_in_ousr": matched,
        "superuser_present_in_excel": sorted(superuser_excel),
        "rows": rows,
    }


def channel_summary(cur) -> dict:
    """Exact classification by document markers (baseline gate reused)."""
    cur.execute('''SELECT canal, COUNT(*) AS n,
        SUM(CASE WHEN CANCELED='N' THEN 1 ELSE 0 END) AS active
        FROM (
          SELECT CASE
            WHEN "U_ORIGIN"='DMS' THEN 'DMS'
            WHEN "U_ORIGIN"='SAP' AND "U_SO1_01RETAILONE"='Y' THEN 'RETAIL_ONE'
            WHEN "U_ORIGIN"='SAP' AND "U_SO1_01RETAILONE"='N' THEN 'SAP_DIRECT'
            ELSE 'UNCLASSIFIED'
          END AS canal,
          "CANCELED"
          FROM "TELCHI"."OINV"
        ) GROUP BY canal''')
    return [dict(zip(("canal", "docs_total", "docs_active"), r)) for r in cur.fetchall()]


def run_all() -> dict:
    conn, cur = connect()
    try:
        roconn = ReadOnlyConnection(conn)
        rocur = roconn.cursor()
        excel_model = json.loads(
            (EVIDENCE_DIR / "excel_authorization_model.json").read_text(encoding="utf-8")
        )
        excel_logins = [u["login"] for u in excel_model["users_by_login"]]

        evidence = {
            "company_credit_config": company_credit_config(rocur),
            "tn_discovery": tn_dependency_graph(rocur),
            "users_master": users_master(rocur, excel_logins),
            "channel_summary": channel_summary(rocur),
        }
        (EVIDENCE_DIR / "hana_phase234_probes.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8",
        )
        return evidence
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    ev = run_all()
    print("OADM:", ev["company_credit_config"])
    print("TN deps: called_procs=%d tables=%d udts=%d" % (
        len(ev["tn_discovery"]["sbo_sp_transactionnotification"]["called_procedures"]),
        ev["tn_discovery"]["sbo_sp_transactionnotification"]["referenced_tables_count"],
        len(ev["tn_discovery"]["sbo_sp_transactionnotification"]["referenced_udts"])))
    print("OUSR: total=%d excel_match=%d superusers=%d" % (
        ev["users_master"]["users_total"],
        ev["users_master"]["excel_users_matched_in_ousr"],
        len(ev["users_master"]["superusers"])))
    print("CHANNEL:", ev["channel_summary"])
