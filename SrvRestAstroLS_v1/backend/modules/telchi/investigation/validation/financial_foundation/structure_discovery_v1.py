#!/usr/bin/env python3
"""TELCHI financial/accounting foundation — structure discovery V1.

Investigation-only, SELECT-only HANA probe.  It establishes the first real
map for OACT/OJDT/JDT1 and discovers the standard financial objects used by
this installation.  It deliberately does not calculate a closed financial
position or claim the final foundation gate.

Outputs stay below INVESTIGATION_ROOT.  SAP_WRITE_COUNT is structurally zero:
this module only calls cursor.execute for SELECT statements and never commits.
"""
from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
DEFAULT_OUTPUT = ROOT / "validation" / "financial_foundation" / "structure_discovery_v1.json"

# SAP B1 object/header pairs to test against OJDT.TransId.  Existence is
# validated before execution so this remains safe on installations with fewer
# modules/tables.
OBJECT_MAP = OrderedDict(
    [
        ("13", "OINV"),
        ("14", "ORIN"),
        ("15", "ODLN"),
        ("16", "ORDN"),
        ("18", "OPCH"),
        ("19", "ORPC"),
        ("20", "OPDN"),
        ("21", "ORPD"),
        ("24", "ORCT"),
        ("25", "ODPS"),
        ("46", "OVPM"),
        ("59", "OIGN"),
        ("60", "OIGE"),
        ("67", "OWTR"),
        ("69", "OIPF"),
        ("162", "OMRV"),
        ("202", "OWOR"),
        ("321", "OITR"),
    ]
)

DISCOVERY_TABLES = (
    "OACT",
    "ODLN",
    "OIPF",
    "OMRV",
    "OPDN",
    "ORPD",
    "ORDN",
    "ORPC",
    "OIGN",
    "OIGE",
    "OWTR",
    "OWOR",
    "OITR",
    "OJDT",
    "JDT1",
    "OINV",
    "ORIN",
    "ORCT",
    "RCT1",
    "RCT2",
    "RCT3",
    "RCT4",
    "OPCH",
    "PCH5",
    "PCH6",
    "OVPM",
    "VPM1",
    "VPM2",
    "VPM3",
    "VPM4",
    "VPM5",
    "VPM6",
    "ODPS",
    "DPS1",
    "ODSC",
    "OCRB",
    "OCHO",
    "OCHH",
    "OBOE",
    "OWHT",
    "WHT1",
    "WHT2",
    "WHT3",
    "AWHT",
    "OTAX",
    "TAX1",
    "TAX2",
    "OFPR",
)


def fetch(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Run one SELECT and return plain serializable rows."""
    cur.execute(sql, params)
    columns = [str(desc[0]) for desc in (cur.description or ())]
    return columns, [tuple(row) for row in cur.fetchall()]


def rows_as_dicts(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row, strict=False)) for row in rows]


def scalar(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    _, rows = fetch(cur, sql, params)
    return rows[0][0] if rows else None


def serial(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal without importing Decimal
        return float(value)
    return value


def serial_rows(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{k: serial(v) for k, v in row.items()} for row in rows_as_dicts(columns, rows)]


def table_inventory(cur: Any) -> dict[str, Any]:
    columns, rows = fetch(
        cur,
        'SELECT "TABLE_NAME" FROM SYS.TABLES WHERE "SCHEMA_NAME"=? AND "TABLE_NAME" IN ('
        + ",".join("?" for _ in DISCOVERY_TABLES)
        + ') ORDER BY "TABLE_NAME"',
        ("TELCHI", *DISCOVERY_TABLES),
    )
    existing = [row[0] for row in rows]
    result: dict[str, Any] = {"existing": existing, "missing": [t for t in DISCOVERY_TABLES if t not in existing], "columns": {}}
    for table in existing:
        cols, col_rows = fetch(
            cur,
            'SELECT "COLUMN_NAME" FROM SYS.TABLE_COLUMNS WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"',
            ("TELCHI", table),
        )
        names = [row[0] for row in col_rows]
        result["columns"][table] = names
        result.setdefault("row_counts", {})[table] = int(
            scalar(cur, f'SELECT COUNT(*) FROM TELCHI."{table}"') or 0
        )
    return result


def gl_overview(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, sql in (
        (
            "ojdt",
            'SELECT COUNT(*) AS "COUNT", MIN("RefDate") AS "MIN_DATE", MAX("RefDate") AS "MAX_DATE" FROM TELCHI."OJDT"',
        ),
        (
            "jdt1",
            'SELECT COUNT(*) AS "COUNT", MIN("RefDate") AS "MIN_DATE", MAX("RefDate") AS "MAX_DATE" FROM TELCHI."JDT1"',
        ),
        ("oact", 'SELECT COUNT(*) AS "COUNT" FROM TELCHI."OACT"'),
    ):
        columns, rows = fetch(cur, sql)
        result[label] = serial_rows(columns, rows)[0]

    columns, rows = fetch(
        cur,
        '''SELECT "TransType", COUNT(*) AS "JOURNALS",
                  MIN("RefDate") AS "MIN_DATE", MAX("RefDate") AS "MAX_DATE",
                  SUM("LocTotal") AS "LOC_TOTAL", SUM("SysTotal") AS "SYS_TOTAL",
                  SUM(CASE WHEN "CreatedBy"="TransId" THEN 1 ELSE 0 END) AS "CREATEDBY_SELF",
                  SUM(CASE WHEN "StornoToTr" IS NOT NULL THEN 1 ELSE 0 END) AS "HAS_STORNO_TO_TR",
                  SUM(CASE WHEN COALESCE("Memo",'')='' THEN 1 ELSE 0 END) AS "EMPTY_MEMO"
           FROM TELCHI."OJDT"
           GROUP BY "TransType" ORDER BY "JOURNALS" DESC''',
    )
    result["transtype_profile"] = serial_rows(columns, rows)

    columns, rows = fetch(
        cur,
        '''SELECT "GroupMask", COUNT(*) AS "ACCOUNTS",
                  SUM(CASE WHEN "Postable"='Y' THEN 1 ELSE 0 END) AS "POSTABLE",
                  SUM(CASE WHEN "ValidFor"='Y' THEN 1 ELSE 0 END) AS "VALID",
                  SUM(CASE WHEN "FrozenFor"='Y' THEN 1 ELSE 0 END) AS "FROZEN",
                  SUM("CurrTotal") AS "CURR_TOTAL", SUM("SysTotal") AS "SYS_TOTAL"
           FROM TELCHI."OACT" GROUP BY "GroupMask" ORDER BY "GroupMask"''',
    )
    result["account_group_profile"] = serial_rows(columns, rows)
    return result


def document_map(cur: Any, inventory: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for trans_type, table in OBJECT_MAP.items():
        if table not in inventory["existing"]:
            result.append({"trans_type": trans_type, "table": table, "status": "TABLE_MISSING"})
            continue
        # These headers are known to expose TransId in this installation; the
        # catalog is consulted first and no fallback assumptions are used.
        if "TransId" not in inventory["columns"].get(table, []):
            result.append({"trans_type": trans_type, "table": table, "status": "TRANSID_COLUMN_MISSING"})
            continue
        sql = f'''
            SELECT COUNT(*) AS "HEADERS", COUNT(H."TransId") AS "WITH_TRANSID",
                   COUNT(DISTINCT H."TransId") AS "DISTINCT_HEADER_TRANSID",
                   COUNT(DISTINCT J."TransId") AS "OJDT_MATCH"
            FROM TELCHI."{table}" H
            LEFT JOIN TELCHI."OJDT" J ON H."TransId"=J."TransId"'''
        columns, rows = fetch(cur, sql)
        item = serial_rows(columns, rows)[0]
        item.update({"trans_type": trans_type, "table": table})
        item["coverage_pct"] = round(
            100.0 * item["OJDT_MATCH"] / item["WITH_TRANSID"] if item["WITH_TRANSID"] else 0.0,
            4,
        )
        item["status"] = "PASS" if item["WITH_TRANSID"] == item["OJDT_MATCH"] else "PARTIAL"
        result.append(item)
    return result


def account_profiles(cur: Any) -> dict[str, Any]:
    base = '''
        SELECT A."AcctCode", A."AcctName", A."GroupMask", A."FatherNum",
               A."Postable", A."CashBox", A."Advance", A."ActCurr",
               A."CurrTotal", A."SysTotal", A."ValidFor", A."FrozenFor",
               COALESCE(M."LINES",0) AS "LINES", COALESCE(M."TRANS",0) AS "TRANS",
               COALESCE(M."DEBIT",0) AS "DEBIT", COALESCE(M."CREDIT",0) AS "CREDIT",
               COALESCE(M."NET",0) AS "NET", COALESCE(M."GROSS",0) AS "GROSS"
        FROM TELCHI."OACT" A
        LEFT JOIN (
          SELECT "Account", COUNT(*) AS "LINES", COUNT(DISTINCT "TransId") AS "TRANS",
                 SUM("Debit") AS "DEBIT", SUM("Credit") AS "CREDIT",
                 SUM("Debit"-"Credit") AS "NET", SUM("Debit"+"Credit") AS "GROSS"
          FROM TELCHI."JDT1" GROUP BY "Account"
        ) M ON M."Account"=A."AcctCode"
    '''
    out: dict[str, Any] = {}
    for key, order in (("top_net", 'ORDER BY ABS(COALESCE(M."NET",0)) DESC'), ("top_gross", 'ORDER BY COALESCE(M."GROSS",0) DESC')):
        columns, rows = fetch(cur, base + order + " LIMIT 50")
        out[key] = serial_rows(columns, rows)

    columns, rows = fetch(
        cur,
        '''SELECT "AcctCode","AcctName","FatherNum","GroupMask","Postable","CashBox",
                         "Advance","ActCurr","CurrTotal","SysTotal","ValidFor","FrozenFor"
                  FROM TELCHI."OACT"
                  WHERE "AcctCode" LIKE '111%' OR "AcctCode" LIKE '11201%'
                     OR "AcctCode" LIKE '11203%' OR "AcctCode" LIKE '11213%'
                     OR "AcctCode" LIKE '11214%' OR "AcctCode" LIKE '11215%'
                     OR "AcctCode" LIKE '211%' OR "AcctCode" LIKE '214%'
                  ORDER BY "AcctCode"''',
    )
    out["financial_family_accounts"] = serial_rows(columns, rows)
    return out


def trace_samples(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    # One payment reconciliation with multiple invoice members, selected from
    # 2023-02 to keep continuity with previous Telchi financial gates.
    columns, rows = fetch(
        cur,
        '''SELECT P."DocEntry" AS "PAYMENT_DOCENTRY", P."DocNum" AS "PAYMENT_DOCNUM",
                  P."DocDate" AS "PAYMENT_DATE", P."CardCode", P."DocTotal" AS "PAYMENT_TOTAL",
                  P."DocCurr", P."TransId" AS "PAYMENT_TRANSID", R."ReconNum",
                  V."DocEntry" AS "INVOICE_DOCENTRY", V."DocNum" AS "INVOICE_DOCNUM",
                  V."DocDate" AS "INVOICE_DATE", V."DocDueDate", V."DocTotal" AS "INVOICE_TOTAL",
                  V."PaidToDate", V."TransId" AS "INVOICE_TRANSID"
           FROM TELCHI."ORCT" P
           JOIN TELCHI."ITR1" IP ON IP."SrcObjTyp"='24' AND IP."SrcObjAbs"=P."DocEntry"
           JOIN TELCHI."OITR" R ON R."ReconNum"=IP."ReconNum" AND R."Canceled"='N'
           JOIN TELCHI."ITR1" IV ON IV."ReconNum"=R."ReconNum" AND IV."SrcObjTyp"='13'
           JOIN TELCHI."OINV" V ON V."DocEntry"=IV."SrcObjAbs"
           WHERE P."Canceled"='N' AND P."DocDate">='2023-02-01' AND P."DocDate"<'2023-03-01'
           ORDER BY P."DocTotal" DESC LIMIT 1''',
    )
    if rows:
        sample = serial_rows(columns, rows)[0]
        result["ar_payment_invoice"] = sample
        recon_num = sample.get("RECONNUM", sample.get("ReconNum"))
        columns, rows = fetch(
            cur,
            'SELECT "ReconNum","LineSeq","SrcObjTyp","SrcObjAbs","TransId","TransRowId","ReconSum","IsCredit","ShortName","Account" FROM TELCHI."ITR1" WHERE "ReconNum"=? ORDER BY "LineSeq"',
            (recon_num,),
        )
        result["ar_reconciliation_members"] = serial_rows(columns, rows)
        for label, trans_id in (("invoice_journal", sample["INVOICE_TRANSID"]), ("payment_journal", sample["PAYMENT_TRANSID"])):
            columns, rows = fetch(
                cur,
                'SELECT "TransId","Line_ID","Account","Debit","Credit","ContraAct","LineMemo","ShortName","TransType","DocEntry","DocNum" FROM TELCHI."JDT1" WHERE "TransId"=? ORDER BY "Line_ID"',
                (trans_id,),
            )
            result[label] = serial_rows(columns, rows)

    columns, rows = fetch(
        cur,
        '''SELECT P."DocEntry" AS "PAYMENT_DOCENTRY", P."DocNum" AS "PAYMENT_DOCNUM",
                  P."DocDate" AS "PAYMENT_DATE", P."CardCode", P."DocTotal" AS "PAYMENT_TOTAL",
                  P."DocCurr", P."CashSum", P."CheckSum", P."TrsfrSum", P."CreditSum",
                  P."TransId" AS "PAYMENT_TRANSID", M."InvType", M."DocEntry" AS "AP_DOCENTRY",
                  M."SumApplied", V."DocNum" AS "AP_DOCNUM", V."DocDate" AS "AP_DATE",
                  V."DocDueDate", V."DocTotal" AS "AP_TOTAL", V."WTSum" AS "AP_WTSUM",
                  V."CANCELED", V."TransId" AS "AP_TRANSID"
           FROM TELCHI."OVPM" P
           JOIN TELCHI."VPM2" M ON M."DocNum"=P."DocEntry" AND M."InvType"='18'
           JOIN TELCHI."OPCH" V ON V."DocEntry"=M."DocEntry"
           WHERE P."Canceled"='N' AND V."CANCELED"='N'
           ORDER BY P."DocTotal" DESC LIMIT 1''',
    )
    if rows:
        sample = serial_rows(columns, rows)[0]
        result["ap_payment_invoice"] = sample
        for label, trans_id in (("ap_invoice_journal", sample["AP_TRANSID"]), ("ap_payment_journal", sample["PAYMENT_TRANSID"])):
            columns, rows = fetch(
                cur,
                'SELECT "TransId","Line_ID","Account","Debit","Credit","ContraAct","LineMemo","ShortName","TransType","DocEntry","DocNum","WTaxCode","WTSum" FROM TELCHI."JDT1" WHERE "TransId"=? ORDER BY "Line_ID"',
                (trans_id,),
            )
            result[label] = serial_rows(columns, rows)

    columns, rows = fetch(
        cur,
        '''SELECT "DeposId","DeposType","DeposNum","DeposDate","DeposCurr","DpsBank",
                  "DeposAcct","BanckAcct","AllocAcct","Canceled","LocTotal","TransAbs",
                  "BPLId","U_SUC","U_Fecha_ventas"
           FROM TELCHI."ODPS" WHERE "Canceled"='N' ORDER BY "DeposDate" DESC,"DeposId" DESC LIMIT 1''',
    )
    if rows:
        sample = serial_rows(columns, rows)[0]
        result["deposit"] = sample
        columns, rows = fetch(
            cur,
            'SELECT "TransId","Line_ID","Account","Debit","Credit","ContraAct","LineMemo","ShortName","TransType","DocEntry","DocNum" FROM TELCHI."JDT1" WHERE "TransId"=? ORDER BY "Line_ID"',
            (sample.get("TRANSABS", sample.get("TransAbs")),),
        )
        result["deposit_journal"] = serial_rows(columns, rows)
    return result


def payment_profiles(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table, cancel_col in (("ORCT", "Canceled"), ("OVPM", "Canceled")):
        columns, rows = fetch(
            cur,
            f'''SELECT "{cancel_col}" AS "CANCELED", COUNT(*) AS "COUNT",
                       SUM("DocTotal") AS "DOC_TOTAL", SUM("CashSum") AS "CASH",
                       SUM("CheckSum") AS "CHECKS", SUM("TrsfrSum") AS "TRANSFERS",
                       SUM("CreditSum") AS "CARDS", SUM("NoDocSum") AS "NO_DOC"
                FROM TELCHI."{table}" GROUP BY "{cancel_col}" ORDER BY "{cancel_col}"''',
        )
        result[table] = serial_rows(columns, rows)
    return result


def wht_and_deposit_profiles(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "OWHT" in DISCOVERY_TABLES:
        columns, rows = fetch(cur, 'SELECT "WTCode","WTName","Rate","PrctBsAmnt","Account","ApTdsAcc","ArTdsAcc","Inactive","UseInAPDPR","EffecDate" FROM TELCHI."OWHT" ORDER BY "WTCode"')
        result["configured_withholding_codes"] = serial_rows(columns, rows)
    for label, sql in (
        (
            "opch_wht_fields",
            'SELECT COUNT(*) AS "DOCS", SUM("WTSum") AS "WTSUM", SUM("WTApplied") AS "WTAPPLIED" FROM TELCHI."OPCH"',
        ),
        (
            "ovpm_wht_fields",
            'SELECT COUNT(*) AS "DOCS", SUM("WtSum") AS "WTSUM" FROM TELCHI."OVPM"',
        ),
        (
            "pch5_nonzero",
            'SELECT COUNT(*) AS "ROWS", COALESCE(SUM("WTAmnt"),0) AS "WTAMNT", COALESCE(SUM("ApplAmnt"),0) AS "APPLAMNT" FROM TELCHI."PCH5" WHERE "WTAmnt"<>0',
        ),
        (
            "pchn_installment_wht",
            'SELECT COUNT(*) AS "ROWS", COALESCE(SUM("WTSum"),0) AS "WTSUM", COALESCE(SUM("WTApplied"),0) AS "WTAPPLIED" FROM TELCHI."PCH6" WHERE "WTSum"<>0',
        ),
        (
            "vpm6_nonzero",
            'SELECT COUNT(*) AS "ROWS", COALESCE(SUM("WTSum"),0) AS "WTSUM", COALESCE(SUM("WTPosted"),0) AS "WTPOSTED" FROM TELCHI."VPM6" WHERE "WTSum"<>0',
        ),
    ):
        try:
            columns, rows = fetch(cur, sql)
            result[label] = serial_rows(columns, rows)[0]
        except Exception as exc:  # metadata discovery stays useful if an optional table differs
            result[label] = {"status": "QUERY_ERROR", "error_type": type(exc).__name__}
    return result


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        inventory = table_inventory(cur)
        report: dict[str, Any] = {
            "report_id": "TELCHI_FINANCIAL_ACCOUNTING_FOUNDATION_STRUCTURE_DISCOVERY_V1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "entity": "TELCHI",
            "domain": "CONTABILIDAD",
            "stage": "INVESTIGATION",
            "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True},
            "sap_write_count": 0,
            "inventory": inventory,
            "gl_overview": gl_overview(cur),
            "document_to_ojdt_map": document_map(cur, inventory),
            "account_profiles": account_profiles(cur),
            "payment_profiles": payment_profiles(cur),
            "withholding_and_tax_discovery": wht_and_deposit_profiles(cur),
            "trace_samples": trace_samples(cur),
            "limitations": [
                "This is the first structural execution, not the final financial foundation gate.",
                "OACT CurrTotal/SysTotal currency semantics and period behavior require explicit validation before cross-currency totals.",
                "Transaction Type 30 is a journal-entry object; automatic/manual classification is not inferred solely from UserSign or empty Memo.",
                "Withholding configuration is present, but transactional WHT lifecycle and period aging are still unresolved.",
                "Deposit linkage is documented at ODPS.TransAbs -> OJDT.TransId; cobro-to-deposit timing still requires a dedicated relation study.",
            ],
        }
        return report
    finally:
        cur.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=serial), encoding="utf-8")
    print(f"report={args.output}")
    print(f"SAP_WRITE_COUNT={report['sap_write_count']}")
    print(f"OJDT={report['gl_overview']['ojdt']['COUNT']} JDT1={report['gl_overview']['jdt1']['COUNT']} OACT={report['gl_overview']['oact']['COUNT']}")
    print(f"transtypes={len(report['gl_overview']['transtype_profile'])} mapped_objects={len(report['document_to_ojdt_map'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
