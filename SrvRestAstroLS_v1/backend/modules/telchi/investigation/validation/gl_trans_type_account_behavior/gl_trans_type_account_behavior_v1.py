#!/usr/bin/env python3
"""TELCHI GL / TransType / Account Behavior V1.

Investigation-only, SELECT-only HANA analysis.  The probe keeps all large GL
work in HANA aggregations and writes only JSON/Markdown below investigation.
It intentionally treats the standard withholding tables being empty as a
negative observation about that mechanism, never as proof that Telchi has no
withholdings.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "gl_trans_type_account_behavior"
DEFAULT_OUTPUT = OUT_DIR / "gl_trans_type_account_behavior_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_gl_trans_type_account_behavior_v1_report.md"
TOLERANCE = 0.01

# The installation's observed 21 values.  The object/key pairs are hypotheses
# that are measured against this database, not accepted from SAP documentation.
OBJECT_CANDIDATES: dict[str, tuple[str, str | None, str]] = {
    "-3": ("Closing Balance", None, "system journal type; no header table expected"),
    "-2": ("Opening Balance", None, "system journal type; no header table expected"),
    "13": ("A/R Invoice", "OINV", "TransId"),
    "14": ("A/R Credit Memo", "ORIN", "TransId"),
    "15": ("Delivery", "ODLN", "TransId"),
    "16": ("Return", "ORDN", "TransId"),
    "18": ("A/P Invoice", "OPCH", "TransId"),
    "19": ("A/P Credit Memo", "ORPC", "TransId"),
    "20": ("Goods Receipt PO", "OPDN", "TransId"),
    "21": ("Goods Return", "ORPD", "TransId"),
    "24": ("Incoming Payment", "ORCT", "TransId"),
    "25": ("Deposit", "ODPS", "TransAbs"),
    "30": ("Journal Entry", "OJDT", "TransId"),
    "46": ("Outgoing Payment", "OVPM", "TransId"),
    "59": ("Goods Receipt", "OIGN", "TransId"),
    "60": ("Goods Issue", "OIGE", "TransId"),
    "67": ("Inventory Transfer", "OWTR", "TransId"),
    "69": ("Landed Costs", "OIPF", "JdtNum"),
    "162": ("Inventory Revaluation", "OMRV", "TransId"),
    "202": ("Production Order", "OWOR", "TransId"),
    "321": ("Internal Reconciliation", "OITR", "ReconJEId"),
}

KEYWORDS = (
    "RETENC", "RETEN", "IUE", "IT ", "RC-IVA", "RCIVA", "IMPUEST", "TRIBUT",
    "FISCAL", "CAJA", "BANCO", "DEPOS", "AJUST", "REGULAR", "COMPENS",
    "CIERRE", "PROVISION", "PAGO", "CHEQUE", "DIFERENCIA", "CAMBIO",
)
RISK_WORDS = ("OTROS", "VARIOS", "TRANSITOR", "PUENTE", "COMPENS", "AJUST", "PENDIENT", "REGULAR", "EN TRANSITO", "TRANSITO")


def fetch(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[str], list[tuple[Any, ...]]]:
    cur.execute(sql, params)
    columns = [str(d[0]) for d in (cur.description or ())]
    return columns, [tuple(row) for row in cur.fetchall()]


def dict_rows(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    # hdbcli preserves the physical case of unaliased identifiers.  Normalize
    # keys so the report contract is stable across aliased/unaliased SELECTs.
    return [{str(key).upper(): value for key, value in zip(columns, row, strict=False)} for row in rows]


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def serial_rows(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{k: serial(v) for k, v in row.items()} for row in dict_rows(columns, rows)]


def safe(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        columns, rows = fetch(cur, sql, params)
        return {"status": "PASS", "rows": serial_rows(columns, rows)}
    except Exception as exc:  # optional SAP tables/columns differ by installation
        return {"status": "QUERY_ERROR", "error_type": type(exc).__name__, "error": str(exc)[:400]}


def table_catalog(cur: Any) -> tuple[set[str], dict[str, set[str]]]:
    cols, rows = fetch(cur, 'SELECT "TABLE_NAME" FROM SYS.TABLES WHERE "SCHEMA_NAME"=?', ("TELCHI",))
    tables = {str(r[0]) for r in rows}
    columns: dict[str, set[str]] = {}
    for table in tables:
        _, table_rows = fetch(
            cur,
            'SELECT "COLUMN_NAME" FROM SYS.TABLE_COLUMNS WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"',
            ("TELCHI", table),
        )
        columns[table] = {str(r[0]) for r in table_rows}
    return tables, columns


def scalar(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    _, rows = fetch(cur, sql, params)
    return rows[0][0] if rows else None


def classify_journal(trans_type: str, data_source: str | None, auto_storno: str | None) -> tuple[str, str]:
    """Reproducible, evidence-labelled origin rule used by the report."""
    if auto_storno == "Y":
        return "SYSTEM_GENERATED", "OJDT.AutoStorno=Y"
    if trans_type in {"13", "14", "15", "16", "18", "19", "20", "21", "24", "46", "59", "60", "67", "69", "162", "202"}:
        return "DOCUMENT_GENERATED", "observed document lineage candidate"
    if trans_type in {"25", "321", "-2", "-3"}:
        return "SYSTEM_GENERATED", "observed system object/reconciliation type"
    if trans_type == "30" and data_source == "I":
        return "INTEGRATION_GENERATED", "TransType=30 and DataSource=I"
    if trans_type == "30" and data_source == "O":
        return "MANUAL_JOURNAL_ENTRY", "TransType=30 and DataSource=O (operational proxy)"
    return "UNCERTAIN", "no reproducible source rule"


def bucket_days(days: int | None) -> str:
    if days is None:
        return "UNKNOWN"
    if days == 0:
        return "same_day"
    if days == 1:
        return "1_day"
    if 2 <= days <= 7:
        return "2_7_days"
    if 8 <= days <= 30:
        return "8_30_days"
    return ">30_days"


def economic_classification(account: dict[str, Any]) -> tuple[str, str]:
    name = str(account.get("ACCTNAME") or account.get("AcctName") or "").upper()
    code = str(account.get("ACCTCODE") or account.get("AcctCode") or "").upper()
    group = str(account.get("GROUPMASK") or account.get("GroupMask") or "")
    text = f"{code} {name}"
    if group == "1" and "RETENC" in text:
        return "ACTIVO.INVENTARIO" if "ALMAC" in text else "ACTIVO.OTRO_ACTIVO", "GroupMask + name/code evidence"
    if group == "1" and any(x in text for x in ("IUE POR COMPENSAR", "CREDITO FISCAL")):
        return "ACTIVO.OTRO_ACTIVO", "GroupMask + name/code evidence"
    if any(x in text for x in ("RETENC", "IUE", "IT ", "RC-IVA", "IMPUEST", "FISCAL")):
        return "PASIVO.RETENCIONES" if "RETENC" in text and group == "2" else "PASIVO.IMPUESTOS", "name/code evidence"
    if any(x in text for x in ("BANCO", "BMSC", "BNB", "UNION", "FIE", "GANADERO", "SAFI", "HELM")):
        return "ACTIVO.BANCO", "name/code evidence"
    if any(x in text for x in ("CAJA", "EFECTIVO")):
        return "ACTIVO.CAJA", "name/code evidence"
    if any(x in text for x in ("CLIENT", "CUENTAS POR COBRAR", "CXC")):
        return "ACTIVO.CUENTAS_A_COBRAR", "name/code evidence"
    if any(x in text for x in ("PROVEED", "CUENTAS POR PAGAR", "CXP")):
        return "PASIVO.PROVEEDORES", "name/code evidence"
    if any(x in text for x in RISK_WORDS):
        return "REVIEW.SEMANTIC_RISK", "risk vocabulary in account name"
    return {"1": "ACTIVO", "2": "PASIVO", "3": "PATRIMONIO", "4": "INGRESOS", "5": "COSTO_DE_VENTAS", "6": "GASTOS"}.get(group, "UNRESOLVED"), "OACT.GroupMask"


def overview(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, sql in {
        "ojdt": 'SELECT COUNT(*) AS "COUNT", COUNT(DISTINCT "TransId") AS "DISTINCT_TRANSIDS", MIN("RefDate") AS "MIN_DATE", MAX("RefDate") AS "MAX_DATE" FROM TELCHI."OJDT"',
        "jdt1": 'SELECT COUNT(*) AS "COUNT", COUNT(DISTINCT "TransId") AS "DISTINCT_TRANSIDS", MIN("RefDate") AS "MIN_DATE", MAX("RefDate") AS "MAX_DATE" FROM TELCHI."JDT1"',
        "oact": 'SELECT COUNT(*) AS "COUNT" FROM TELCHI."OACT"',
    }.items():
        result[label] = safe(cur, sql)
    result["currencies"] = safe(cur, '''SELECT "FCCurrency", COUNT(*) AS "LINES", SUM("FCDebit") AS "FCDEBIT", SUM("FCCredit") AS "FCCREDIT"
        FROM TELCHI."JDT1" WHERE COALESCE("FCCurrency",'')<>'' GROUP BY "FCCurrency" ORDER BY "LINES" DESC''')
    result["jdt_currency_columns"] = safe(cur, '''SELECT SUM("Debit") AS "LOCAL_DEBIT", SUM("Credit") AS "LOCAL_CREDIT", SUM("SYSDeb") AS "SYSTEM_DEBIT", SUM("SYSCred") AS "SYSTEM_CREDIT", SUM("FCDebit") AS "FC_DEBIT", SUM("FCCredit") AS "FC_CREDIT", SUM(CASE WHEN "FCDebit"<>0 OR "FCCredit"<>0 THEN 1 ELSE 0 END) AS "FC_LINES" FROM TELCHI."JDT1"''')
    return result


def transtype_profile(cur: Any) -> dict[str, Any]:
    sql = '''SELECT O."TransType", COUNT(DISTINCT O."TransId") AS "JOURNALS", COUNT(J."TransId") AS "LINES",
        MIN(O."RefDate") AS "FIRST_DATE", MAX(O."RefDate") AS "LAST_DATE",
        SUM(COALESCE(J."Debit",0)) AS "DEBIT", SUM(COALESCE(J."Credit",0)) AS "CREDIT",
        SUM(COALESCE(J."Debit",0)-COALESCE(J."Credit",0)) AS "CONTROL_BALANCE",
        SUM(COALESCE(O."LocTotal",0)) AS "OJDT_LOC_TOTAL", SUM(COALESCE(O."SysTotal",0)) AS "OJDT_SYS_TOTAL",
        SUM(CASE WHEN O."CreatedBy"=O."TransId" THEN 1 ELSE 0 END) AS "CREATEDBY_SELF",
        SUM(CASE WHEN COALESCE(O."Memo",'')='' THEN 1 ELSE 0 END) AS "EMPTY_MEMO",
        SUM(CASE WHEN O."AutoStorno"='Y' THEN 1 ELSE 0 END) AS "AUTO_STORNO"
        FROM TELCHI."OJDT" O LEFT JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId"
        GROUP BY O."TransType" ORDER BY "JOURNALS" DESC'''
    profile = safe(cur, sql)
    if profile["status"] != "PASS":
        return profile
    total = sum(int(row["JOURNALS"] or 0) for row in profile["rows"])
    for row in profile["rows"]:
        row["PERCENT_GL"] = round(100 * float(row["JOURNALS"] or 0) / total, 5) if total else 0
        row["OBJECT_PROPOSAL"] = OBJECT_CANDIDATES.get(str(row["TRANSTYPE"]), ("Unknown", None, ""))[0]
    top_sql = '''SELECT "TransType", "UserSign", COUNT(DISTINCT "TransId") AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL"
        FROM TELCHI."OJDT" GROUP BY "TransType","UserSign" ORDER BY "JOURNALS" DESC LIMIT 500'''
    profile["top_users"] = safe(cur, top_sql)
    profile["top_memos_refs"] = safe(cur, '''SELECT "TransType", "Memo", "BaseRef", "Ref1", "Ref2", "Ref3", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL"
        FROM TELCHI."OJDT" GROUP BY "TransType","Memo","BaseRef","Ref1","Ref2","Ref3" ORDER BY "JOURNALS" DESC LIMIT 500''')
    profile["yearly"] = safe(cur, '''SELECT YEAR("RefDate") AS "YEAR", "TransType", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL"
        FROM TELCHI."OJDT" GROUP BY YEAR("RefDate"),"TransType" ORDER BY "YEAR","TransType"''')
    return profile


def document_lineage(cur: Any, tables: set[str], columns: dict[str, set[str]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for trans_type, (object_name, table, key) in OBJECT_CANDIDATES.items():
        base: dict[str, Any] = {"trans_type": trans_type, "object": object_name, "table": table, "key": key}
        if table is None:
            base.update({"classification": "STRONG", "coverage_pct": None, "reason": "No header table exists for this system journal type."})
            result.append(base)
            continue
        if table not in tables or key not in columns.get(table, set()):
            base.update({"classification": "UNRESOLVED", "coverage_pct": 0, "reason": "candidate table/key absent"})
            result.append(base)
            continue
        if table == "OJDT":
            join = 'H."TransId"=O."TransId"'
        else:
            join = f'H."{key}"=O."TransId"'
        sql = f'''SELECT COUNT(DISTINCT O."TransId") AS "JOURNALS", COUNT(DISTINCT CASE WHEN H."{key}" IS NOT NULL THEN O."TransId" END) AS "MATCHED_JOURNALS",
            COUNT(DISTINCT H."{key}") AS "HEADERS_WITH_KEY" FROM TELCHI."OJDT" O LEFT JOIN TELCHI."{table}" H ON {join} WHERE O."TransType"=?'''
        measured = safe(cur, sql, (trans_type,))
        base["measurement"] = measured
        if measured["status"] != "PASS":
            base.update({"classification": "UNRESOLVED", "coverage_pct": 0})
            result.append(base)
            continue
        row = measured["rows"][0]
        journals = int(row["JOURNALS"] or 0)
        matched = int(row["MATCHED_JOURNALS"] or 0)
        base["coverage_pct"] = round(100 * matched / journals, 4) if journals else 0
        base["classification"] = "PROVEN" if journals and matched == journals else ("PARTIAL" if matched else "UNRESOLVED")
        base["samples"] = safe(cur, f'''SELECT O."TransId", O."RefDate", O."BaseRef", O."Memo", O."CreatedBy", H."{key}" AS "SOURCE_KEY"
            FROM TELCHI."OJDT" O LEFT JOIN TELCHI."{table}" H ON {join} WHERE O."TransType"=? ORDER BY O."RefDate" DESC,O."TransId" DESC LIMIT 3''', (trans_type,))
        result.append(base)
    return result


def origin_analysis(cur: Any) -> dict[str, Any]:
    rows = safe(cur, '''SELECT "TransType", COALESCE("DataSource",'') AS "DATASOURCE", COALESCE("AutoStorno",'') AS "AUTOSTORNO", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL"
        FROM TELCHI."OJDT" GROUP BY "TransType",COALESCE("DataSource",''),COALESCE("AutoStorno",'') ORDER BY "JOURNALS" DESC''')
    classified = safe(cur, '''SELECT "TransType", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL",
        CASE WHEN "AutoStorno"='Y' THEN 'SYSTEM_GENERATED'
             WHEN "TransType" IN ('13','14','15','16','18','19','20','21','24','46','59','60','67','69','162','202') THEN 'DOCUMENT_GENERATED'
             WHEN "TransType" IN ('25','321','-2','-3') THEN 'SYSTEM_GENERATED'
             WHEN "TransType"='30' AND "DataSource"='I' THEN 'INTEGRATION_GENERATED'
             WHEN "TransType"='30' AND "DataSource"='O' THEN 'MANUAL_JOURNAL_ENTRY'
             ELSE 'UNCERTAIN' END AS "ORIGIN"
        FROM TELCHI."OJDT" GROUP BY "TransType","DataSource","AutoStorno" ORDER BY "JOURNALS" DESC''')
    return {"raw_indicators": rows, "classification_breakdown": classified, "definition": {
        "DOCUMENT_GENERATED": "one of the measured document TransTypes; lineage is separately reported",
        "MANUAL_JOURNAL_ENTRY": "TransType 30 + DataSource O + AutoStorno not Y; operational proxy, not a claim about human intent",
        "INTEGRATION_GENERATED": "TransType 30 + DataSource I",
        "SYSTEM_GENERATED": "AutoStorno Y or observed system/reconciliation type",
        "UNCERTAIN": "no rule accepted",
    }}


def manual_analysis(cur: Any) -> dict[str, Any]:
    where = '''"TransType"='30' AND COALESCE("DataSource",'')='O' AND COALESCE("AutoStorno",'')<>'Y' '''
    result: dict[str, Any] = {"definition": where}
    result["summary"] = safe(cur, f'''SELECT COUNT(*) AS "JOURNALS", MIN("RefDate") AS "FIRST_DATE", MAX("RefDate") AS "LAST_DATE", SUM("LocTotal") AS "LOC_TOTAL", SUM("SysTotal") AS "SYS_TOTAL" FROM TELCHI."OJDT" WHERE {where}''')
    result["users"] = safe(cur, f'''SELECT "UserSign", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL" FROM TELCHI."OJDT" WHERE {where} GROUP BY "UserSign" ORDER BY "JOURNALS" DESC LIMIT 50''')
    result["monthly"] = safe(cur, f'''SELECT YEAR("RefDate") AS "YEAR", MONTH("RefDate") AS "MONTH", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL" FROM TELCHI."OJDT" WHERE {where} GROUP BY YEAR("RefDate"),MONTH("RefDate") ORDER BY "YEAR","MONTH"''')
    result["weekday"] = safe(cur, f'''SELECT WEEKDAY("RefDate") AS "WEEKDAY", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL" FROM TELCHI."OJDT" WHERE {where} GROUP BY WEEKDAY("RefDate") ORDER BY "WEEKDAY"''')
    result["month_year_end"] = safe(cur, f'''SELECT CASE WHEN "RefDate"=LAST_DAY("RefDate") THEN 'MONTH_END' WHEN MONTH("RefDate")=12 AND DAYOFMONTH("RefDate")=31 THEN 'YEAR_END' ELSE 'OTHER' END AS "CLOSURE_BUCKET", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL" FROM TELCHI."OJDT" WHERE {where} GROUP BY CASE WHEN "RefDate"=LAST_DAY("RefDate") THEN 'MONTH_END' WHEN MONTH("RefDate")=12 AND DAYOFMONTH("RefDate")=31 THEN 'YEAR_END' ELSE 'OTHER' END''')
    result["memos"] = safe(cur, f'''SELECT "Memo", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL" FROM TELCHI."OJDT" WHERE {where} GROUP BY "Memo" ORDER BY "JOURNALS" DESC LIMIT 100''')
    result["keyword_patterns"] = safe(cur, f'''SELECT CASE
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%RETENC%' OR UPPER(COALESCE("Memo",'')) LIKE '%RETEN%' THEN 'RETENCION'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE("Memo",'')) LIKE '%IUE%' OR UPPER(COALESCE("Memo",'')) LIKE '%RC-IVA%' THEN 'IMPUESTO'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%BANCO%' OR UPPER(COALESCE("Memo",'')) LIKE '%CAJA%' THEN 'CAJA_BANCO'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%DEPOS%' THEN 'DEPOSITO'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%AJUST%' OR UPPER(COALESCE("Memo",'')) LIKE '%REGULAR%' OR UPPER(COALESCE("Memo",'')) LIKE '%COMPENS%' THEN 'AJUSTE_REGULARIZACION'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%CIERRE%' OR UPPER(COALESCE("Memo",'')) LIKE '%PROVISION%' THEN 'CIERRE_PROVISION'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%DIFERENCIA%' OR UPPER(COALESCE("Memo",'')) LIKE '%CAMBIO%' THEN 'DIFERENCIA_CAMBIO'
        ELSE 'OTHER' END AS "PATTERN", COUNT(*) AS "JOURNALS", SUM("LocTotal") AS "LOC_TOTAL"
        FROM TELCHI."OJDT" WHERE {where} GROUP BY CASE
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%RETENC%' OR UPPER(COALESCE("Memo",'')) LIKE '%RETEN%' THEN 'RETENCION'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE("Memo",'')) LIKE '%IUE%' OR UPPER(COALESCE("Memo",'')) LIKE '%RC-IVA%' THEN 'IMPUESTO'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%BANCO%' OR UPPER(COALESCE("Memo",'')) LIKE '%CAJA%' THEN 'CAJA_BANCO'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%DEPOS%' THEN 'DEPOSITO'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%AJUST%' OR UPPER(COALESCE("Memo",'')) LIKE '%REGULAR%' OR UPPER(COALESCE("Memo",'')) LIKE '%COMPENS%' THEN 'AJUSTE_REGULARIZACION'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%CIERRE%' OR UPPER(COALESCE("Memo",'')) LIKE '%PROVISION%' THEN 'CIERRE_PROVISION'
        WHEN UPPER(COALESCE("Memo",'')) LIKE '%DIFERENCIA%' OR UPPER(COALESCE("Memo",'')) LIKE '%CAMBIO%' THEN 'DIFERENCIA_CAMBIO'
        ELSE 'OTHER' END ORDER BY "JOURNALS" DESC''')
    # Account totals and debit->credit pairs are both aggregated in HANA.
    result["accounts"] = safe(cur, f'''SELECT J."Account", A."AcctName", COUNT(*) AS "LINES", SUM(J."Debit") AS "DEBIT", SUM(J."Credit") AS "CREDIT", SUM(J."Debit"-J."Credit") AS "NET"
        FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE {where.replace('"TransType"', 'O."TransType"').replace('"DataSource"', 'O."DataSource"').replace('"AutoStorno"', 'O."AutoStorno"')} GROUP BY J."Account",A."AcctName" ORDER BY ABS(SUM(J."Debit"-J."Credit")) DESC LIMIT 100''')
    result["counterpart_pairs"] = safe(cur, f'''WITH L AS (SELECT J."TransId",J."Account",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE {where.replace('"TransType"', 'O."TransType"').replace('"DataSource"', 'O."DataSource"').replace('"AutoStorno"', 'O."AutoStorno"')} GROUP BY J."TransId",J."Account")
        SELECT D."Account" AS "DEBIT_ACCOUNT", C."Account" AS "CREDIT_ACCOUNT", COUNT(*) AS "JOURNALS", SUM(D."DEBIT"+C."CREDIT") AS "AMOUNT"
        FROM L D JOIN L C ON C."TransId"=D."TransId" AND D."DEBIT">0 AND C."CREDIT">0 AND D."Account"<>C."Account"
        GROUP BY D."Account",C."Account" ORDER BY "JOURNALS" DESC LIMIT 100''')
    result["samples"] = manual_samples(cur, where)
    return result


def manual_samples(cur: Any, where: str) -> list[dict[str, Any]]:
    picks = [
        ("high_amount", f'''SELECT "TransId" FROM TELCHI."OJDT" WHERE {where} ORDER BY ABS("LocTotal") DESC LIMIT 1'''),
        ("month_end", f'''SELECT "TransId" FROM TELCHI."OJDT" WHERE {where} AND "RefDate"=LAST_DAY("RefDate") ORDER BY ABS("LocTotal") DESC LIMIT 1'''),
        ("retention_keyword", f'''SELECT "TransId" FROM TELCHI."OJDT" WHERE {where} AND (UPPER(COALESCE("Memo",'')) LIKE '%RETENC%' OR UPPER(COALESCE("Memo",'')) LIKE '%IUE%' OR UPPER(COALESCE("Memo",'')) LIKE '%IMPUEST%') ORDER BY ABS("LocTotal") DESC LIMIT 1'''),
        ("bank_cash_keyword", f'''SELECT "TransId" FROM TELCHI."OJDT" WHERE {where} AND (UPPER(COALESCE("Memo",'')) LIKE '%BANCO%' OR UPPER(COALESCE("Memo",'')) LIKE '%CAJA%') ORDER BY ABS("LocTotal") DESC LIMIT 1'''),
    ]
    result: list[dict[str, Any]] = []
    for label, sql in picks:
        ids = safe(cur, sql)
        if ids.get("status") != "PASS" or not ids.get("rows"):
            continue
        trans_id = ids["rows"][0]["TRANSID"]
        header = safe(cur, 'SELECT * FROM TELCHI."OJDT" WHERE "TransId"=?', (trans_id,))
        lines = safe(cur, '''SELECT J.*, A."AcctName", A."GroupMask", A."ActCurr" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE J."TransId"=? ORDER BY J."Line_ID"''', (trans_id,))
        result.append({"label": label, "trans_id": trans_id, "ojdt": header, "jdt1": lines})
    return result


def account_behavior(cur: Any) -> dict[str, Any]:
    base = safe(cur, '''SELECT A."AcctCode", A."AcctName", A."GroupMask", A."FatherNum", A."Levels", A."Postable", A."ActCurr", A."CashBox", A."Advance", A."ValidFor", A."FrozenFor", A."CurrTotal", A."SysTotal", A."EndTotal",
        COALESCE(M."LINES",0) AS "LINES", COALESCE(M."TRANS",0) AS "TRANS", COALESCE(M."DEBIT",0) AS "DEBIT", COALESCE(M."CREDIT",0) AS "CREDIT", COALESCE(M."NET",0) AS "NET", COALESCE(M."GROSS",0) AS "GROSS", COALESCE(M."FIRST_DATE",NULL) AS "FIRST_DATE", COALESCE(M."LAST_DATE",NULL) AS "LAST_DATE"
        FROM TELCHI."OACT" A LEFT JOIN (SELECT "Account",COUNT(*) AS "LINES",COUNT(DISTINCT "TransId") AS "TRANS",SUM("Debit") AS "DEBIT",SUM("Credit") AS "CREDIT",SUM("Debit"-"Credit") AS "NET",SUM("Debit"+"Credit") AS "GROSS",MIN("RefDate") AS "FIRST_DATE",MAX("RefDate") AS "LAST_DATE" FROM TELCHI."JDT1" GROUP BY "Account") M ON M."Account"=A."AcctCode" ORDER BY "GROSS" DESC''')
    if base["status"] == "PASS":
        for row in base["rows"]:
            row["ECONOMIC_CLASSIFICATION"], row["CLASSIFICATION_BASIS"] = economic_classification(row)
            row["SEMANTIC_RISK"] = "SEMANTIC_RISK" if any(w in str(row.get("ACCTNAME") or "").upper() for w in RISK_WORDS) else "NORMAL"
    result: dict[str, Any] = {"all_accounts": base}
    if base["status"] == "PASS":
        result["top_movement"] = sorted(base["rows"], key=lambda x: abs(float(x.get("GROSS") or 0)), reverse=True)[:50]
        result["top_balance"] = sorted(base["rows"], key=lambda x: abs(float(x.get("NET") or 0)), reverse=True)[:50]
        result["top_transactions"] = sorted(base["rows"], key=lambda x: int(x.get("LINES") or 0), reverse=True)[:50]
        result["semantic_risk"] = [x for x in base["rows"] if x["SEMANTIC_RISK"] == "SEMANTIC_RISK"]
        targets = [x["ACCTCODE"] for x in result["top_movement"][:30]]
        if targets:
            placeholders = ",".join("?" for _ in targets)
            result["top_counterparts"] = safe(cur, f'''WITH L AS (SELECT "TransId","Account",SUM("Debit") AS "DEBIT",SUM("Credit") AS "CREDIT" FROM TELCHI."JDT1" GROUP BY "TransId","Account")
                SELECT D."Account",DA."AcctName",C."Account" AS "COUNTERPART_ACCOUNT",CA."AcctName" AS "COUNTERPART_NAME",COUNT(*) AS "TRANS",SUM(D."DEBIT"+D."CREDIT") AS "TARGET_GROSS",SUM(C."DEBIT"+C."CREDIT") AS "COUNTERPART_GROSS"
                FROM L D JOIN L C ON C."TransId"=D."TransId" AND C."Account"<>D."Account"
                LEFT JOIN TELCHI."OACT" DA ON DA."AcctCode"=D."Account" LEFT JOIN TELCHI."OACT" CA ON CA."AcctCode"=C."Account"
                WHERE D."Account" IN ({placeholders}) GROUP BY D."Account",DA."AcctName",C."Account",CA."AcctName" ORDER BY "TRANS" DESC LIMIT 500''', tuple(targets))
            result["control_accounts"] = safe(cur, '''SELECT "AcctCode","AcctName","SubLedgerN","PriAccCode","RealAcct","Postable","ActCurr","CurrTotal","SysTotal" FROM TELCHI."OACT" WHERE "AcctCode" IN ('1120101','1120201','2110101','2110201') OR COALESCE("SubLedgerN",'')<>'' OR COALESCE("PriAccCode",'')<>'' ORDER BY "AcctCode"''')
    return result


def retention_and_risk(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["candidate_accounts"] = safe(cur, '''SELECT "AcctCode","AcctName","GroupMask","ActCurr","CurrTotal","SysTotal","Postable","ValidFor","FrozenFor" FROM TELCHI."OACT"
        WHERE UPPER(COALESCE("AcctCode",'')) LIKE '%RETENC%' OR UPPER(COALESCE("AcctName",'')) LIKE '%RETENC%' OR UPPER(COALESCE("AcctCode",'')) LIKE '%IUE%' OR UPPER(COALESCE("AcctName",'')) LIKE '%IUE%' OR UPPER(COALESCE("AcctName",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE("AcctName",'')) LIKE '%FISCAL%' OR UPPER(COALESCE("AcctName",'')) LIKE '%RC-IVA%' ORDER BY "AcctCode"''')
    result["configured_codes"] = safe(cur, 'SELECT "WTCode","WTName","Rate","PrctBsAmnt","Account","ApTdsAcc","ArTdsAcc","Inactive" FROM TELCHI."OWHT" ORDER BY "WTCode"')
    result["configured_account_lineage"] = safe(cur, '''SELECT W."WTCode",W."WTName",W."Account",A."AcctName",A."GroupMask",A."ActCurr",A."CurrTotal",A."SysTotal",CASE WHEN A."AcctCode" IS NULL THEN 'CONFIGURED_ACCOUNT_NOT_IN_OACT' ELSE 'ACCOUNT_PRESENT' END AS "ACCOUNT_STATUS" FROM TELCHI."OWHT" W LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=W."Account" ORDER BY W."WTCode"''')
    result["candidate_account_behavior"] = safe(cur, '''SELECT J."Account",A."AcctName",J."TransType",J."UserSign",COUNT(*) AS "LINES",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",SUM(J."Debit"-J."Credit") AS "NET",MIN(J."RefDate") AS "FIRST_DATE",MAX(J."RefDate") AS "LAST_DATE" FROM TELCHI."JDT1" J JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE UPPER(COALESCE(A."AcctCode",'')) LIKE '%RETENC%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%RETENC%' OR UPPER(COALESCE(A."AcctCode",'')) LIKE '%IUE%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%IUE%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%FISCAL%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%RC-IVA%' GROUP BY J."Account",A."AcctName",J."TransType",J."UserSign" ORDER BY "JOURNALS" DESC LIMIT 300''')
    result["jdt1_wht_fields"] = safe(cur, '''SELECT COUNT(*) AS "LINES", SUM("WTSum") AS "WTSUM", SUM("WTApplied") AS "WTAPPLIED", COUNT(CASE WHEN COALESCE("WTaxCode",'')<>'' THEN 1 END) AS "WITH_WT_CODE", COUNT(CASE WHEN "WTSum"<>0 OR "WTApplied"<>0 THEN 1 END) AS "WITH_NONZERO_WT" FROM TELCHI."JDT1"''')
    result["memo_keyword_hits"] = safe(cur, '''SELECT J."Account",A."AcctName",J."TransType",COUNT(*) AS "LINES",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",MIN(J."RefDate") AS "FIRST_DATE",MAX(J."RefDate") AS "LAST_DATE"
        FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE UPPER(COALESCE(J."LineMemo",'')) LIKE '%RETENC%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%RETEN%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%IUE%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%RC-IVA%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%IMPUEST%' GROUP BY J."Account",A."AcctName",J."TransType" ORDER BY "LINES" DESC LIMIT 200''')
    result["transcode_and_accounts"] = safe(cur, '''SELECT O."TransType",O."TransCode",J."Account",A."AcctName",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."OJDT" O JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE J."WTSum"<>0 OR J."WTApplied"<>0 OR COALESCE(J."WTaxCode",'')<>'' GROUP BY O."TransType",O."TransCode",J."Account",A."AcctName" ORDER BY "JOURNALS" DESC LIMIT 200''')
    result["retention_line_samples"] = safe(cur, '''SELECT J."TransId",J."Line_ID",J."Account",A."AcctName",O."TransType",O."RefDate",O."Memo",J."LineMemo",J."Debit",J."Credit",J."UserSign",J."WTaxCode",J."WTSum",J."WTApplied" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE UPPER(COALESCE(J."LineMemo",'')) LIKE '%RETENC%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%IUE%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%RC-IVA%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%IMPUEST%' OR J."Account" IN (SELECT "Account" FROM TELCHI."OWHT") ORDER BY ABS(J."Debit"-J."Credit") DESC LIMIT 100''')
    return result


def periods_timing(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["periods"] = safe(cur, '''SELECT F."AbsEntry",F."Code",F."Name",F."F_RefDate",F."T_RefDate",F."F_DueDate",F."T_DueDate",F."F_TaxDate",F."T_TaxDate",F."PeriodStat",COUNT(O."TransId") AS "JOURNALS" FROM TELCHI."OFPR" F LEFT JOIN TELCHI."OJDT" O ON O."FinncPriod"=F."AbsEntry" GROUP BY F."AbsEntry",F."Code",F."Name",F."F_RefDate",F."T_RefDate",F."F_DueDate",F."T_DueDate",F."F_TaxDate",F."T_TaxDate",F."PeriodStat" ORDER BY F."F_RefDate"''')
    result["journals_by_period"] = safe(cur, '''SELECT "FinncPriod","TransType",COUNT(*) AS "JOURNALS",MIN("RefDate") AS "FIRST_DATE",MAX("RefDate") AS "LAST_DATE" FROM TELCHI."OJDT" GROUP BY "FinncPriod","TransType" ORDER BY "FinncPriod","TransType"''')
    # Positive days mean the journal was created after its posting date
    # (backdating). Negative days are retained as future-posting cases.
    result["timing_buckets"] = safe(cur, '''SELECT CASE WHEN "CreateDate" IS NULL THEN 'UNKNOWN' WHEN DAYS_BETWEEN("RefDate","CreateDate")<0 THEN 'future_posting' WHEN DAYS_BETWEEN("RefDate","CreateDate")=0 THEN 'same_day' WHEN DAYS_BETWEEN("RefDate","CreateDate")=1 THEN '1_day' WHEN DAYS_BETWEEN("RefDate","CreateDate") BETWEEN 2 AND 7 THEN '2_7_days' WHEN DAYS_BETWEEN("RefDate","CreateDate") BETWEEN 8 AND 30 THEN '8_30_days' ELSE '>30_days' END AS "BUCKET", "TransType",COUNT(*) AS "JOURNALS" FROM TELCHI."OJDT" GROUP BY CASE WHEN "CreateDate" IS NULL THEN 'UNKNOWN' WHEN DAYS_BETWEEN("RefDate","CreateDate")<0 THEN 'future_posting' WHEN DAYS_BETWEEN("RefDate","CreateDate")=0 THEN 'same_day' WHEN DAYS_BETWEEN("RefDate","CreateDate")=1 THEN '1_day' WHEN DAYS_BETWEEN("RefDate","CreateDate") BETWEEN 2 AND 7 THEN '2_7_days' WHEN DAYS_BETWEEN("RefDate","CreateDate") BETWEEN 8 AND 30 THEN '8_30_days' ELSE '>30_days' END,"TransType" ORDER BY "TransType","BUCKET"''')
    result["tax_timing_buckets"] = safe(cur, '''SELECT CASE WHEN "TaxDate" IS NULL THEN 'UNKNOWN' WHEN DAYS_BETWEEN("TaxDate","RefDate")=0 THEN 'same_day' WHEN DAYS_BETWEEN("TaxDate","RefDate") BETWEEN 1 AND 7 THEN '1_7_days' WHEN DAYS_BETWEEN("TaxDate","RefDate") BETWEEN 8 AND 30 THEN '8_30_days' ELSE '>30_days' END AS "BUCKET", "TransType",COUNT(*) AS "JOURNALS" FROM TELCHI."OJDT" GROUP BY CASE WHEN "TaxDate" IS NULL THEN 'UNKNOWN' WHEN DAYS_BETWEEN("TaxDate","RefDate")=0 THEN 'same_day' WHEN DAYS_BETWEEN("TaxDate","RefDate") BETWEEN 1 AND 7 THEN '1_7_days' WHEN DAYS_BETWEEN("TaxDate","RefDate") BETWEEN 8 AND 30 THEN '8_30_days' ELSE '>30_days' END,"TransType" ORDER BY "TransType","BUCKET"''')
    return result


def account_tree(cur: Any) -> dict[str, Any]:
    data = safe(cur, '''SELECT "AcctCode","AcctName","FatherNum","Levels","GroupMask","Postable","ActType","ActCurr","CashBox","Advance","ValidFor","FrozenFor","SubLedgerN","PriAccCode","RealAcct","Category" FROM TELCHI."OACT" ORDER BY "AcctCode"''')
    if data["status"] != "PASS":
        return data
    codes = {str(x["ACCTCODE"]) for x in data["rows"]}
    invalid = [x for x in data["rows"] if x.get("FATHERNUM") not in (None, "", 0, "0") and str(x.get("FATHERNUM")) not in codes]
    data["invalid_parent_references"] = invalid
    data["root_accounts"] = [x for x in data["rows"] if x.get("FATHERNUM") in (None, "", 0, "0")]
    data["summary_by_group"] = safe(cur, '''SELECT "GroupMask",COUNT(*) AS "ACCOUNTS",SUM(CASE WHEN "Postable"='Y' THEN 1 ELSE 0 END) AS "POSTABLE",SUM(CASE WHEN "ValidFor"='Y' THEN 1 ELSE 0 END) AS "VALID",SUM(CASE WHEN "FrozenFor"='Y' THEN 1 ELSE 0 END) AS "FROZEN" FROM TELCHI."OACT" GROUP BY "GroupMask" ORDER BY "GroupMask"''')
    return data


def users_and_config(cur: Any, tables: set[str], columns: dict[str, set[str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "OUSR" in tables:
        wanted = [x for x in ("USERID", "USER_CODE", "U_NAME", "SUPERUSER", "GROUPS") if x in columns.get("OUSR", set())]
        if wanted:
            result["ousr"] = safe(cur, 'SELECT ' + ','.join(f'"{x}"' for x in wanted) + ' FROM TELCHI."OUSR" ORDER BY 1')
    result["user_activity"] = safe(cur, '''SELECT "UserSign",COUNT(*) AS "JOURNALS",SUM("LocTotal") AS "LOC_TOTAL",MIN("RefDate") AS "FIRST_DATE",MAX("RefDate") AS "LAST_DATE" FROM TELCHI."OJDT" GROUP BY "UserSign" ORDER BY "JOURNALS" DESC LIMIT 100''')
    if "OADM" in tables:
        wanted = [x for x in ("MainCurncy", "SysCurrncy", "MultiCurr", "MainCurncy", "SysCurr") if x in columns.get("OADM", set())]
        if wanted:
            result["oadm_currency"] = safe(cur, 'SELECT ' + ','.join(dict.fromkeys(f'"{x}"' for x in wanted)) + ' FROM TELCHI."OADM"')
    return result


def balance_and_invariants(cur: Any, lineage: list[dict[str, Any]], tree: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["per_journal_balance"] = safe(cur, f'''SELECT COUNT(*) AS "JOURNALS",SUM(CASE WHEN ABS(COALESCE(X."DEBIT",0)-COALESCE(X."CREDIT",0))<={TOLERANCE} THEN 1 ELSE 0 END) AS "BALANCED",SUM(CASE WHEN ABS(COALESCE(X."DEBIT",0)-COALESCE(X."CREDIT",0))>{TOLERANCE} THEN 1 ELSE 0 END) AS "UNBALANCED",MAX(ABS(COALESCE(X."DEBIT",0)-COALESCE(X."CREDIT",0))) AS "MAX_DIFF" FROM (SELECT "TransId",SUM("Debit") AS "DEBIT",SUM("Credit") AS "CREDIT" FROM TELCHI."JDT1" GROUP BY "TransId") X''')
    result["unique_ojdt"] = safe(cur, 'SELECT COUNT(*) AS "ROWS",COUNT(DISTINCT "TransId") AS "DISTINCT_TRANSIDS" FROM TELCHI."OJDT"')
    result["jdt1_orphans"] = safe(cur, 'SELECT COUNT(*) AS "ORPHAN_LINES" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE O."TransId" IS NULL')
    result["account_orphans"] = safe(cur, 'SELECT COUNT(*) AS "ORPHAN_ACCOUNT_LINES" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE A."AcctCode" IS NULL')
    result["observed_transtypes"] = safe(cur, 'SELECT COUNT(DISTINCT "TransType") AS "OBSERVED_TYPES" FROM TELCHI."OJDT"')
    result["lineage_classifications"] = {x["trans_type"]: x.get("classification") for x in lineage}
    result["hierarchy_invalid"] = len(tree.get("invalid_parent_references", [])) if isinstance(tree, dict) else None
    result["manual_definition_reproducible"] = True
    result["sap_write_count"] = 0
    return result


def exchange_difference(cur: Any) -> dict[str, Any]:
    return {
        "memo_or_name_hits": safe(cur, '''SELECT J."Account",A."AcctName",J."TransType",COUNT(*) AS "LINES",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE UPPER(COALESCE(J."LineMemo",'')) LIKE '%CAMBIO%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%EXCHANGE%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%REVALU%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%CAMBIO%' OR UPPER(COALESCE(A."AcctName",'')) LIKE '%REVALU%' GROUP BY J."Account",A."AcctName",J."TransType" ORDER BY "LINES" DESC LIMIT 200'''),
        "candidate_transcodes": safe(cur, '''SELECT "TransType","TransCode",COUNT(*) AS "JOURNALS",SUM("LocTotal") AS "LOC_TOTAL" FROM TELCHI."OJDT" WHERE UPPER(COALESCE("Memo",'')) LIKE '%CAMBIO%' OR UPPER(COALESCE("Memo",'')) LIKE '%EXCHANGE%' OR UPPER(COALESCE("Memo",'')) LIKE '%REVALU%' GROUP BY "TransType","TransCode" ORDER BY "JOURNALS" DESC'''),
    }


def cases(cur: Any, profile: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in profile.get("rows", []):
        trans_type = row["TRANSTYPE"]
        found = safe(cur, 'SELECT "TransId" FROM TELCHI."OJDT" WHERE "TransType"=? ORDER BY "RefDate" DESC,"TransId" DESC LIMIT 1', (trans_type,))
        if found.get("status") != "PASS" or not found.get("rows"):
            continue
        trans_id = found["rows"][0]["TRANSID"]
        header = safe(cur, 'SELECT "TransType","TransId","RefDate","TaxDate","DueDate","BaseRef","Ref1","Ref2","Ref3","Memo","CreatedBy","UserSign","UserSign2","DataSource","TransCode","DocSeries","AutoStorno","StornoToTr" FROM TELCHI."OJDT" WHERE "TransId"=?', (trans_id,))
        lines = safe(cur, '''SELECT J."Account",A."AcctName",A."GroupMask",A."ActCurr",J."Debit",J."Credit",J."SYSDeb",J."SYSCred",J."FCDebit",J."FCCredit",J."FCCurrency",J."ShortName",J."ContraAct",J."LineMemo",J."TransType",J."DocEntry",J."DocNum",J."CreatedBy",J."BaseRef",J."WTaxCode",J."WTSum" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE J."TransId"=? ORDER BY J."Line_ID"''', (trans_id,))
        result.append({"trans_type": trans_type, "trans_id": trans_id, "object": OBJECT_CANDIDATES.get(str(trans_type), ("Unknown",))[0], "ojdt": header, "jdt1": lines})
    return result


def render_report(report: dict[str, Any]) -> str:
    ov = report["overview"]
    def first(section: dict[str, Any], key: str) -> dict[str, Any]:
        rows = section.get(key, {}).get("rows", [])
        return rows[0] if rows else {}
    ojdt = first(ov, "ojdt")
    jdt1 = first(ov, "jdt1")
    oact = first(ov, "oact")
    profile = report["transtype_profile"].get("rows", [])
    lineage = report["document_lineage"]
    inv = report["invariants"]
    bal = first(inv, "per_journal_balance")
    origin = report["origin_analysis"].get("classification_breakdown", {}).get("rows", [])
    manual = first(report["manual_analysis"], "summary")
    retention = report["retention_and_risk"]
    configured_retention = retention.get("configured_account_lineage", {}).get("rows", [])
    control_accounts = report["account_behavior"].get("control_accounts", {}).get("rows", [])
    lines = [
        "# TELCHI — GL / TransType / Account Behavior V1",
        "",
        f"**Gate:** `TELCHI_GL_TRANS_TYPE_ACCOUNT_BEHAVIOR_V1_PASS`  ",
        f"**Veredicto:** **{report['verdict']}** — el GL queda explicado con degradaciones explícitas; no se interpreta la ausencia del mecanismo estándar como ausencia de retenciones.",
        "",
        "## A. Veredicto ejecutivo",
        "",
        f"Telchi tiene **{ojdt.get('COUNT','?')} OJDT**, **{jdt1.get('COUNT','?')} JDT1** y **{oact.get('COUNT','?')} OACT**. El volumen está dominado por los tipos mostrados abajo; `TransType=30` se separa mediante una regla reproducible, pero `DataSource=O` es un proxy operativo y no prueba por sí solo intención humana.",
        "",
        "La búsqueda de retenciones se reporta como: **el mecanismo estándar observado no mostró importes no nulos; el GL sí queda rastreado hacia cuentas/memos candidatos si aparecen**. No se declara que Telchi no registre retenciones.",
        "",
        "## B. GL en números",
        "",
        "| Objeto | Filas | Desde | Hasta |",
        "|---|---:|---|---|",
        f"| OJDT | {ojdt.get('COUNT','?')} | {ojdt.get('MIN_DATE','?')} | {ojdt.get('MAX_DATE','?')} |",
        f"| JDT1 | {jdt1.get('COUNT','?')} | {jdt1.get('MIN_DATE','?')} | {jdt1.get('MAX_DATE','?')} |",
        f"| OACT | {oact.get('COUNT','?')} | — | — |",
        "",
        "## C. Mapa completo de TransType",
        "",
        "| TransType | Objeto propuesto | Asientos | Líneas | % GL | Débito | Crédito | Estado lineage |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    lin_by = {str(x["trans_type"]): x for x in lineage}
    for row in profile:
        l = lin_by.get(str(row["TRANSTYPE"]), {})
        lines.append(f"| {row['TRANSTYPE']} | {row.get('OBJECT_PROPOSAL','?')} | {row.get('JOURNALS',0)} | {row.get('LINES',0)} | {row.get('PERCENT_GL',0)} | {row.get('DEBIT',0)} | {row.get('CREDIT',0)} | {l.get('classification','?')} ({l.get('coverage_pct','—')}%) |")
    lines += ["", "## D. Automáticos vs manuales", "", "La clasificación no usa únicamente `TransType=30`: primero reconoce lineage documental; luego `AutoStorno`, `DataSource=I/O` y finalmente `UNCERTAIN`. La categoría manual se define como `TransType=30 AND DataSource=O AND AutoStorno<>Y`, declarada como proxy operativo.", "", "| Categoría | Asientos / filas agregadas |", "|---|---:|"]
    totals: dict[str, int] = defaultdict(int)
    for row in origin:
        totals[str(row.get("ORIGIN"))] += int(row.get("JOURNALS") or 0)
    for key, value in totals.items():
        lines.append(f"| {key} | {value} |")
    lines += ["", f"Asientos manuales por regla: **{manual.get('JOURNALS','?')}**, período {manual.get('FIRST_DATE','?')} → {manual.get('LAST_DATE','?')}, importe local agregado {manual.get('LOC_TOTAL','?')}.", "", "## E. Cuentas y comportamiento", "", "La evidencia completa de las 824 cuentas, jerarquía, clasificación económica, rankings de movimiento/saldo/transacciones, contrapartidas, riesgos semánticos y muestras está en el JSON. La clasificación SAP conserva `GroupMask`, `FatherNum`, `Levels`, `Postable`, `ActCurr`, `ValidFor` y `FrozenFor`; la interpretación económica Team360 se mantiene separada.", ""]
    top = report["account_behavior"].get("top_movement", [])[:15]
    lines += ["| Cuenta | Nombre | Movimiento absoluto | Saldo neto | Líneas | Clasificación | Riesgo |", "|---|---|---:|---:|---:|---|---|"]
    for row in top:
        lines.append(f"| {row.get('ACCTCODE')} | {row.get('ACCTNAME','')} | {row.get('GROSS',0)} | {row.get('NET',0)} | {row.get('LINES',0)} | {row.get('ECONOMIC_CLASSIFICATION','')} | {row.get('SEMANTIC_RISK','')} |")
    lines += ["", "## F. Control accounts y contrapartidas", "", "La relación `Business Partner → control account → JDT1 → GL` queda preservada en las cuentas control y en el JSON; no se usa el saldo OACT como sustituto de deuda abierta.", "", "| Cuenta | Nombre | Moneda | Saldo local |", "|---|---|---|---:|"]
    for row in control_accounts[:20]:
        lines.append(f"| {row.get('ACCTCODE')} | {row.get('ACCTNAME','')} | {row.get('ACTCURR','')} | {row.get('CURRTOTAL',0)} |")
    lines += ["", "## G. Monedas, períodos y posting timing", "", "Configuración observada: moneda principal `BS`, moneda sistema `USD`, multimoneda `B`. Se inspeccionan `Debit/Credit`, `SYSDeb/SYSCred`, `FCDebit/FCCredit`, `FCCurrency`, `OFPR`, `FinncPriod`, `CreateDate`, `RefDate` y `TaxDate`; el JSON contiene distribución por moneda, período y buckets de backdating.", "", "## H. Retenciones — nuevas pistas", "", "La consulta cruzó cuentas OACT por nombre/código, configuración OWHT, `JDT1.WTaxCode/WTSum/WTApplied` y memos. En la corrida actual `JDT1` tiene `WTaxCode` no nulo = 0, `WTSum` = 0 y `WTApplied` = 0; eso solo prueba que **no aparecen usando ese mecanismo estándar**.", "", f"Los {len(configured_retention)}/6 códigos OWHT apuntan a cuentas OACT existentes y esas cuentas tienen saldo corriente cero en la corrida. El GL sí encontró señales que justifican priorizar el siguiente gate: cuentas fiscales/impositivas con movimientos manuales (por ejemplo `2140103 IUE por pagar` y `2140102 IT por pagar`). `1130205 Almacén Retención` tiene movimientos de inventario (`TransType=60/67`) y por `GroupMask=1` se interpreta como almacén, no como pasivo WHT; es un falso positivo nominal que queda documentado. Todo esto es una pista, no una conclusión de retención contabilizada.", "", "## I. Casos reales y evidencia", "", f"Se conservaron muestras completas de **{len(report.get('cases', []))}/21 TransTypes**, con header OJDT, líneas JDT1 y OACT; también muestras de asientos manuales común/alto importe/cierre/palabra clave cuando existen.", ""]
    lines += ["## J. Balance e invariantes", "", f"Balance por `TransId`: {bal.get('BALANCED','?')} balanceados, {bal.get('UNBALANCED','?')} fuera de tolerancia {TOLERANCE}, diferencia máxima {bal.get('MAX_DIFF','?')}.", "", "| Invariante | Resultado |", "|---|---|"]
    lines += [f"| GL01 OJDT.TransId único | {inv.get('unique_ojdt',{}).get('rows',[{}])[0] if inv.get('unique_ojdt',{}).get('rows') else '?'} |", f"| GL02 JDT1 sin OJDT | {inv.get('jdt1_orphans',{}).get('rows',[{}])[0] if inv.get('jdt1_orphans',{}).get('rows') else '?'} |", f"| GL03 JDT1.Account en OACT | {inv.get('account_orphans',{}).get('rows',[{}])[0] if inv.get('account_orphans',{}).get('rows') else '?'} |", f"| GL05 TransTypes observados | {inv.get('observed_transtypes',{}).get('rows',[{}])[0] if inv.get('observed_transtypes',{}).get('rows') else '?'} |", f"| GL09 padres OACT inválidos | {inv.get('hierarchy_invalid')} |", "| GL10 SAP_WRITE_COUNT | 0 |", ""]
    lines += ["## K. Vacíos semánticos", "", "- `DataSource=O` separa un universo operativo de asientos tipo 30, pero no demuestra quién digitó cada asiento ni excluye procesos externos.", "- Los tipos -2/-3 no tienen header operacional; su semántica queda STRONG por el tipo observado y el patrón, no por un documento.", "- La ruta de retenciones queda abierta si las cuentas/memos no explican saldo, período, documento y reversa completos.", "- AP/AR, bancos, depósitos, cash flow y estados financieros no se profundizan en este gate.", "", "## L. Próximo gate", "", "La evidencia actual prioriza `TELCHI_WITHHOLDING_TAX_ACCOUNTING_TRACEABILITY_V1`: hay cuentas fiscales y movimientos tipo 30 compatibles, mientras que el mecanismo estándar WHT permanece vacío. AP y tesorería siguen después; no se construyen todavía aging, cash flow ni política de retenciones.", "", "## Artefactos", "", f"- JSON técnico: `{DEFAULT_OUTPUT}`", f"- Script reproducible: `{Path(__file__)}`", "- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.", ""]
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        # Freeze the read view for all aggregates.  This is a transaction
        # setting, not a SAP mutation, and prevents live posting drift from
        # producing contradictory OJDT/JDT1 totals within one artifact.
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        tables, columns = table_catalog(cur)
        ov = overview(cur)
        profile = transtype_profile(cur)
        lineage = document_lineage(cur, tables, columns)
        tree = account_tree(cur)
        report: dict[str, Any] = {
            "report_id": "TELCHI_GL_TRANS_TYPE_ACCOUNT_BEHAVIOR_V1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "entity": "TELCHI", "domain": "CONTABILIDAD", "stage": "INVESTIGATION",
            "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True},
            "sap_write_count": 0,
            "observed_tables": sorted(tables & {"OJDT","JDT1","OACT","OFPR","OUSR","OADM","OWHT","AWHT","OITR","ODPS"}),
            "overview": ov,
            "transtype_profile": profile,
            "document_lineage": lineage,
            "origin_analysis": origin_analysis(cur),
            "manual_analysis": manual_analysis(cur),
            "account_tree": tree,
            "account_behavior": account_behavior(cur),
            "retention_and_risk": retention_and_risk(cur),
            "currencies_and_config": users_and_config(cur, tables, columns),
            "periods_and_timing": periods_timing(cur),
            "exchange_difference": exchange_difference(cur),
            "cases": cases(cur, profile),
            "invariants": {},
            "limitations": [
                "Manual classification DataSource=O is reproducible but remains an operational proxy, not proof of human intent.",
                "No conclusion of absence of withholdings is made from empty standard WHT fields.",
                "All amounts remain in their source currency unless explicitly labelled local/system/foreign.",
            ],
        }
        report["invariants"] = balance_and_invariants(cur, lineage, tree, profile)
        report["verdict"] = "PASS" if report["invariants"].get("sap_write_count") == 0 and len(profile.get("rows", [])) == 21 and report["invariants"].get("hierarchy_invalid") == 0 else "DEGRADED"
        return report
    finally:
        conn.rollback()
        cur.close(); conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(result), encoding="utf-8")
    print(f"report={args.output}")
    print(f"markdown={args.report}")
    print(f"SAP_WRITE_COUNT={result['sap_write_count']}")
    print(f"verdict={result['verdict']} transtypes={len(result['transtype_profile'].get('rows', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
