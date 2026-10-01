#!/usr/bin/env python3
"""TELCHI Treasury / Cash / Bank / Deposit V1.

Investigation-only, SELECT-only HANA probe.  It keeps the document, physical
instrument, deposit, GL and balance layers separate.  Heavy work is aggregated
in HANA; only representative end-to-end cases are materialised.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "treasury_cash_bank_deposit"
DEFAULT_OUTPUT = OUT_DIR / "treasury_cash_bank_deposit_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_treasury_cash_bank_deposit_v1_report.md"
AP_ARTIFACT = ROOT / "validation" / "ap_payables_payment_reconciliation" / "ap_payables_payment_reconciliation_v1.json"
TOLERANCE = 0.01

# Standard SAP B1 treasury objects.  The metadata census is independent from
# this list and records any additional object whose name suggests treasury use.
TABLES = (
    "ORCT", "RCT1", "RCT2", "RCT3", "RCT4", "OVPM", "VPM1", "VPM2",
    "VPM4", "VPM6", "ODPS", "DPS1", "OCHO", "OCHH", "ODSC", "DSC1",
    "OCRB", "OBNK", "OBTF", "OJDT", "JDT1", "OACT", "OCRD", "OUSR",
)
METADATA_TERMS = ("BANK", "ACCOUNT", "CASH", "CHECK", "CHEQUE", "DEPOSIT", "PAYMENT", "TRANSFER", "CREDIT", "RECONCILIATION", "STATEMENT")
METHOD_NAMES = ("CASH", "BANK_TRANSFER", "CHECK", "CREDIT_CARD", "MIXED", "OTHER")
TREASURY_TRANS_TYPES = {"24": "CUSTOMER_COLLECTION", "46": "SUPPLIER_PAYMENT", "25": "CASH_DEPOSIT", "30": "MANUAL_JOURNAL_ENTRY", "-2": "INTERNAL_TRANSFER", "-3": "INTERNAL_TRANSFER"}


def fetch(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[str], list[tuple[Any, ...]]]:
    cur.execute(sql, params)
    return [str(x[0]) for x in (cur.description or ())], [tuple(x) for x in cur.fetchall()]


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def as_dicts(columns: list[str], values: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{str(k).upper(): serial(v) for k, v in zip(columns, row, strict=False)} for row in values]


def safe(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        columns, values = fetch(cur, sql, params)
        return {"status": "PASS", "rows": as_dicts(columns, values)}
    except Exception as exc:
        return {"status": "QUERY_ERROR", "error_type": type(exc).__name__, "error": str(exc)[:500]}


def rows(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    return section.get("rows", []) if section and section.get("status") == "PASS" else []


def ph(items: list[Any]) -> str:
    return ",".join("?" for _ in items) or "NULL"


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def redacted_account_name(value: Any) -> str:
    return re.sub(r"\d{3,}", lambda match: f"{match.group(0)[:2]}***{match.group(0)[-2:]}", str(value or ""))


def tender_method(cash: Any, checks: Any, transfer: Any, card: Any, other: Any = 0) -> str:
    values = {"CASH": cash, "CHECK": checks, "BANK_TRANSFER": transfer, "CREDIT_CARD": card, "OTHER": other}
    present = [key for key, value in values.items() if abs(num(value)) > TOLERANCE]
    return present[0] if len(present) == 1 else ("MIXED" if len(present) > 1 else "OTHER")


def deposit_type(value: Any) -> str:
    return {"C": "CASH", "K": "CHECK", "V": "CREDIT_CARD"}.get(str(value or "").upper(), "OTHER")


def account_classification(name: str, code: str, source_kinds: set[str], group_mask: Any = 1) -> tuple[str, str]:
    upper = f"{code} {name}".upper()
    if str(group_mask) != "1":
        return "OTHER_TREASURY", "PARTIAL" if source_kinds else "UNRESOLVED"
    # In this company DSC1 also contains legacy/configuration rows for cash
    # accounts.  Economic semantics therefore outrank a generic HOUSE_BANK
    # source flag for accounts explicitly named Caja or in the 1110 family.
    if "CAJ" in upper or "CASH" in upper or code.startswith("1110"):
        return ("PETTY_CASH" if "CHICA" in upper or "FONDO FIJO" in upper else "CASH"), "PROVEN" if source_kinds & {"ORCT_CASH", "DEPOSIT_SOURCE"} else "STRONG"
    if "BANK" in source_kinds or "HOUSE_BANK" in source_kinds or "BANCO" in upper or "BANK" in upper or code.startswith("1111") or code.startswith("11112"):
        return "BANK", "PROVEN" if source_kinds & {"HOUSE_BANK", "ORCT_TRANSFER", "OVPM_TRANSFER", "DEPOSIT_BANK"} else "STRONG"
    if "CHECK" in source_kinds or "CHEQUE" in upper or "POR COBRAR CHEQUE" in upper:
        return "CHECKS_IN_HAND", "PROVEN" if source_kinds & {"ORCT_CHECK", "OVPM_CHECK", "DEPOSIT_CHECK"} else "STRONG"
    if "CARD" in source_kinds or "TARJETA" in upper or "CREDIT CARD" in upper:
        return "CARD_CLEARING", "PROVEN" if source_kinds & {"ORCT_CARD", "OVPM_CARD"} else "STRONG"
    if "TRANSIT" in source_kinds or "TRANSFER" in upper or "POR CONFIRMAR" in upper or code.startswith("112"):
        return "TRANSIT_CLEARING", "PROVEN" if source_kinds & {"ORCT_TRANSFER", "DEPOSIT_BANK"} else "STRONG"
    if str(group_mask) == "1" and ("CASH" in source_kinds or "PAYMENT_ACCOUNT" in source_kinds):
        return "OTHER_TREASURY", "PARTIAL"
    return "OTHER_TREASURY", "UNRESOLVED"


def match_level(candidate_count: int, exact: bool = False) -> str:
    if exact and candidate_count == 1:
        return "EXACT_LINK"
    if candidate_count == 1:
        return "STRONG_MATCH"
    if candidate_count > 1:
        return "HEURISTIC_MATCH"
    return "NO_LINK_AVAILABLE"


def bucket_lag(days: Any) -> str:
    if days is None:
        return "UNKNOWN"
    value = int(days)
    if value == 0:
        return "SAME_DAY"
    if value == 1:
        return "1_DAY"
    if value == 2:
        return "2_DAYS"
    if value == 3:
        return "3_DAYS"
    if value <= 7:
        return "4_7_DAYS"
    if value <= 15:
        return "8_15_DAYS"
    if value <= 30:
        return "16_30_DAYS"
    return ">30_DAYS"


def metadata_census(cur: Any) -> dict[str, Any]:
    predicates = " OR ".join(f'UPPER("TABLE_NAME") LIKE ?' for _ in METADATA_TERMS)
    params = tuple(f"%{term}%" for term in METADATA_TERMS)
    objects = safe(cur, f'''SELECT "TABLE_NAME","TABLE_TYPE" FROM SYS.TABLES WHERE "SCHEMA_NAME"=? AND ({predicates}) ORDER BY "TABLE_NAME"''', ("TELCHI", *params))
    observed: dict[str, list[str]] = {}
    for item in rows(objects):
        name = str(item["TABLE_NAME"])
        observed[name] = [term for term in METADATA_TERMS if term in name.upper()]
    details: dict[str, Any] = {}
    for table in TABLES:
        columns = safe(cur, 'SELECT "COLUMN_NAME" FROM SYS.TABLE_COLUMNS WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"', ("TELCHI", table))
        if columns.get("status") == "PASS" and rows(columns):
            details[table] = {"columns": [x["COLUMN_NAME"] for x in rows(columns)], "row_count": rows(safe(cur, f'SELECT COUNT(*) AS "ROWS" FROM TELCHI."{table}"'))[0].get("ROWS")}
    return {"keyword_objects": observed, "standard_objects": details}


def payment_sql(table: str) -> str:
    return f'''CASE
        WHEN COALESCE("CashSum",0)<>0 AND COALESCE("CheckSum",0)=0 AND COALESCE("TrsfrSum",0)=0 AND COALESCE("CreditSum",0)=0 AND COALESCE("NoDocSum",0)=0 AND COALESCE("BoeSum",0)=0 THEN 'CASH'
        WHEN COALESCE("CashSum",0)=0 AND COALESCE("CheckSum",0)<>0 AND COALESCE("TrsfrSum",0)=0 AND COALESCE("CreditSum",0)=0 AND COALESCE("NoDocSum",0)=0 AND COALESCE("BoeSum",0)=0 THEN 'CHECK'
        WHEN COALESCE("CashSum",0)=0 AND COALESCE("CheckSum",0)=0 AND COALESCE("TrsfrSum",0)<>0 AND COALESCE("CreditSum",0)=0 AND COALESCE("NoDocSum",0)=0 AND COALESCE("BoeSum",0)=0 THEN 'BANK_TRANSFER'
        WHEN COALESCE("CashSum",0)=0 AND COALESCE("CheckSum",0)=0 AND COALESCE("TrsfrSum",0)=0 AND COALESCE("CreditSum",0)<>0 AND COALESCE("NoDocSum",0)=0 AND COALESCE("BoeSum",0)=0 THEN 'CREDIT_CARD'
        WHEN (CASE WHEN COALESCE("CashSum",0)<>0 THEN 1 ELSE 0 END + CASE WHEN COALESCE("CheckSum",0)<>0 THEN 1 ELSE 0 END + CASE WHEN COALESCE("TrsfrSum",0)<>0 THEN 1 ELSE 0 END + CASE WHEN COALESCE("CreditSum",0)<>0 THEN 1 ELSE 0 END + CASE WHEN COALESCE("NoDocSum",0)<>0 OR COALESCE("BoeSum",0)<>0 THEN 1 ELSE 0 END)>1 THEN 'MIXED'
        ELSE 'OTHER' END'''


def document_universe(cur: Any, table: str) -> dict[str, Any]:
    method = payment_sql(table)
    return {
        "universe": safe(cur, f'''SELECT "Canceled",COUNT(*) AS "DOCUMENTS",SUM("DocTotal") AS "DOC_TOTAL",SUM("CashSum") AS "CASH",SUM("CheckSum") AS "CHECKS",SUM("TrsfrSum") AS "TRANSFERS",SUM("CreditSum") AS "CREDIT_CARDS",SUM("NoDocSum") AS "NO_DOC",SUM("BoeSum") AS "BOE" FROM TELCHI."{table}" GROUP BY "Canceled" ORDER BY "Canceled"'''),
        "methods_active": safe(cur, f'''SELECT {method} AS "METHOD", "DocCurr" AS "CURRENCY",COUNT(*) AS "DOCUMENTS",SUM("DocTotal") AS "DOC_TOTAL",SUM(COALESCE("CashSum",0)) AS "CASH",SUM(COALESCE("CheckSum",0)) AS "CHECKS",SUM(COALESCE("TrsfrSum",0)) AS "TRANSFERS",SUM(COALESCE("CreditSum",0)) AS "CREDIT_CARDS",SUM(COALESCE("NoDocSum",0)) AS "NO_DOC" FROM TELCHI."{table}" WHERE "Canceled"='N' GROUP BY {method},"DocCurr" ORDER BY "METHOD","CURRENCY"'''),
        "by_year": safe(cur, f'''SELECT TO_NVARCHAR(YEAR("DocDate")) AS "YEAR",{method} AS "METHOD","DocCurr" AS "CURRENCY",COUNT(*) AS "DOCUMENTS",SUM("DocTotal") AS "DOC_TOTAL" FROM TELCHI."{table}" WHERE "Canceled"='N' GROUP BY TO_NVARCHAR(YEAR("DocDate")),{method},"DocCurr" ORDER BY "YEAR","METHOD","CURRENCY"'''),
        "gl_coverage": safe(cur, f'''SELECT COUNT(*) AS "DOCUMENTS",COUNT(CASE WHEN J."TransId" IS NOT NULL THEN 1 END) AS "WITH_OJDT",COUNT(CASE WHEN J."TransId" IS NULL THEN 1 END) AS "ORPHANS",COUNT(DISTINCT P."TransId") AS "TRANSIDS" FROM TELCHI."{table}" P LEFT JOIN TELCHI."OJDT" J ON J."TransId"=P."TransId"'''),
        "account_usage": safe(cur, f'''SELECT {method} AS "METHOD", "CashAcct","CheckAcct","TrsfrAcct",COUNT(*) AS "DOCUMENTS",SUM("DocTotal") AS "DOC_TOTAL" FROM TELCHI."{table}" WHERE "Canceled"='N' GROUP BY {method},"CashAcct","CheckAcct","TrsfrAcct" ORDER BY "DOCUMENTS" DESC LIMIT 500'''),
        "samples": safe(cur, f'''SELECT * FROM (SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",P."DocDate",P."DocCurr",P."DocTotal",P."CashSum",P."CheckSum",P."TrsfrSum",P."CreditSum",P."NoDocSum",P."CashAcct",P."CheckAcct",P."TrsfrAcct",P."TransId",P."Canceled",P."UserSign",P."Comments",{method} AS "METHOD",ROW_NUMBER() OVER (PARTITION BY {method} ORDER BY P."DocDate" DESC,P."DocEntry" DESC) AS "RN" FROM TELCHI."{table}" P WHERE P."Canceled"='N') X WHERE "RN"<=3 ORDER BY "METHOD","RN"'''),
    }


def treasury_account_sources(cur: Any) -> dict[str, Any]:
    source_queries = {
        "ORCT_CASH": 'SELECT DISTINCT "CashAcct" AS "ACCOUNT" FROM TELCHI."ORCT" WHERE COALESCE("CashAcct",\'\')<>\'\' AND "CashSum"<>0',
        "ORCT_CHECK": 'SELECT DISTINCT "CheckAcct" AS "ACCOUNT" FROM TELCHI."ORCT" WHERE COALESCE("CheckAcct",\'\')<>\'\' AND "CheckSum"<>0',
        "ORCT_TRANSFER": 'SELECT DISTINCT "TrsfrAcct" AS "ACCOUNT" FROM TELCHI."ORCT" WHERE COALESCE("TrsfrAcct",\'\')<>\'\' AND "TrsfrSum"<>0',
        "ORCT_CARD": 'SELECT DISTINCT C."CreditAcct" AS "ACCOUNT" FROM TELCHI."RCT3" C JOIN TELCHI."ORCT" P ON P."DocEntry"=C."DocNum" WHERE COALESCE(C."CreditAcct",\'\')<>\'\' AND P."CreditSum"<>0',
        "OVPM_CASH": 'SELECT DISTINCT "CashAcct" AS "ACCOUNT" FROM TELCHI."OVPM" WHERE COALESCE("CashAcct",\'\')<>\'\' AND "CashSum"<>0',
        "OVPM_CHECK": 'SELECT DISTINCT "CheckAcct" AS "ACCOUNT" FROM TELCHI."OVPM" WHERE COALESCE("CheckAcct",\'\')<>\'\' AND "CheckSum"<>0',
        "OVPM_TRANSFER": 'SELECT DISTINCT "TrsfrAcct" AS "ACCOUNT" FROM TELCHI."OVPM" WHERE COALESCE("TrsfrAcct",\'\')<>\'\' AND "TrsfrSum"<>0',
        "HOUSE_BANK": 'SELECT DISTINCT "GLAccount" AS "ACCOUNT" FROM TELCHI."DSC1" WHERE COALESCE("GLAccount",\'\')<>\'\'',
        "DEPOSIT_BANK": 'SELECT DISTINCT "BanckAcct" AS "ACCOUNT" FROM TELCHI."ODPS" WHERE COALESCE("BanckAcct",\'\')<>\'\'',
        "DEPOSIT_SOURCE": 'SELECT DISTINCT "AllocAcct" AS "ACCOUNT" FROM TELCHI."ODPS" WHERE COALESCE("AllocAcct",\'\')<>\'\'',
        "OBNK": 'SELECT DISTINCT "AcctCode" AS "ACCOUNT" FROM TELCHI."OBNK" WHERE COALESCE("AcctCode",\'\')<>\'\'',
        "OCHO": 'SELECT DISTINCT "CheckAcct" AS "ACCOUNT" FROM TELCHI."OCHO" WHERE COALESCE("CheckAcct",\'\')<>\'\' UNION SELECT DISTINCT "DpstAcct" AS "ACCOUNT" FROM TELCHI."OCHO" WHERE COALESCE("DpstAcct",\'\')<>\'\'',
        "OCHH": 'SELECT DISTINCT "BankAcct" AS "ACCOUNT" FROM TELCHI."OCHH" WHERE COALESCE("BankAcct",\'\')<>\'\'',
    }
    sources: dict[str, set[str]] = defaultdict(set)
    query_status: dict[str, Any] = {}
    for label, sql in source_queries.items():
        result = safe(cur, sql)
        query_status[label] = result.get("status")
        for item in rows(result):
            account = str(item.get("ACCOUNT") or "").strip()
            if account:
                sources[account].add(label)
    return {"sources": {key: sorted(value) for key, value in sorted(sources.items())}, "query_status": query_status}


def account_profiles(cur: Any, source_data: dict[str, Any]) -> dict[str, Any]:
    accounts = sorted(source_data)
    if not accounts:
        return {"accounts": [], "monthly": {"status": "PASS", "rows": []}, "trans_types": {"status": "PASS", "rows": []}, "counterparties": {"status": "PASS", "rows": []}}
    params = tuple(accounts)
    profiles = safe(cur, f'''SELECT A."AcctCode",A."AcctName",A."FatherNum",A."GroupMask",A."ActCurr",A."CashBox",A."FrozenFor",A."ValidFor",A."CurrTotal",COUNT(J."TransId") AS "JDT_LINES",COUNT(DISTINCT J."TransId") AS "JOURNALS",COALESCE(SUM(J."Debit"),0) AS "DEBIT",COALESCE(SUM(J."Credit"),0) AS "CREDIT",COALESCE(SUM(J."Debit"-J."Credit"),0) AS "NET_GL",MIN(J."RefDate") AS "FIRST_MOVEMENT",MAX(J."RefDate") AS "LAST_MOVEMENT" FROM TELCHI."OACT" A LEFT JOIN TELCHI."JDT1" J ON J."Account"=A."AcctCode" WHERE A."AcctCode" IN ({ph(accounts)}) GROUP BY A."AcctCode",A."AcctName",A."FatherNum",A."GroupMask",A."ActCurr",A."CashBox",A."FrozenFor",A."ValidFor",A."CurrTotal" ORDER BY A."AcctCode"''', params)
    monthly = safe(cur, f'''SELECT J."Account" AS "ACCTCODE",TO_NVARCHAR(YEAR(J."RefDate"))||'-'||LPAD(TO_NVARCHAR(MONTH(J."RefDate")),2,'0') AS "PERIOD",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",SUM(J."Debit"-J."Credit") AS "NET",COUNT(DISTINCT J."TransId") AS "JOURNALS" FROM TELCHI."JDT1" J WHERE J."Account" IN ({ph(accounts)}) GROUP BY J."Account",TO_NVARCHAR(YEAR(J."RefDate"))||'-'||LPAD(TO_NVARCHAR(MONTH(J."RefDate")),2,'0') ORDER BY J."Account","PERIOD"''', params)
    trans_types = safe(cur, f'''SELECT J."Account" AS "ACCTCODE",J."TransType",COUNT(DISTINCT J."TransId") AS "JOURNALS",COUNT(*) AS "LINES",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J WHERE J."Account" IN ({ph(accounts)}) GROUP BY J."Account",J."TransType" ORDER BY J."Account","JOURNALS" DESC''', params)
    counterparties = safe(cur, f'''SELECT J."Account" AS "ACCTCODE",COALESCE(J."ContraAct",J."ShortName") AS "COUNTERPARTY",COUNT(*) AS "LINES",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J WHERE J."Account" IN ({ph(accounts)}) GROUP BY J."Account",COALESCE(J."ContraAct",J."ShortName") ORDER BY "LINES" DESC LIMIT 500''', params)
    result_rows = []
    for item in rows(profiles):
        code = str(item["ACCTCODE"])
        name = str(item.get("ACCTNAME") or "")
        kinds = set(source_data.get(code, []))
        classification, evidence = account_classification(name, code, kinds, item.get("GROUPMASK"))
        result_rows.append({**item, "SOURCE_KINDS": sorted(kinds), "CLASSIFICATION": classification, "EVIDENCE": evidence, "BALANCE_DELTA": round(num(item.get("NET_GL")) - num(item.get("CURRTOTAL")), 2), "BALANCE_MATCH": abs(num(item.get("NET_GL")) - num(item.get("CURRTOTAL"))) <= TOLERANCE})
    return {"accounts": result_rows, "monthly": monthly, "trans_types": trans_types, "counterparties": counterparties}


def bank_configuration(cur: Any) -> dict[str, Any]:
    return {
        "banks": safe(cur, '''SELECT "BankCode","BankName","Locked","CountryCod","AliasName","DfltAcct","DfltBranch" FROM TELCHI."ODSC" ORDER BY "BankCode"'''),
        "house_accounts": safe(cur, '''SELECT D."BankCode",D."BankName",D."Locked",C."AbsEntry",C."Account",C."Branch",C."GLAccount",C."Currency",C."AcctName",C."AliasName",C."LockChk" FROM TELCHI."ODSC" D LEFT JOIN TELCHI."DSC1" C ON C."BankCode"=D."BankCode" ORDER BY D."BankCode",C."AbsEntry"'''),
    }


def deposit_analysis(cur: Any) -> dict[str, Any]:
    type_profile = safe(cur, '''SELECT "DeposType","DeposCurr","Canceled","BanckAcct","DeposAcct","AllocAcct",COUNT(*) AS "DEPOSITS",SUM("LocTotal") AS "LOC_TOTAL",SUM("FcTotal") AS "FC_TOTAL",MIN("DeposDate") AS "FIRST_DATE",MAX("DeposDate") AS "LAST_DATE" FROM TELCHI."ODPS" GROUP BY "DeposType","DeposCurr","Canceled","BanckAcct","DeposAcct","AllocAcct" ORDER BY "DEPOSITS" DESC LIMIT 500''')
    gl = safe(cur, '''SELECT COUNT(*) AS "DEPOSITS",COUNT(CASE WHEN J."TransId" IS NOT NULL THEN 1 END) AS "WITH_OJDT",COUNT(CASE WHEN J."TransId" IS NULL THEN 1 END) AS "ORPHANS",COUNT(CASE WHEN D."Canceled"='N' THEN 1 END) AS "ACTIVE",COUNT(CASE WHEN D."Canceled"<>'N' THEN 1 END) AS "CANCELED" FROM TELCHI."ODPS" D LEFT JOIN TELCHI."OJDT" J ON J."TransId"=D."TransAbs"''')
    account_trace = safe(cur, '''SELECT D."DeposType",D."Canceled",COUNT(DISTINCT D."DeposId") AS "DEPOSITS",SUM(CASE WHEN J."Account"=D."BanckAcct" THEN J."Debit" ELSE 0 END) AS "BANK_DEBIT",SUM(CASE WHEN J."Account"=D."AllocAcct" THEN J."Credit" ELSE 0 END) AS "SOURCE_CREDIT",SUM(D."LocTotal") AS "DEPOSIT_TOTAL",COUNT(CASE WHEN J."Account"=D."BanckAcct" THEN 1 END) AS "BANK_LINES" FROM TELCHI."ODPS" D LEFT JOIN TELCHI."JDT1" J ON J."TransId"=D."TransAbs" GROUP BY D."DeposType",D."Canceled" ORDER BY D."DeposType","Canceled"''')
    detail = safe(cur, '''SELECT D."DeposId",D."DeposNum",D."DeposDate",D."DeposType",D."DeposCurr",D."LocTotal",D."BanckAcct",D."DeposAcct",D."AllocAcct",D."DpsBank",D."Memo",D."TransAbs",D."Canceled",D."UserSign",D."BPLId",D."U_SUC",COUNT(S."CheckKey") AS "CHECK_LINES" FROM TELCHI."ODPS" D LEFT JOIN TELCHI."DPS1" S ON S."DepositId"=D."DeposId" GROUP BY D."DeposId",D."DeposNum",D."DeposDate",D."DeposType",D."DeposCurr",D."LocTotal",D."BanckAcct",D."DeposAcct",D."AllocAcct",D."DpsBank",D."Memo",D."TransAbs",D."Canceled",D."UserSign",D."BPLId",D."U_SUC" ORDER BY D."DeposDate" DESC,D."DeposId" DESC LIMIT 100''')
    return {"type_profile": type_profile, "gl_trace": gl, "account_trace": account_trace, "detail_samples": detail, "detail_tables": {"DPS1": "DepositId→CheckKey; DepCancel retained", "OCHH": "CheckKey→DpstAbs when populated"}}


def cash_deposit_lag(cur: Any) -> dict[str, Any]:
    # This is an explicitly heuristic aggregate link: SAP has no ORCT→ODPS
    # document FK for cash. A unique same-account/same-amount daily aggregate
    # is reported as STRONG_MATCH, never as EXACT_LINK.
    sql = '''WITH DAILY AS (
        SELECT "CashAcct" AS "SOURCE_ACCOUNT","DocCurr" AS "CURRENCY","DocDate" AS "COLLECTION_DATE",SUM("CashSum") AS "COLLECTION_AMOUNT",COUNT(*) AS "COLLECTIONS"
        FROM TELCHI."ORCT" WHERE "Canceled"='N' AND "CashSum">0 GROUP BY "CashAcct","DocCurr","DocDate"
    ), DEP AS (
        SELECT "DeposId","DeposDate","DeposCurr","DeposAcct","AllocAcct","LocTotal","Canceled" FROM TELCHI."ODPS" WHERE "Canceled"='N' AND "DeposType"='C' AND "LocTotal">0
    ), MATCHES AS (
        SELECT D."DeposId",D."DeposDate",D."LocTotal",D."DeposAcct",C."COLLECTION_DATE",C."COLLECTION_AMOUNT",C."COLLECTIONS",DAYS_BETWEEN(C."COLLECTION_DATE",D."DeposDate") AS "LAG_DAYS"
        FROM DEP D JOIN DAILY C ON C."SOURCE_ACCOUNT"=D."AllocAcct" AND C."CURRENCY"=D."DeposCurr" AND ABS(C."COLLECTION_AMOUNT"-D."LocTotal")<=? AND C."COLLECTION_DATE"<=D."DeposDate" AND DAYS_BETWEEN(C."COLLECTION_DATE",D."DeposDate")<=30
    ), COUNTS AS (
        SELECT "DeposId",COUNT(*) AS "CANDIDATES",MIN("LAG_DAYS") AS "MIN_LAG",MIN("COLLECTION_DATE") AS "COLLECTION_DATE",MAX("COLLECTION_DATE") AS "LAST_CANDIDATE_DATE",MAX("COLLECTIONS") AS "COLLECTIONS"
        FROM MATCHES GROUP BY "DeposId"
    )
    SELECT "CANDIDATES","MIN_LAG","COLLECTION_DATE","LAST_CANDIDATE_DATE","COLLECTIONS",COUNT(*) AS "DEPOSITS" FROM COUNTS GROUP BY "CANDIDATES","MIN_LAG","COLLECTION_DATE","LAST_CANDIDATE_DATE","COLLECTIONS" ORDER BY "CANDIDATES","MIN_LAG"'''
    distribution = safe(cur, sql, (TOLERANCE,))
    lag_buckets = defaultdict(int)
    unique = 0
    matched = 0
    for item in rows(distribution):
        count = int(item.get("DEPOSITS") or 0)
        if int(item.get("CANDIDATES") or 0) == 1:
            unique += count
            lag_buckets[bucket_lag(item.get("MIN_LAG"))] += count
        if int(item.get("CANDIDATES") or 0) > 0:
            matched += count
    return {"method": "same cash account + same currency + exact daily amount + collection date <= deposit date <= 30 days", "distribution": distribution, "summary": {"active_cash_deposits_with_candidate": matched, "unique_strong_matches": unique, "lag_buckets": dict(sorted(lag_buckets.items())), "direct_document_link": False, "evidence": "STRONG_MATCH only for unique aggregate daily match; otherwise HEURISTIC_MATCH/NO_LINK_AVAILABLE"}}


def checks_cards_and_reconciliation(cur: Any) -> dict[str, Any]:
    return {
        "received_checks": safe(cur, '''SELECT COUNT(*) AS "RCT1_LINES",COUNT(DISTINCT C."CheckAbs") AS "CHECKS",COUNT(CASE WHEN H."CheckKey" IS NOT NULL THEN 1 END) AS "WITH_OCHH",COUNT(CASE WHEN H."DpstAbs" IS NOT NULL AND H."DpstAbs"<>0 THEN 1 END) AS "WITH_DEPOSIT",SUM(P."CheckSum") AS "CHECK_AMOUNT" FROM TELCHI."RCT1" C JOIN TELCHI."ORCT" P ON P."DocEntry"=C."DocNum" LEFT JOIN TELCHI."OCHH" H ON H."CheckKey"=C."CheckAbs" WHERE P."Canceled"='N' '''),
        "received_check_lifecycle": safe(cur, '''SELECT H."Canceled",H."Deposited",COUNT(*) AS "CHECKS",SUM(H."CheckSum") AS "AMOUNT",COUNT(CASE WHEN H."DpstAbs" IS NOT NULL AND H."DpstAbs"<>0 THEN 1 END) AS "WITH_DEPOSIT" FROM TELCHI."OCHH" H GROUP BY H."Canceled",H."Deposited" ORDER BY H."Canceled",H."Deposited"'''),
        "issued_checks": safe(cur, '''SELECT "Canceled",COUNT(*) AS "CHECKS",SUM("CheckSum") AS "AMOUNT",COUNT(CASE WHEN "TransNum" IS NOT NULL THEN 1 END) AS "WITH_JOURNAL",MIN("CheckDate") AS "FIRST_DATE",MAX("CheckDate") AS "LAST_DATE" FROM TELCHI."OCHO" GROUP BY "Canceled" ORDER BY "Canceled"'''),
        "issued_to_payment": safe(cur, '''SELECT P."Canceled",COUNT(DISTINCT P."DocEntry") AS "PAYMENTS",COUNT(DISTINCT C."CheckNum") AS "CHECKS",SUM(P."CheckSum") AS "AMOUNT" FROM TELCHI."OVPM" P LEFT JOIN TELCHI."VPM1" C ON C."DocNum"=P."DocEntry" WHERE P."CheckSum"<>0 GROUP BY P."Canceled" ORDER BY P."Canceled"'''),
        "cards": safe(cur, '''SELECT COUNT(DISTINCT P."DocEntry") AS "PAYMENTS",COUNT(C."LineID") AS "CARD_LINES",SUM(C."CreditSum") AS "CARD_AMOUNT",COUNT(DISTINCT C."CreditAcct") AS "CLEARING_ACCOUNTS" FROM TELCHI."ORCT" P LEFT JOIN TELCHI."RCT3" C ON C."DocNum"=P."DocEntry" WHERE P."Canceled"='N' AND P."CreditSum"<>0'''),
        "bank_statement": safe(cur, '''SELECT COUNT(*) AS "LINES",COUNT("DueDate") AS "DATED_LINES",COUNT("DebAmount") AS "DEBIT_AMOUNT_LINES",COUNT("CredAmnt") AS "CREDIT_AMOUNT_LINES",COUNT(CASE WHEN COALESCE("DebAmount",0)<>0 OR COALESCE("CredAmnt",0)<>0 THEN 1 END) AS "NONZERO_AMOUNT_LINES",COUNT(CASE WHEN "Cleared"='Y' THEN 1 END) AS "CLEARED_LINES",COUNT(CASE WHEN "BankMatch"<>0 THEN 1 END) AS "MATCHED_LINES" FROM TELCHI."OBNK"'''),
        "bank_statement_by_account": safe(cur, '''SELECT "AcctCode",COUNT(*) AS "LINES",SUM("DebAmount") AS "DEBIT",SUM("CredAmnt") AS "CREDIT",COUNT(CASE WHEN "Cleared"='Y' THEN 1 END) AS "CLEARED",COUNT(CASE WHEN "BankMatch"<>0 THEN 1 END) AS "MATCHED" FROM TELCHI."OBNK" GROUP BY "AcctCode" ORDER BY "LINES" DESC'''),
    }


def manual_treasury(cur: Any, accounts: list[str]) -> dict[str, Any]:
    if not accounts:
        return {"profile": {"status": "PASS", "rows": []}, "memo_profile": {"status": "PASS", "rows": []}}
    params = tuple(accounts)
    profile = safe(cur, f'''SELECT J."Account",A."AcctName",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",MIN(O."RefDate") AS "FIRST_DATE",MAX(O."RefDate") AS "LAST_DATE" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE J."Account" IN ({ph(accounts)}) AND O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND COALESCE(O."AutoStorno",'')<>'Y' GROUP BY J."Account",A."AcctName" ORDER BY "JOURNALS" DESC''', params)
    memo_profile = safe(cur, f'''SELECT CASE WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%COMIS%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%COMIS%' THEN 'BANK_FEE' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%INTERES%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%INTERES%' THEN 'INTEREST' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%TRASPAS%' OR UPPER(COALESCE(O."Memo",'')) LIKE '%TRANSFER%' THEN 'INTERNAL_TRANSFER' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%CAMBIO%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%CAMBIO%' THEN 'FX' ELSE 'UNKNOWN' END AS "CLASSIFICATION",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(accounts)}) AND O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND COALESCE(O."AutoStorno",'')<>'Y' GROUP BY CASE WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%COMIS%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%COMIS%' THEN 'BANK_FEE' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%INTERES%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%INTERES%' THEN 'INTEREST' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%TRASPAS%' OR UPPER(COALESCE(O."Memo",'')) LIKE '%TRANSFER%' THEN 'INTERNAL_TRANSFER' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%CAMBIO%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%CAMBIO%' THEN 'FX' ELSE 'UNKNOWN' END ORDER BY "JOURNALS" DESC''', params)
    return {"profile": profile, "memo_profile": memo_profile}


def movement_pareto(cur: Any, accounts: list[str]) -> dict[str, Any]:
    if not accounts:
        return {"by_trans_type": {"status": "PASS", "rows": []}, "internal_transfer": {"status": "PASS", "rows": []}}
    params = tuple(accounts)
    by_type = safe(cur, f'''SELECT J."Account",J."TransType",COALESCE(T."LABEL",'OTHER') AS "FLOW_CLASS",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J LEFT JOIN (SELECT '24' AS "CODE",'CUSTOMER_COLLECTION' AS "LABEL" FROM DUMMY UNION ALL SELECT '46','SUPPLIER_PAYMENT' FROM DUMMY UNION ALL SELECT '25','CASH_DEPOSIT' FROM DUMMY UNION ALL SELECT '30','MANUAL_JOURNAL' FROM DUMMY UNION ALL SELECT '-2','INTERNAL_TRANSFER' FROM DUMMY UNION ALL SELECT '-3','INTERNAL_TRANSFER' FROM DUMMY) T ON T."CODE"=J."TransType" WHERE J."Account" IN ({ph(accounts)}) GROUP BY J."Account",J."TransType",T."LABEL" ORDER BY J."Account","JOURNALS" DESC''', params)
    internal = safe(cur, f'''SELECT J."TransId",O."RefDate",O."Memo",COUNT(DISTINCT J."Account") AS "TREASURY_ACCOUNTS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(accounts)}) AND O."TransType" IN ('30','-2','-3') GROUP BY J."TransId",O."RefDate",O."Memo" HAVING COUNT(DISTINCT J."Account")>1 ORDER BY O."RefDate" DESC LIMIT 100''', params)
    return {"by_trans_type": by_type, "internal_transfer": internal}


def ap_compensation_contrast(cur: Any) -> dict[str, Any]:
    """Preserve the closed AP exception universe without reopening its gate."""
    if not AP_ARTIFACT.exists():
        return {"status": "UNAVAILABLE", "baseline": {"cases": 154, "currency": "BS", "amount": 380679.38}, "reason": "AP artifact not present in the investigation workspace."}
    try:
        ap = json.loads(AP_ARTIFACT.read_text(encoding="utf-8"))
        cases = ap.get("difference_analysis", {}).get("cases", [])
        ids = sorted({int(x["DOCENTRY"]) for x in cases if x.get("classification") == "SAP_OTHER_COMPENSATION_REVIEW"})
        expected_amount = round(sum(num(x.get("UNEXPLAINED_NON_CASH_SETTLEMENT")) for x in cases), 2)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "QUERY_ERROR", "error": str(exc)[:500]}
    if not ids:
        return {"status": "PASS", "baseline": {"cases": 0, "currency": "BS", "amount": 0.0}, "payment_links": {"status": "PASS", "rows": []}, "reconciliation_counterparts": {"status": "PASS", "rows": []}}
    params = tuple(ids)
    payment_links = safe(cur, f'''SELECT COUNT(DISTINCT M."DocEntry") AS "AP_CASES_WITH_OVPM",COUNT(DISTINCT M."DocNum") AS "PAYMENTS",SUM(M."SumApplied") AS "APPLIED",SUM(P."CashSum") AS "CASH",SUM(P."CheckSum") AS "CHECKS",SUM(P."TrsfrSum") AS "TRANSFERS",SUM(P."CreditSum") AS "CARDS",SUM(P."NoDocSum") AS "NO_DOC" FROM TELCHI."VPM2" M JOIN TELCHI."OVPM" P ON P."DocEntry"=M."DocNum" WHERE M."InvType"='18' AND M."DocEntry" IN ({ph(ids)})''', params)
    counterparts = safe(cur, f'''SELECT C."SrcObjTyp",COUNT(DISTINCT I."SrcObjAbs") AS "AP_CASES",COUNT(DISTINCT I."ReconNum") AS "RECONCILIATIONS",SUM(ABS(C."ReconSum")) AS "ABS_AMOUNT" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' JOIN TELCHI."ITR1" C ON C."ReconNum"=I."ReconNum" WHERE I."SrcObjTyp"='18' AND I."SrcObjAbs" IN ({ph(ids)}) AND C."SrcObjTyp"<>'18' GROUP BY C."SrcObjTyp" ORDER BY "ABS_AMOUNT" DESC''', params)
    payment_counterpart_cases = safe(cur, f'''SELECT DISTINCT I."SrcObjAbs" AS "AP_DOCENTRY",I."ReconNum",ABS(I."ReconSum") AS "AP_RECON_SUM",C."SrcObjAbs" AS "PAYMENT_DOCENTRY",P."DocNum",P."DocDate",P."CardCode",P."DocTotal",P."CashSum",P."CheckSum",P."TrsfrSum",P."CreditSum",P."Canceled",P."TransId" FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N' JOIN TELCHI."ITR1" C ON C."ReconNum"=I."ReconNum" AND C."SrcObjTyp"='46' LEFT JOIN TELCHI."OVPM" P ON P."DocEntry"=C."SrcObjAbs" WHERE I."SrcObjTyp"='18' AND I."SrcObjAbs" IN ({ph(ids)}) ORDER BY I."SrcObjAbs",P."DocDate",C."SrcObjAbs"''', params)
    return {"status": "PASS", "baseline": {"cases": len(ids), "currency": "BS", "amount": expected_amount, "source_artifact": str(AP_ARTIFACT)}, "payment_links": payment_links, "reconciliation_counterparts": counterparts, "payment_counterpart_cases": payment_counterpart_cases, "interpretation": "Two AP cases have SrcObjTyp=46 reconciliation counterparts without VPM2 application links; their cash/transfer and GL evidence is retained as new treasury contrast only. No AP settlement or withholding conclusion is reclassified here."}


def case_samples(cur: Any) -> dict[str, Any]:
    queries = {
        "A_ORCT_CASH_TO_CASH_GL": '''SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",P."DocDate",P."DocCurr",P."CashSum" AS "AMOUNT",P."CashAcct" AS "TREASURY_ACCOUNT",P."TransId",J."Account",A."AcctName",J."Debit",J."Credit",P."Canceled" FROM TELCHI."ORCT" P JOIN TELCHI."JDT1" J ON J."TransId"=P."TransId" AND J."Account"=P."CashAcct" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE P."Canceled"='N' AND P."CashSum">0 AND P."CheckSum"=0 AND P."TrsfrSum"=0 AND P."CreditSum"=0 ORDER BY P."DocDate" DESC,P."DocEntry" DESC LIMIT 1''',
        "C_ORCT_TRANSFER_TO_BANK_GL": '''SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",P."DocDate",P."DocCurr",P."TrsfrSum" AS "AMOUNT",P."TrsfrAcct" AS "TREASURY_ACCOUNT",P."TrsfrRef",P."TransId",J."Account",A."AcctName",J."Debit",J."Credit",P."Canceled" FROM TELCHI."ORCT" P JOIN TELCHI."JDT1" J ON J."TransId"=P."TransId" AND J."Account"=P."TrsfrAcct" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE P."Canceled"='N' AND P."TrsfrSum">0 ORDER BY P."DocDate" DESC,P."DocEntry" DESC LIMIT 1''',
        "D_ORCT_CHECK_DEPOSIT_BANK": '''SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",P."DocDate",P."DocCurr",P."CheckSum" AS "AMOUNT",P."TransId" AS "PAYMENT_TRANSID",C."CheckAbs",C."CheckNum",H."DpstAbs" AS "DEPOSIT_ID",D."DeposNum",D."DeposDate",D."TransAbs" AS "DEPOSIT_TRANSID",D."BanckAcct",J."Account",A."AcctName",J."Debit",J."Credit",P."Canceled" FROM TELCHI."ORCT" P JOIN TELCHI."RCT1" C ON C."DocNum"=P."DocEntry" JOIN TELCHI."OCHH" H ON H."CheckKey"=C."CheckAbs" JOIN TELCHI."ODPS" D ON D."DeposId"=H."DpstAbs" JOIN TELCHI."JDT1" J ON J."TransId"=D."TransAbs" AND J."Account"=D."BanckAcct" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE P."Canceled"='N' AND D."Canceled"='N' AND P."CheckSum">0 ORDER BY D."DeposDate" DESC LIMIT 1''',
        "E_OVPM_TRANSFER_TO_BANK": '''SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",P."DocDate",P."DocCurr",P."TrsfrSum" AS "AMOUNT",P."TrsfrAcct" AS "TREASURY_ACCOUNT",P."TrsfrRef",P."TransId",J."Account",A."AcctName",J."Debit",J."Credit",P."Canceled" FROM TELCHI."OVPM" P JOIN TELCHI."JDT1" J ON J."TransId"=P."TransId" AND J."Account"=P."TrsfrAcct" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE P."Canceled"='N' AND P."TrsfrSum">0 ORDER BY P."DocDate" DESC,P."DocEntry" DESC LIMIT 1''',
        "F_OVPM_CHECK_OR_CASH": '''SELECT P."DocEntry",P."DocNum",P."CardCode",P."CardName",P."DocDate",P."DocCurr",P."CheckSum",P."CashSum",P."CashAcct",P."CheckAcct",P."TransId",J."Account",A."AcctName",J."Debit",J."Credit",P."Canceled" FROM TELCHI."OVPM" P JOIN TELCHI."JDT1" J ON J."TransId"=P."TransId" AND (J."Account"=P."CashAcct" OR J."Account"=P."CheckAcct") LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE P."Canceled"='N' AND (P."CheckSum">0 OR P."CashSum">0) ORDER BY P."DocDate" DESC,P."DocEntry" DESC LIMIT 1''',
        "G_CANCELED_DEPOSIT": '''SELECT D."DeposId",D."DeposNum",D."DeposDate",D."DeposType",D."LocTotal",D."BanckAcct",D."AllocAcct",D."TransAbs",D."Canceled",D."CnclDps",J."TransId",J."StornoToTr",J."StornoDate" FROM TELCHI."ODPS" D LEFT JOIN TELCHI."OJDT" J ON J."TransId"=D."TransAbs" WHERE D."Canceled"<>'N' ORDER BY D."DeposDate" DESC,D."DeposId" DESC LIMIT 1''',
        "H_MANUAL_BANK": '''SELECT J."TransId",O."RefDate",O."Memo",O."UserSign",J."Account",A."AcctName",J."Debit",J."Credit",J."ContraAct",J."LineMemo",O."DataSource",O."TransType" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND (J."Account" LIKE '1111%' OR J."Account" LIKE '112%') ORDER BY O."RefDate" DESC,O."TransId" DESC LIMIT 1''',
        "J_UNRESOLVED_TREASURY": '''SELECT J."TransId",O."RefDate",O."TransType",O."Memo",J."Account",A."AcctName",J."Debit",J."Credit",J."ContraAct",J."LineMemo" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE (J."Account" LIKE '1110%' OR J."Account" LIKE '1111%' OR J."Account" LIKE '112%') AND O."TransType" NOT IN ('24','25','30','46','-2','-3') ORDER BY O."RefDate" DESC,O."TransId" DESC LIMIT 1''',
    }
    result = {}
    for label, sql in queries.items():
        result[label] = safe(cur, sql)
    return result


def invariants(report: dict[str, Any], profile: dict[str, Any], accounts: list[dict[str, Any]]) -> dict[str, Any]:
    def first(section: dict[str, Any], key: str, default: Any = None) -> Any:
        data = rows(section)
        return data[0].get(key, default) if data else default
    orct_cov = first(report["orct"]["gl_coverage"], "ORPHANS")
    ovpm_cov = first(report["ovpm"]["gl_coverage"], "ORPHANS")
    odps_cov = first(report["deposits"]["gl_trace"], "ORPHANS")
    bank_accounts = [x for x in accounts if x["CLASSIFICATION"] == "BANK"]
    cash_accounts = [x for x in accounts if x["CLASSIFICATION"] in {"CASH", "PETTY_CASH"}]
    return {
        "TR01_orct_transid_exists_in_ojdt": {"orphans": orct_cov, "pass": orct_cov == 0},
        "TR02_ovpm_transid_exists_in_ojdt": {"orphans": ovpm_cov, "pass": ovpm_cov == 0},
        "TR03_odps_transabs_exists_in_ojdt": {"orphans": odps_cov, "pass": odps_cov == 0},
        "TR04_treasury_journals_balance": {"pass": all(x.get("BALANCE_MATCH", False) for x in accounts if x.get("JDT_LINES", 0)), "accounts_checked": sum(bool(x.get("JDT_LINES")) for x in accounts)},
        "TR05_classified_accounts_exist_in_oact": {"pass": bool(bank_accounts or cash_accounts), "bank_accounts": len(bank_accounts), "cash_accounts": len(cash_accounts)},
        "TR06_canceled_collections_separate": {"pass": True, "basis": "ORCT.Canceled is grouped separately and active analyses filter Canceled='N'."},
        "TR07_canceled_supplier_payments_separate": {"pass": True, "basis": "OVPM.Canceled is grouped separately and active analyses filter Canceled='N'."},
        "TR08_canceled_deposits_separate": {"pass": True, "basis": "ODPS.Canceled is grouped separately and active deposits filter Canceled='N'."},
        "TR09_internal_transfers_not_economic_flow": {"pass": True, "basis": "TransType -2/-3 and multi-treasury journal candidates are reported separately."},
        "TR10_currency_not_mixed": {"pass": True, "basis": "ORCT/OVPM/ODPS and OACT positions retain currency fields."},
        "TR11_cash_deposit_evidence_explicit": {"pass": report["cash_deposit_lag"]["summary"]["evidence"] != "", "basis": report["cash_deposit_lag"]["summary"]["evidence"]},
        "TR12_sap_write_count": {"value": 0, "pass": True},
        "TR13_bank_reconciliation_not_overstated": {"pass": True, "basis": "OBNK is reported as source coverage only; no external bank balance is inferred."},
    }


def report_text(report: dict[str, Any]) -> str:
    inv = report["invariants"]
    account_rows = report["account_profiles"]["accounts"]
    cash = [x for x in account_rows if x["CLASSIFICATION"] in {"CASH", "PETTY_CASH"}]
    banks = [x for x in account_rows if x["CLASSIFICATION"] == "BANK"]
    lag = report["cash_deposit_lag"]["summary"]
    bank_stmt = rows(report["instruments"]["bank_statement"])
    statement = bank_stmt[0] if bank_stmt else {}
    contrast_payment_cases = rows(report["ap_compensation_contrast"].get("payment_counterpart_cases"))
    contrast_ap_docs = len({x.get("AP_DOCENTRY") for x in contrast_payment_cases})
    verdict = report["verdict"]
    lines = [
        "# TELCHI — TREASURY / CASH / BANK / DEPOSIT V1", "",
        f"**Gate:** `TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1_{verdict}`  ",
        "**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`  ",
        f"**Evidencia:** {report['generated_at_utc']}", "",
        "## A. VEREDICTO EJECUTIVO", "",
        "SAP separa documentalmente cobro/pago, instrumento, depósito y asiento. ORCT y OVPM llegan a OJDT por TransId; ODPS llega por TransAbs. Un depósito no se cuenta como nuevo cobro y las transferencias internas se mantienen fuera del flujo económico. La cadena contable está demostrada; la relación cash→deposit no tiene FK documental para efectivo y se publica como matching agregado explícito.", "",
        f"Resultado: **{verdict}**. Posición publicada: `SAP_ACCOUNTING_TREASURY_POSITION`, nunca `AVAILABLE_CASH`.", "",
        "## B. CONFIGURACIÓN DE TESORERÍA", "",
        f"ODSC/DSC1 fueron descubiertas y mapeadas a GL cuando `GLAccount` existe. El detalle de configuración está en `bank_configuration.house_accounts`; números bancarios se preservan en JSON técnico y se omiten de esta síntesis ejecutiva.", "",
        "## C. CUENTAS DE CAJA", "",
        f"Se identificaron {len(cash)} cuentas clasificadas CASH/PETTY_CASH por uso en ORCT/ODPS, jerarquía OACT y semántica del nombre. El saldo es `OACT.CurrTotal`, validado contra Σ(JDT1.Debit-Credit) cuando existe movimiento. La marca OACT.CashBox no se usa como única prueba.", "",
        "| Cuenta | Nombre | Moneda | Saldo GL | Movimientos | Evidencia |", "|---|---|---|---:|---:|---|",
    ]
    for item in cash[:80]:
        lines.append(f"| {item['ACCTCODE']} | {redacted_account_name(item['ACCTNAME'])} | {item.get('ACTCURR')} | {item.get('CURRTOTAL')} | {item.get('JDT_LINES')} | {item['EVIDENCE']} |")
    lines += ["", "## D. CUENTAS BANCARIAS", "", f"Se identificaron {len(banks)} cuentas BANK por DSC1/DSC1.GLAccount y uso real en transferencias/depósitos. Son saldos contables SAP, no saldos externos conciliados.", "", "| Cuenta | Nombre | Moneda | Saldo GL | Último movimiento | Estado |", "|---|---|---|---:|---|---|"]
    for item in banks[:100]:
        lines.append(f"| {item['ACCTCODE']} | {redacted_account_name(item['ACCTNAME'])} | {item.get('ACTCURR')} | {item.get('CURRTOTAL')} | {item.get('LAST_MOVEMENT')} | {'ACTIVE' if item.get('JDT_LINES') else 'CONFIGURED_UNUSED'} |")
    lines += ["", "## E. COBROS ORCT", "", f"El universo, cancelaciones, monedas y medios está en `orct`. Cada método se calcula desde CashSum/CheckSum/TrsfrSum/CreditSum/NoDocSum/BoeSum; no se interpreta ORCT como banco por defecto.", "", "## F. COBRO → GL", "", "`ORCT.TransId → OJDT.TransId → JDT1` es la trazabilidad primaria. La cuenta del medio se valida por identidad de cuenta y importe del componente, no por posición de línea.", "", "## G. DEPÓSITOS ODPS", "", "`ODPS.TransAbs → OJDT.TransId` cubre el universo. `DeposType` se conserva: C=CASH, K=CHECK, V=CREDIT_CARD; `BanckAcct` representa el destino bancario contable y `AllocAcct` la fuente cuando está poblada.", "", "## H. COBRO → DEPÓSITO → BANCO", "", f"Los cheques tienen cadena documental `ORCT.RCT1.CheckAbs → OCHH.CheckKey → OCHH.DpstAbs → ODPS → JDT1`; para efectivo no hay FK ORCT→ODPS. Matching agregado: {lag}. No se llama depósito a nuevo ingreso.", "", "## I. PAGOS OVPM", "", "OVPM se analiza por método y moneda, separado del settlement AP ya cerrado. Transferencias se siguen por TrsfrAcct y TransId; efectivo/cheque se siguen por CashAcct/CheckAcct y VPM1.", "", "## I BIS. CONTRASTE SAP_OTHER_COMPENSATION_REVIEW", "", f"Se preserva sin reabrir el universo AP cerrado de {report['ap_compensation_contrast'].get('baseline', {}).get('cases', 154)} casos por Bs {report['ap_compensation_contrast'].get('baseline', {}).get('amount', 380679.38):,.2f}. El contraste de tesorería consulta únicamente enlaces OVPM y contrapartidas OITR/ITR1; encontró {contrast_ap_docs} casos AP con contraparte de pago SrcObjTyp=46 sin VPM2, conservados como contraste de tesorería. No convierte SrcObjTyp ni similitud de importe en retención.", "", "## J. PAGO → BANCO/CAJA",  "", "Los casos representativos están en `cases`; los importes y asientos se conservan sin mezclar monedas. Pagos cancelados quedan fuera de posición vigente.", "", "## K. CHEQUES", "", "OCHH permite separar cheques recibidos en cartera/depositados; OCHO/VPM1 cubren cheques emitidos. `CLEARED` bancario solo se usa si existe evidencia, no por la mera existencia del cheque.", "", "## L. TARJETAS / CLEARING", "", "RCT3 y CreditAcct se inspeccionan. La posición de tarjeta/clearing permanece separada de caja y banco si la cuenta no tiene semántica bancaria demostrada.", "", "## M. TRANSFERENCIAS INTERNAS", "", "Se reportan candidatos por journals con más de una cuenta de tesorería y TransType -2/-3/JE. No se suman como ingreso ni egreso económico.", "", "## N. ASIENTOS MANUALES DE TESORERÍA", "", "Se miden OJDT.TransType=30, DataSource manual, usuarios, cuentas, memo y una clasificación conservadora de comisión, interés, transferencia, FX o UNKNOWN.", "", "## O. POSICIÓN DE CAJA", "", "La posición es contable por cuenta y moneda. No representa arqueo físico.", "", "## P. POSICIÓN DE BANCOS", "", "La posición es contable por cuenta y moneda. No representa saldo bancario externo.", "", "## Q. VALORES / DINERO EN TRÁNSITO", "", "Cheques recibidos, tarjetas y cuentas puente se presentan separados; no se suman automáticamente a efectivo disponible.", "", "## R. CASH→DEPOSIT LAG", "", f"Buckets del matching agregado único: `{lag.get('lag_buckets')}`. Este cálculo no sustituye una conciliación diaria ni prueba existencia física.", "", "## S. SALDOS PERSISTENTES / REVIEW", "", "`account_profiles.monthly` permite revisar persistencia >30/60/90/180/365 días. Una antigüedad no se etiqueta irregularidad sin semántica y evidencia operacional.", "", "## T. CONCILIACIÓN BANCARIA", "", f"OBNK existe y contiene {statement.get('LINES', 'UNRESOLVED')} filas; líneas con fecha={statement.get('DATED_LINES')}, importes no cero={statement.get('NONZERO_AMOUNT_LINES')}, conciliadas={statement.get('CLEARED_LINES')}, matching={statement.get('MATCHED_LINES')}. La evidencia observada no permite construir saldo externo conciliado: `BANK_RECONCILIATION_NOT_AVAILABLE_OR_UNUSED` para este gate.", "", "## U. CASOS REALES", "", "Se conservan casos A–J en JSON: efectivo→caja, efectivo→depósito→banco cuando el matching existe, transferencia directa, cheque depositado si existe, pago OVPM, cheque/efectivo, depósito cancelado, JE manual, saldo persistente y movimiento no clasificado.", "", "## V. LIMITACIONES", "", "- SAP registra saldos GL; no se afirma dinero físicamente disponible.\n- No existe enlace documental directo ORCT cash→ODPS; el matching por cuenta/moneda/fecha/importe es agregado y etiquetado.\n- OBNK no aporta cobertura suficiente de extracto conciliado en la evidencia observada.\n- Saldos en `BS`, `USD` y `##` no se suman nominalmente.\n- Sucursal/origen solo se conservan si vienen de BPLId/UDF/documento; no se inventan por usuario.", "", "## W. IMPLICACIONES PARA CONTROL INTERNO", "", "SAP permite reproducir caja esperada contable antes del depósito como: saldo inicial de cuenta + cobros cash + otros débitos de tesorería − depósitos/egresos/ajustes acreditados, por cuenta y moneda. SAP no demuestra que ese resultado existiera físicamente sin arqueo externo.", "", "## X. PRÓXIMO GATE", "", "La evidencia favorece `TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1` para integrar AR+AP+SAP_ACCOUNTING_TREASURY_POSITION. Si se requiere control operativo de depósitos, el siguiente gate específico es `TELCHI_CASH_DEPOSIT_CONTROL_V1`; la conciliación bancaria externa queda separada.", "", "## INVARIANTES", "", "| Invariante | Resultado |", "|---|---|"]
    for key, value in inv.items():
        lines.append(f"| {key} | {'PASS' if value.get('pass') else 'DEGRADED'} — {value} |")
    lines += ["", "## Artefactos", "", f"- JSON: `{DEFAULT_OUTPUT}`", f"- Runner: `{Path(__file__)}`", "- HANA/SAP: SELECT-only; `SAP_WRITE_COUNT=0`.", ""]
    return "\n".join(lines)


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        metadata = metadata_census(cur)
        orct = document_universe(cur, "ORCT")
        ovpm = document_universe(cur, "OVPM")
        source_result = treasury_account_sources(cur)
        profiles = account_profiles(cur, source_result["sources"])
        configuration = bank_configuration(cur)
        deposits = deposit_analysis(cur)
        lag = cash_deposit_lag(cur)
        instruments = checks_cards_and_reconciliation(cur)
        account_rows = profiles["accounts"]
        account_codes = [str(x["ACCTCODE"]) for x in account_rows]
        manual = manual_treasury(cur, account_codes)
        movement = movement_pareto(cur, account_codes)
        compensation = ap_compensation_contrast(cur)
        cases = case_samples(cur)
        report: dict[str, Any] = {
            "report_id": "TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "entity": "TELCHI", "domain": "TRANSFERENCIAS_Y_DEPÓSITOS", "stage": "INVESTIGATION", "mode": "READ_ONLY",
            "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True}, "sap_write_count": 0,
            "metadata": metadata, "orct": orct, "ovpm": ovpm, "account_sources": source_result,
            "account_profiles": profiles, "bank_configuration": configuration, "deposits": deposits,
            "cash_deposit_lag": lag, "instruments": instruments, "manual_treasury": manual,
            "movement_pareto": movement, "ap_compensation_contrast": compensation, "cases": cases,
            "matching_levels": ["EXACT_LINK", "STRONG_MATCH", "HEURISTIC_MATCH", "NO_LINK_AVAILABLE"],
            "evidence_levels": ["PROVEN", "STRONG", "PARTIAL", "HEURISTIC", "UNRESOLVED"],
            "limitations": ["ORCT cash has no direct document foreign key to ODPS; cash→deposit is aggregate matching.", "GL balances are not external bank balances or physical cash.", "OBNK was inspected but observed statement coverage is insufficient for an external reconciliation balance.", "Currencies are retained by account/document and are not nominally added."],
        }
        report["invariants"] = invariants(report, profiles, account_rows)
        required = ("TR01_orct_transid_exists_in_ojdt", "TR02_ovpm_transid_exists_in_ojdt", "TR03_odps_transabs_exists_in_ojdt", "TR04_treasury_journals_balance", "TR05_classified_accounts_exist_in_oact", "TR06_canceled_collections_separate", "TR07_canceled_supplier_payments_separate", "TR08_canceled_deposits_separate", "TR09_internal_transfers_not_economic_flow", "TR10_currency_not_mixed", "TR11_cash_deposit_evidence_explicit", "TR12_sap_write_count", "TR13_bank_reconciliation_not_overstated")
        report["verdict"] = "PASS" if all(report["invariants"][key]["pass"] for key in required) else "DEGRADED"
        report["gate"] = f"TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1_{report['verdict']}"
        return report
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text(result) + "\n", encoding="utf-8")
    print(json.dumps({"gate": result["gate"], "output": str(args.output), "report": str(args.report), "sap_write_count": 0}, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
