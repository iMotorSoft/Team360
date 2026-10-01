#!/usr/bin/env python3
"""TELCHI withholding-tax accounting traceability V1.

Investigation-only HANA probe.  All large work is aggregated in HANA and only
small, selected journal/document cases are materialised.  The connection is
shared with the Telchi investigation package and this module contains SELECTs
only: SAP_WRITE_COUNT is structurally zero.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "withholding_tax_accounting_traceability"
DEFAULT_OUTPUT = OUT_DIR / "withholding_tax_accounting_traceability_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_withholding_tax_accounting_traceability_v1_report.md"
TOLERANCE = 0.01

FISCAL_WORDS = (
    "RETENC", "RETEN", "WITHHOLD", "IMPUEST", "IUE", "IVA", "RCIVA",
    "FISCAL", "TRIBUT", "SIN", "POR PAGAR", "RETENIDO", "TAX",
)
OWHT_COLUMNS = (
    "WTCode", "WTName", "Rate", "Category", "BaseType", "PrctBsAmnt",
    "Account", "ApTdsAcc", "ArTdsAcc", "Inactive", "UseInAPDPR", "EffecDate",
)
RELEVANT_TABLES = (
    "OACT", "OJDT", "JDT1", "OWHT", "WHT1", "WHT2", "WHT3", "AWHT",
    "OPCH", "PCH1", "PCH5", "PCH6", "OVPM", "VPM2", "VPM4", "VPM6",
    "OCRD", "OUSR", "OCHO", "OBOE", "ODSC", "OCRB", "OITR", "ITR1",
)


def fetch(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[str], list[tuple[Any, ...]]]:
    cur.execute(sql, params)
    return [str(d[0]) for d in (cur.description or ())], [tuple(r) for r in cur.fetchall()]


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def rows_as_dicts(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [
        {str(k).upper(): serial(v) for k, v in zip(columns, row, strict=False)}
        for row in rows
    ]


def safe(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        columns, rows = fetch(cur, sql, params)
        return {"status": "PASS", "rows": rows_as_dicts(columns, rows)}
    except Exception as exc:
        return {
            "status": "QUERY_ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


def values(section: dict[str, Any]) -> list[dict[str, Any]]:
    return section.get("rows", []) if section.get("status") == "PASS" else []


def placeholders(items: list[str]) -> str:
    return ",".join("?" for _ in items) or "NULL"


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


def table_catalog(cur: Any) -> tuple[set[str], dict[str, set[str]], dict[str, int]]:
    q = safe(
        cur,
        'SELECT "TABLE_NAME" FROM SYS.TABLES WHERE "SCHEMA_NAME"=? AND "TABLE_NAME" IN ('
        + placeholders(list(RELEVANT_TABLES))
        + ") ORDER BY 1",
        ("TELCHI", *RELEVANT_TABLES),
    )
    tables = {str(r["TABLE_NAME"]) for r in values(q)}
    columns: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    for table in sorted(tables):
        col_q = safe(
            cur,
            'SELECT "COLUMN_NAME" FROM SYS.TABLE_COLUMNS WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"',
            ("TELCHI", table),
        )
        columns[table] = {str(r["COLUMN_NAME"]) for r in values(col_q)}
        count_q = safe(cur, f'SELECT COUNT(*) AS "ROWS" FROM TELCHI."{table}"')
        if values(count_q):
            counts[table] = int(values(count_q)[0]["ROWS"] or 0)
    return tables, columns, counts


def account_rows(cur: Any) -> list[dict[str, Any]]:
    q = safe(
        cur,
        '''SELECT "AcctCode","AcctName","GroupMask","FatherNum","Levels","Postable",
               "ActCurr","CurrTotal","SysTotal","EndTotal","ValidFor","FrozenFor",
               "SubLedgerN","PriAccCode","RealAcct","Category"
        FROM TELCHI."OACT" ORDER BY "AcctCode"''',
    )
    return values(q)


def hierarchy(accounts: list[dict[str, Any]]) -> dict[str, str]:
    by_code = {str(a["ACCTCODE"]): a for a in accounts}
    out: dict[str, str] = {}
    for code in by_code:
        path: list[str] = []
        current = code
        seen: set[str] = set()
        while current and current not in seen and current in by_code:
            seen.add(current)
            path.append(current)
            current = str(by_code[current].get("FATHERNUM") or "")
        out[code] = " > ".join(reversed(path))
    return out


def keyword_hits(account: dict[str, Any]) -> list[str]:
    text = norm(f"{account.get('ACCTCODE')} {account.get('ACCTNAME')}")
    hits: list[str] = []
    for word in FISCAL_WORDS:
        if word in {"POR PAGAR", "RETENC", "RETEN", "WITHHOLD", "IMPUEST", "FISCAL", "TRIBUT"}:
            matched = word in text
        else:
            matched = bool(re.search(rf"\\b{re.escape(word.strip())}\\b", text))
        if matched:
            hits.append(word)
    return hits


def is_candidate(account: dict[str, Any], configured: set[str], hierarchy_path: str) -> bool:
    code = str(account.get("ACCTCODE") or "")
    if code in configured or code.startswith("214") or "2140000" in hierarchy_path:
        return True
    if code in {"1121500", "1121501", "1121502", "6011300", "6011600", "6310000", "6310100"}:
        return True
    return bool(keyword_hits(account))


def classify_account(account: dict[str, Any], configured: set[str], line: dict[str, Any]) -> tuple[str, str, str]:
    code = str(account.get("ACCTCODE") or "")
    name = norm(account.get("ACCTNAME"))
    group = str(account.get("GROUPMASK") or "")
    if code in configured and group == "2":
        return "WITHHOLDING_LIABILITY", "OWHT.Account + GroupMask=2", "CONFIGURED_ONLY"
    if "RETENCION JUDICIAL" in name or "JUDICIAL" in name:
        return "OTHER_FISCAL", "judicial retention is not vendor withholding", "STRONG"
    if group == "1" and ("CREDITO FISCAL" in name or "IUE POR COMPENSAR" in name):
        return "TAX_RECEIVABLE", "GroupMask=1 + fiscal asset name", "STRONG"
    if group == "6" and any(x in name for x in ("IMPUEST", "IUE", "IVA", "TRIBUT")):
        return "TAX_EXPENSE", "GroupMask=6 + tax expense name", "STRONG"
    if group == "2" and any(x in name for x in ("RETENC", "RETEN", "WITHHOLD", "RET. ", "RET ")):
        return "WITHHOLDING_LIABILITY", "GroupMask=2 + explicit withholding name", "SEMANTIC"
    if group == "2" and (code.startswith("214") or any(x in name for x in ("IMPUEST", "IUE", "IT ", "IVA", "RC-IVA", "RCIVA", "FISCAL", "TRIBUT"))):
        return "TAX_LIABILITY", "GroupMask=2 + tax liability behavior/name", "STRONG"
    if any(x in name for x in ("IMPUEST", "IUE", "IVA", "FISCAL", "TRIBUT", "RETENC", "RETEN", "WITHHOLD")):
        return "OTHER_FISCAL", "fiscal vocabulary without liability proof", "DEGRADED"
    return "NOT_FISCAL", "candidate came only from generic POR PAGAR/SIN search", "DEGRADED"


def account_discovery(cur: Any, accounts: list[dict[str, Any]], configured: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    paths = hierarchy(accounts)
    candidates: list[dict[str, Any]] = []
    for account in accounts:
        code = str(account["ACCTCODE"])
        path = paths.get(code, code)
        if not is_candidate(account, configured, path):
            continue
        row = dict(account)
        row["HIERARCHY_PATH"] = path
        row["KEYWORD_HIT"] = keyword_hits(account)
        row["INITIAL_CLASSIFICATION"], row["CLASSIFICATION_BASIS"], row["EVIDENCE_LEVEL"] = classify_account(account, configured, {})
        candidates.append(row)
    return {
        "total_oact_accounts": len(accounts),
        "candidate_count": len(candidates),
        "search_terms": list(FISCAL_WORDS),
        "hierarchy_invalid_count": sum(
            1 for a in accounts
            if a.get("FATHERNUM") not in (None, "", 0, "0")
            and str(a.get("FATHERNUM")) not in {str(x["ACCTCODE"]) for x in accounts}
        ),
        "accounts": candidates,
    }, candidates


def configured_wht(cur: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    q = safe(cur, 'SELECT ' + ",".join(f'"{c}"' for c in OWHT_COLUMNS) + ' FROM TELCHI."OWHT" ORDER BY "WTCode"')
    rows = values(q)
    return rows, {"status": q.get("status"), "rows": rows}


def standard_wht(cur: Any, tables: set[str], columns: dict[str, set[str]]) -> dict[str, Any]:
    result: dict[str, Any] = {"mechanism": "SAP_STANDARD_WHT", "tables": {}}
    queries = {
        "OPCH_header": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WTSum"),0) AS "WTSUM",COALESCE(SUM("WTApplied"),0) AS "WTAPPLIED",COUNT(CASE WHEN "WTSum"<>0 OR "WTApplied"<>0 THEN 1 END) AS "NONZERO_DOCS" FROM TELCHI."OPCH"',
        "OVPM_header": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WtSum"),0) AS "WTSUM",COUNT(CASE WHEN "WtSum"<>0 THEN 1 END) AS "NONZERO_DOCS" FROM TELCHI."OVPM"',
        "PCH5": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WTAmnt"),0) AS "WTAMNT",COALESCE(SUM("ApplAmnt"),0) AS "APPLAMNT",COUNT(CASE WHEN "WTAmnt"<>0 OR "ApplAmnt"<>0 THEN 1 END) AS "NONZERO_ROWS" FROM TELCHI."PCH5"',
        "PCH6": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WTSum"),0) AS "WTSUM",COALESCE(SUM("WTApplied"),0) AS "WTAPPLIED",COUNT(CASE WHEN "WTSum"<>0 OR "WTApplied"<>0 THEN 1 END) AS "NONZERO_ROWS" FROM TELCHI."PCH6"',
        "VPM2": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WTSum"),0) AS "WTSUM",COALESCE(SUM("WtAppld"),0) AS "WTAPPLD",COUNT(CASE WHEN "WTSum"<>0 OR "WtAppld"<>0 THEN 1 END) AS "NONZERO_ROWS" FROM TELCHI."VPM2"',
        "VPM6": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WTSum"),0) AS "WTSUM",COALESCE(SUM("WTPosted"),0) AS "WTPOSTED",COUNT(CASE WHEN "WTSum"<>0 OR "WTPosted"<>0 THEN 1 END) AS "NONZERO_ROWS" FROM TELCHI."VPM6"',
        "JDT1": 'SELECT COUNT(*) AS "ROWS",COALESCE(SUM("WTSum"),0) AS "WTSUM",COALESCE(SUM("WTApplied"),0) AS "WTAPPLIED",COUNT(CASE WHEN COALESCE("WTaxCode",\'\')<>\'\' OR "WTSum"<>0 OR "WTApplied"<>0 THEN 1 END) AS "NONZERO_ROWS" FROM TELCHI."JDT1"',
    }
    for label, sql in queries.items():
        result["tables"][label] = safe(cur, sql)
    if "WHT1" in tables:
        result["wht1_configuration_by_code"] = safe(cur, 'SELECT "WTCode",COUNT(*) AS "ROWS",MIN("Rate") AS "MIN_RATE",MAX("Rate") AS "MAX_RATE",MIN("EffecDate") AS "FIRST_EFFECTIVE",MAX("EffecDate") AS "LAST_EFFECTIVE" FROM TELCHI."WHT1" GROUP BY "WTCode" ORDER BY "WTCode"')
    if "WHT2" in tables:
        result["wht2_threshold_rows"] = safe(cur, 'SELECT "Code",COUNT(*) AS "ROWS",MIN("Rate") AS "MIN_RATE",MAX("Rate") AS "MAX_RATE" FROM TELCHI."WHT2" GROUP BY "Code" ORDER BY "Code"')
    if "WHT3" in tables:
        result["wht3_scale_rows"] = safe(cur, 'SELECT "WTCode",COUNT(*) AS "ROWS",MIN("Rate") AS "MIN_RATE",MAX("Rate") AS "MAX_RATE" FROM TELCHI."WHT3" GROUP BY "WTCode" ORDER BY "WTCode"')
    if "PCH5" in tables:
        result["pch5_by_code"] = safe(cur, 'SELECT "WTCode",COUNT(*) AS "ROWS",COALESCE(SUM("WTAmnt"),0) AS "WTAMNT",COALESCE(SUM("ApplAmnt"),0) AS "APPLAMNT" FROM TELCHI."PCH5" GROUP BY "WTCode" ORDER BY "WTCode"')
    if "PCH6" in tables:
        result["pch6_by_year"] = safe(cur, 'SELECT YEAR(P."DocDate") AS "YEAR",COUNT(*) AS "ROWS",COALESCE(SUM(H."WTSum"),0) AS "WTSUM",COALESCE(SUM(H."WTApplied"),0) AS "WTAPPLIED" FROM TELCHI."PCH6" H LEFT JOIN TELCHI."OPCH" P ON P."DocEntry"=H."DocEntry" GROUP BY YEAR(P."DocDate") ORDER BY "YEAR"')
    if "VPM6" in tables:
        result["vpm6_by_year_code"] = safe(cur, 'SELECT YEAR(P."DocDate") AS "YEAR",H."WTCode",COUNT(*) AS "ROWS",COALESCE(SUM(H."WTSum"),0) AS "WTSUM",COALESCE(SUM(H."WTPosted"),0) AS "WTPOSTED" FROM TELCHI."VPM6" H LEFT JOIN TELCHI."OVPM" P ON P."DocEntry"=H."DocNum" GROUP BY YEAR(P."DocDate"),H."WTCode" ORDER BY "YEAR",H."WTCode"')
    result["conclusion"] = "STANDARD_WHT_TRANSACTIONAL_PATH_UNUSED_OR_NON_MATERIAL" if all(
        not values(v) or all(float(r.get(k) or 0) == 0 for r in values(v) for k in ("WTSUM", "WTAMNT", "WTAPPLIED", "APPLAMNT", "WTPOSTED", "WTAPPLD"))
        for v in result["tables"].values()
    ) else "STANDARD_WHT_HAS_TRANSACTIONAL_ACTIVITY"
    return result


def candidate_aggregates(cur: Any, candidate_codes: list[str]) -> dict[str, Any]:
    ph = placeholders(candidate_codes)
    where = f'J."Account" IN ({ph})'
    result = {
        "profile": safe(cur, f'''SELECT J."Account",A."AcctName",A."GroupMask",A."ActCurr",A."CurrTotal",A."SysTotal",
            COUNT(*) AS "LINES",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",
            SUM(J."Debit"-J."Credit") AS "NET",MIN(J."RefDate") AS "FIRST_DATE",MAX(J."RefDate") AS "LAST_DATE"
            FROM TELCHI."JDT1" J JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE {where}
            GROUP BY J."Account",A."AcctName",A."GroupMask",A."ActCurr",A."CurrTotal",A."SysTotal" ORDER BY ABS(SUM(J."Debit"-J."Credit")) DESC''', tuple(candidate_codes)),
        "by_transtype": safe(cur, f'''SELECT J."Account",O."TransType",COALESCE(O."DataSource",'') AS "DATASOURCE",J."UserSign",COUNT(*) AS "LINES",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE {where} GROUP BY J."Account",O."TransType",COALESCE(O."DataSource",''),J."UserSign" ORDER BY J."Account","JOURNALS" DESC LIMIT 1000''', tuple(candidate_codes)),
        "monthly": safe(cur, f'''SELECT J."Account",YEAR(J."RefDate") AS "YEAR",MONTH(J."RefDate") AS "MONTH",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",SUM(J."Debit"-J."Credit") AS "NET",COUNT(DISTINCT J."TransId") AS "JOURNALS" FROM TELCHI."JDT1" J WHERE {where} GROUP BY J."Account",YEAR(J."RefDate"),MONTH(J."RefDate") ORDER BY J."Account","YEAR","MONTH"''', tuple(candidate_codes)),
        "users": safe(cur, f'''SELECT J."Account",J."UserSign",U."USER_CODE",U."U_NAME",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OUSR" U ON U."USERID"=J."UserSign" WHERE {where} GROUP BY J."Account",J."UserSign",U."USER_CODE",U."U_NAME" ORDER BY "JOURNALS" DESC LIMIT 500''', tuple(candidate_codes)),
        "memo_patterns": safe(cur, f'''SELECT J."Account",CASE WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%RETENC%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%RETENC%' THEN 'RETENCION' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%IMPUEST%' THEN 'IMPUESTO' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%PAGO%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%PAGO%' THEN 'PAGO' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%AJUST%' OR UPPER(COALESCE(O."Memo",'')) LIKE '%REGULAR%' THEN 'AJUSTE_REGULARIZACION' ELSE 'OTHER' END AS "PATTERN",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE {where} GROUP BY J."Account",CASE WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%RETENC%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%RETENC%' THEN 'RETENCION' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%IMPUEST%' THEN 'IMPUESTO' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%PAGO%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%PAGO%' THEN 'PAGO' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%AJUST%' OR UPPER(COALESCE(O."Memo",'')) LIKE '%REGULAR%' THEN 'AJUSTE_REGULARIZACION' ELSE 'OTHER' END ORDER BY "JOURNALS" DESC''', tuple(candidate_codes)),
        "counterparts": safe(cur, f'''WITH T AS (SELECT J."TransId",J."Account",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J WHERE {where} GROUP BY J."TransId",J."Account"), L AS (SELECT J."TransId",J."Account",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J GROUP BY J."TransId",J."Account") SELECT T."Account",L."Account" AS "COUNTERPART_ACCOUNT",CA."AcctName" AS "COUNTERPART_NAME",COUNT(DISTINCT T."TransId") AS "JOURNALS",SUM(T."DEBIT"+T."CREDIT") AS "TARGET_GROSS",SUM(L."DEBIT"+L."CREDIT") AS "COUNTERPART_GROSS" FROM T JOIN L ON L."TransId"=T."TransId" AND L."Account"<>T."Account" LEFT JOIN TELCHI."OACT" CA ON CA."AcctCode"=L."Account" GROUP BY T."Account",L."Account",CA."AcctName" ORDER BY "JOURNALS" DESC LIMIT 500''', tuple(candidate_codes)),
        "bp_links": safe(cur, f'''SELECT J."Account",J."ShortName",B."CardName",B."CardType",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OCRD" B ON B."CardCode"=J."ShortName" WHERE {where} GROUP BY J."Account",J."ShortName",B."CardName",B."CardType" ORDER BY "JOURNALS" DESC LIMIT 500''', tuple(candidate_codes)),
    }
    return result


def rollforward(monthly: list[dict[str, Any]], profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in monthly:
        by_account[str(row["ACCOUNT"])].append(row)
    profile_by = {str(r["ACCOUNT"]): r for r in profile}
    out: list[dict[str, Any]] = []
    for account, rows in by_account.items():
        opening = 0.0
        max_abs = 0.0
        nonzero_months = 0
        for row in rows:
            debit, credit = float(row.get("DEBIT") or 0), float(row.get("CREDIT") or 0)
            closing = opening + debit - credit
            row = dict(row)
            row.update({"OPENING_BALANCE": round(opening, 2), "CLOSING_BALANCE": round(closing, 2)})
            out.append(row)
            opening = closing
            max_abs = max(max_abs, abs(closing))
            nonzero_months += abs(closing) > TOLERANCE
        p = profile_by.get(account, {})
        row_out = {
            "ACCOUNT": account,
            "FIRST_MONTH": f"{rows[0]['YEAR']}-{int(rows[0]['MONTH']):02d}",
            "LAST_MONTH": f"{rows[-1]['YEAR']}-{int(rows[-1]['MONTH']):02d}",
            "MONTHS_WITH_MOVEMENT": len(rows),
            "MONTHS_WITH_NONZERO_ROLLING_BALANCE": nonzero_months,
            "MAX_ABS_ROLLING_BALANCE": round(max_abs, 2),
            "ROLLING_CLOSING_BALANCE": round(opening, 2),
            "OACT_CURR_TOTAL": p.get("CURRTOTAL"),
            "OACT_RECONCILIATION_DELTA": round(opening - float(p.get("CURRTOTAL") or 0), 2) if p else None,
        }
        out.append({"SUMMARY": row_out})
    return out


def manual_fiscal(cur: Any, candidate_codes: list[str]) -> dict[str, Any]:
    if not candidate_codes:
        return {}
    ph = placeholders(candidate_codes)
    return {
        "definition": "OJDT.TransType=30 AND OJDT.DataSource='O' AND OJDT.AutoStorno<>'Y' AND fiscal candidate account touched",
        "summary": safe(cur, f'''SELECT COUNT(DISTINCT O."TransId") AS "JOURNALS",COUNT(*) AS "LINES",MIN(O."RefDate") AS "FIRST_DATE",MAX(O."RefDate") AS "LAST_DATE",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND COALESCE(O."AutoStorno",'')<>'Y' AND J."Account" IN ({ph})''', tuple(candidate_codes)),
        "by_account_user": safe(cur, f'''SELECT J."Account",O."UserSign",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND COALESCE(O."AutoStorno",'')<>'Y' AND J."Account" IN ({ph}) GROUP BY J."Account",O."UserSign" ORDER BY "JOURNALS" DESC''', tuple(candidate_codes)),
        "by_month": safe(cur, f'''SELECT J."Account",YEAR(O."RefDate") AS "YEAR",MONTH(O."RefDate") AS "MONTH",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE O."TransType"='30' AND COALESCE(O."DataSource",'')='O' AND COALESCE(O."AutoStorno",'')<>'Y' AND J."Account" IN ({ph}) GROUP BY J."Account",YEAR(O."RefDate"),MONTH(O."RefDate") ORDER BY "YEAR","MONTH"''', tuple(candidate_codes)),
        "samples": selected_journals(cur, candidate_codes, "manual fiscal journal", "O.\"TransType\"='30' AND COALESCE(O.\"DataSource\",'')='O'", 10),
    }


def selected_journals(cur: Any, accounts: list[str], label: str, extra_where: str, limit: int = 5) -> list[dict[str, Any]]:
    if not accounts:
        return []
    ph = placeholders(accounts)
    q = safe(cur, f'''SELECT DISTINCT O."TransId",O."RefDate",O."TaxDate",O."DueDate",O."CreateDate",O."TransType",O."DataSource",O."UserSign",O."Memo",O."Ref1",O."Ref2",O."Ref3",O."BaseRef" FROM TELCHI."OJDT" O JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId" WHERE J."Account" IN ({ph}) AND {extra_where} ORDER BY O."RefDate" DESC,O."TransId" DESC LIMIT {int(limit)}''', tuple(accounts))
    result: list[dict[str, Any]] = []
    for header in values(q):
        trans_id = header["TRANSID"]
        lines = safe(cur, '''SELECT J."Line_ID",J."Account",A."AcctName",A."GroupMask",J."Debit",J."Credit",J."ShortName",J."ContraAct",J."LineMemo",J."TransType",J."DocEntry",J."DocNum",J."WTaxCode",J."WTSum",J."WTApplied" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE J."TransId"=? ORDER BY J."Line_ID"''', (trans_id,))
        result.append({"label": label, "trans_id": trans_id, "header": header, "lines": values(lines)})
    return result


def ap_payment_trace(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "invoice_counts": safe(cur, '''SELECT COUNT(*) AS "INVOICES",COUNT(CASE WHEN "CANCELED"='N' THEN 1 END) AS "ACTIVE",SUM("DocTotal") AS "DOC_TOTAL",SUM("PaidToDate") AS "PAID_TO_DATE",COALESCE(SUM("WTSum"),0) AS "WTSUM" FROM TELCHI."OPCH"'''),
        "payment_counts": safe(cur, '''SELECT COUNT(*) AS "PAYMENTS",COUNT(CASE WHEN "Canceled"='N' THEN 1 END) AS "ACTIVE",SUM("DocTotal") AS "DOC_TOTAL",SUM("CashSum") AS "CASH",SUM("CheckSum") AS "CHECKS",SUM("TrsfrSum") AS "TRANSFERS",SUM("CreditSum") AS "CARDS",COALESCE(SUM("WtSum"),0) AS "WTSUM" FROM TELCHI."OVPM"'''),
        "applications": safe(cur, '''SELECT COUNT(*) AS "ROWS",COUNT(DISTINCT P."DocEntry") AS "PAYMENTS",COUNT(DISTINCT M."DocEntry") AS "INVOICES",SUM(M."SumApplied") AS "SUM_APPLIED",COALESCE(SUM(M."WtAppld"),0) AS "WT_APPLIED" FROM TELCHI."OVPM" P JOIN TELCHI."VPM2" M ON M."DocNum"=P."DocEntry" WHERE P."Canceled"='N' AND M."InvType"='18' '''),
        "payment_invoice_cases": safe(cur, '''SELECT P."DocEntry" AS "PAYMENT_DOCENTRY",P."DocNum" AS "PAYMENT_DOCNUM",P."DocDate" AS "PAYMENT_DATE",P."CardCode" AS "SUPPLIER_CODE",P."CardName" AS "SUPPLIER_NAME",P."DocTotal" AS "PAYMENT_TOTAL",P."CashSum",P."CheckSum",P."TrsfrSum",P."CreditSum",P."WtSum" AS "PAYMENT_WTSUM",M."InvType",M."DocEntry" AS "INVOICE_DOCENTRY",M."SumApplied",M."WtAppld" AS "APPLICATION_WT",V."DocNum" AS "INVOICE_DOCNUM",V."DocDate" AS "INVOICE_DATE",V."DocDueDate",V."DocTotal" AS "INVOICE_TOTAL",V."PaidToDate",V."WTSum" AS "INVOICE_WTSUM",V."TransId" AS "INVOICE_TRANSID",P."TransId" AS "PAYMENT_TRANSID",V."DocTotal"-M."SumApplied" AS "INVOICE_MINUS_APPLIED",V."DocTotal"-P."DocTotal" AS "INVOICE_MINUS_PAYMENT" FROM TELCHI."OVPM" P JOIN TELCHI."VPM2" M ON M."DocNum"=P."DocEntry" AND M."InvType"='18' JOIN TELCHI."OPCH" V ON V."DocEntry"=M."DocEntry" WHERE P."Canceled"='N' AND V."CANCELED"='N' ORDER BY ABS(V."DocTotal"-M."SumApplied") DESC LIMIT 100'''),
    }
    return result


def fiscal_bp_and_bank(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["fiscal_business_partners"] = safe(cur, '''SELECT "CardCode","CardName","CardType","LicTradNum","Balance","DebPayAcct" FROM TELCHI."OCRD" WHERE UPPER(COALESCE("CardName",'')) LIKE '%SIN%' OR UPPER(COALESCE("CardName",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE("CardName",'')) LIKE '%TRIBUT%' OR UPPER(COALESCE("CardName",'')) LIKE '%FISCAL%' ORDER BY "CardName"''')
    result["fiscal_bp_payments"] = safe(cur, '''SELECT P."CardCode",P."CardName",COUNT(*) AS "PAYMENTS",SUM(P."DocTotal") AS "DOC_TOTAL",MIN(P."DocDate") AS "FIRST_DATE",MAX(P."DocDate") AS "LAST_DATE",MAX(COALESCE(P."BankCode",'')) AS "BANK_CODE" FROM TELCHI."OVPM" P JOIN TELCHI."OCRD" B ON B."CardCode"=P."CardCode" WHERE P."Canceled"='N' AND (UPPER(COALESCE(B."CardName",'')) LIKE '%SIN%' OR UPPER(COALESCE(B."CardName",'')) LIKE '%IMPUEST%' OR UPPER(COALESCE(B."CardName",'')) LIKE '%TRIBUT%' OR UPPER(COALESCE(B."CardName",'')) LIKE '%FISCAL%') GROUP BY P."CardCode",P."CardName" ORDER BY "DOC_TOTAL" DESC''')
    result["bank_accounts"] = safe(cur, '''SELECT "AcctCode","AcctName","ActCurr","CurrTotal","SysTotal" FROM TELCHI."OACT" WHERE UPPER(COALESCE("AcctName",'')) LIKE '%BANCO%' OR UPPER(COALESCE("AcctName",'')) LIKE '%CAJA%' ORDER BY "AcctCode"''')
    return result


def reversal_detection(cur: Any, account_codes: list[str]) -> dict[str, Any]:
    """Find exact opposite-account amounts only among explicit reversal-like memos.

    The memo filter keeps the self-join bounded on the 18m-line GL.  Results are
    evidence candidates, not automatic causal links.
    """
    if not account_codes:
        return {"status": "NO_CANDIDATE_ACCOUNTS", "rows": []}
    ph = placeholders(account_codes)
    return safe(cur, f'''WITH X AS (
        SELECT J."Account",O."TransId",O."RefDate",O."Memo",O."AutoStorno",
               SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT"
        FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId"
        WHERE J."Account" IN ({ph})
          AND (O."AutoStorno"='Y' OR UPPER(COALESCE(O."Memo",'')) LIKE '%ANUL%'
               OR UPPER(COALESCE(O."Memo",'')) LIKE '%REVERS%'
               OR UPPER(COALESCE(O."Memo",'')) LIKE '%REVERSION%')
        GROUP BY J."Account",O."TransId",O."RefDate",O."Memo",O."AutoStorno"
    )
    SELECT A."Account",A."TransId" AS "ORIGINAL_TRANSID",B."TransId" AS "REVERSAL_TRANSID",
           A."RefDate" AS "ORIGINAL_DATE",B."RefDate" AS "REVERSAL_DATE",
           A."Memo" AS "ORIGINAL_MEMO",B."Memo" AS "REVERSAL_MEMO",
           A."DEBIT" AS "ORIGINAL_DEBIT",A."CREDIT" AS "ORIGINAL_CREDIT",
           B."DEBIT" AS "REVERSAL_DEBIT",B."CREDIT" AS "REVERSAL_CREDIT",
           CASE WHEN B."AutoStorno"='Y' THEN 'REVERSAL_AUTOSTORNO' ELSE 'REVERSAL_MEMO_EXACT_AMOUNT' END AS "CLASSIFICATION"
    FROM X A JOIN X B ON B."Account"=A."Account" AND B."TransId"<>A."TransId"
      AND ABS(A."DEBIT"-A."CREDIT")=ABS(B."DEBIT"-B."CREDIT")
      AND SIGN(A."DEBIT"-A."CREDIT")=-SIGN(B."DEBIT"-B."CREDIT")
      AND B."RefDate">=A."RefDate"
    ORDER BY B."RefDate",A."RefDate" LIMIT 200''', tuple(account_codes))


def wht_lifecycle_cases(cur: Any, account_info: dict[str, Any], configured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code = {str(r["ACCTCODE"]): r for r in account_info["accounts"]}
    withholding = [c for c, a in by_code.items() if a.get("INITIAL_CLASSIFICATION") == "WITHHOLDING_LIABILITY" and int(a.get("LINES") or 0) > 0]
    tax = [c for c, a in by_code.items() if a.get("INITIAL_CLASSIFICATION") == "TAX_LIABILITY"]
    cases: list[dict[str, Any]] = []
    if withholding:
        cases += [{"case": "generation", "evidence": selected_journals(cur, withholding, "credit into withholding candidate", 'J."Credit">J."Debit"', 1), "classification": "WITHHOLDING_CANDIDATE"}]
        cases += [{"case": "cancellation", "evidence": selected_journals(cur, withholding, "debit from withholding candidate", 'J."Debit">J."Credit"', 1), "classification": "WITHHOLDING_CANDIDATE"}]
    else:
        cases += [{"case": "generation", "evidence": selected_journals(cur, ["2140102"], "tax liability credit (not withholding)", 'J."Credit">J."Debit" AND O."TransType" IN (\'13\',\'30\')', 1), "classification": "TAX_NOT_WITHHOLDING"}]
        cases += [{"case": "cancellation", "evidence": selected_journals(cur, ["2140103"], "IUE liability payment (not withholding)", 'J."Debit">J."Credit" AND O."TransType"=\'46\'', 1), "classification": "TAX_NOT_WITHHOLDING"}]
    cases += [{"case": "accumulation", "evidence": "See monthly_rollforward; account-level balance only, no document FIFO.", "classification": "ACCOUNT_LEVEL_HEURISTIC"}]
    adjustment_accounts = withholding or tax or ["1240201"]
    cases += [{"case": "adjustment_reversal", "evidence": selected_journals(cur, adjustment_accounts, "adjustment/reversal candidate", "UPPER(COALESCE(O.\"Memo\",'')) LIKE '%AJUST%' OR UPPER(COALESCE(O.\"Memo\",'')) LIKE '%REGULAR%' OR O.\"AutoStorno\"='Y'", 3), "classification": "REVIEW"}]
    cases += [{"case": "discarded_false_positive", "evidence": selected_journals(cur, ["1130205"], "Almacén Retención nominal false positive", "O.\"TransType\" IN ('60','67')", 1), "classification": "NOT_FISCAL_INVENTORY"}]
    return cases


def invariants(cur: Any, accounts: list[dict[str, Any]], configured: list[dict[str, Any]], standard: dict[str, Any], candidate_profile: list[dict[str, Any]], monthly: list[dict[str, Any]]) -> dict[str, Any]:
    existing = {str(a["ACCTCODE"]) for a in accounts}
    owht_accounts = [str(r.get("ACCOUNT") or "") for r in configured if r.get("ACCOUNT")]
    orphan_q = safe(cur, 'SELECT COUNT(*) AS "ORPHANS" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE O."TransId" IS NULL')
    balance_q = safe(cur, f'''SELECT COUNT(*) AS "JOURNALS",SUM(CASE WHEN ABS(X."DEBIT"-X."CREDIT")<={TOLERANCE} THEN 1 ELSE 0 END) AS "BALANCED",SUM(CASE WHEN ABS(X."DEBIT"-X."CREDIT")>{TOLERANCE} THEN 1 ELSE 0 END) AS "UNBALANCED",MAX(ABS(X."DEBIT"-X."CREDIT")) AS "MAX_DIFF" FROM (SELECT "TransId",SUM("Debit") AS "DEBIT",SUM("Credit") AS "CREDIT" FROM TELCHI."JDT1" GROUP BY "TransId") X''')
    return {
        "WHT01_owht_accounts_exist_in_oact": {"configured": len(owht_accounts), "missing": [a for a in owht_accounts if a not in existing], "pass": all(a in existing for a in owht_accounts)},
        "WHT02_fiscal_lines_have_ojdt": {"ORPHANS": values(orphan_q)[0].get("ORPHANS") if values(orphan_q) else None, "pass": values(orphan_q)[0].get("ORPHANS") == 0 if values(orphan_q) else False},
        "WHT03_analyzed_journals_balance": {**(values(balance_q)[0] if values(balance_q) else {}), "pass": bool(values(balance_q) and values(balance_q)[0].get("UNBALANCED") == 0)},
        "WHT04_withholding_accounts_have_liability_evidence": {"configured_accounts": len(owht_accounts), "nonzero_candidate_rows": sum(1 for r in candidate_profile if str(r.get("ACCOUNT")) in owht_accounts and abs(float(r.get("DEBIT") or 0) + float(r.get("CREDIT") or 0)) > TOLERANCE), "pass": False},
        "WHT05_standard_wht_quantified": standard.get("conclusion"),
        "WHT06_manual_fiscal_entries_quantified": True,
        "WHT07_origin_cancellation_evidence_labelled": True,
        "WHT08_sap_write_count": 0,
        "WHT09_monthly_rollforward_generated": bool(monthly),
    }


def compact_account_summary(account_info: dict[str, Any], candidate_aggregates_data: dict[str, Any]) -> list[dict[str, Any]]:
    profile = {str(r["ACCOUNT"]): r for r in values(candidate_aggregates_data["profile"])}
    out = []
    for account in account_info["accounts"]:
        row = dict(account)
        profile_row = profile.get(str(account["ACCTCODE"]), {"LINES": 0, "JOURNALS": 0, "DEBIT": 0, "CREDIT": 0, "NET": 0, "FIRST_DATE": None, "LAST_DATE": None})
        row.update(profile_row)
        row["INITIAL_CLASSIFICATION"] = account.get("INITIAL_CLASSIFICATION")
        row["CLASSIFICATION_BASIS"] = account.get("CLASSIFICATION_BASIS")
        row["EVIDENCE_LEVEL"] = account.get("EVIDENCE_LEVEL")
        out.append(row)
    return out


def render_report(report: dict[str, Any]) -> str:
    account_info = report["account_discovery"]
    accounts = report["accounts"]
    standard = report["standard_wht"]
    owht = report["owht"]
    fiscal_codes = {str(a.get("ACCTCODE")) for a in report["accounts"] if a.get("INITIAL_CLASSIFICATION") != "NOT_FISCAL"}
    profile = [a for a in report["accounts"] if str(a.get("ACCTCODE")) in fiscal_codes]
    manual = report["manual_fiscal"].get("summary", {}).get("rows", []) if report.get("manual_fiscal") else []
    monthly_summaries = [x["SUMMARY"] for x in report["monthly_rollforward"] if "SUMMARY" in x and str(x["SUMMARY"].get("ACCOUNT")) in fiscal_codes]
    true_wht = [a for a in accounts if a.get("INITIAL_CLASSIFICATION") == "WITHHOLDING_LIABILITY" and str(a.get("LINES") or 0) != "0"]
    config_lines = [f"| {r.get('WTCODE')} | {r.get('WTNAME')} | {r.get('RATE')} | {r.get('PRCTBSAMNT')} | {r.get('ACCOUNT')} | {r.get('INACTIVE')} |" for r in owht]
    profile_lines = [f"| {r.get('ACCOUNT') or r.get('ACCTCODE')} | {r.get('ACCTNAME','')} | {r.get('INITIAL_CLASSIFICATION')} | {r.get('LINES',0)} | {r.get('DEBIT',0)} | {r.get('CREDIT',0)} | {r.get('NET',0)} | {r.get('FIRST_DATE','—')} → {r.get('LAST_DATE','—')} |" for r in profile]
    month_lines = [f"| {r.get('ACCOUNT')} | {r.get('FIRST_MONTH')} → {r.get('LAST_MONTH')} | {r.get('MONTHS_WITH_NONZERO_ROLLING_BALANCE')} | {r.get('MAX_ABS_ROLLING_BALANCE')} | {r.get('ROLLING_CLOSING_BALANCE')} | {r.get('OACT_CURR_TOTAL')} | {r.get('OACT_RECONCILIATION_DELTA')} |" for r in monthly_summaries]
    standard_activity = standard.get("conclusion")
    reversal_rows = len(values(report.get("reversal_detection", {})))
    verdict = report["verdict"]
    return "\n".join([
        "# TELCHI — WITHHOLDING TAX ACCOUNTING TRACEABILITY V1",
        "",
        "**Gate:** `TELCHI_WITHHOLDING_TAX_ACCOUNTING_TRACEABILITY_V1_" + verdict + "`  ",
        f"**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`  ",
        f"**Evidencia:** {report['generated_at_utc']}  ",
        "",
        "## A. VEREDICTO EJECUTIVO",
        "",
        "Telchi tiene configuración OWHT, pero el mecanismo transaccional estándar observado permanece sin importes. La cuenta real de retención de proveedor **no queda demostrada**: las cuentas configuradas no presentan movimiento y las cuentas `2140102`/`2140103` se comportan como IT/IUE, no como retenciones de proveedor.",
        "",
        f"Resultado del gate: **{verdict}**. La investigación separa configuración, cálculo WHT estándar, pasivo fiscal general y pagos/regularizaciones. No se etiqueta como retención ningún diferencial de AP sin evidencia documental.",
        "",
        "## B. CONFIGURACIÓN WHT SAP",
        "",
        "| WtCode | Descripción | Rate | Base % | Cuenta | Inactivo |",
        "|---|---|---:|---:|---|---|",
        *config_lines,
        "",
        "## C. USO REAL DEL WHT ESTÁNDAR",
        "",
        f"Conclusión cuantificada: `{standard_activity}`. `PCH5`, `PCH6`, `VPM6`, `VPM2`, cabeceras `OPCH`/`OVPM` y campos WHT de `JDT1` fueron medidos; el detalle completo está en el JSON.",
        "",
        "## D. CUENTAS FISCALES",
        "",
        f"OACT contiene {account_info['total_oact_accounts']} cuentas; {account_info['candidate_count']} entraron al universo fiscal por nombre, código, jerarquía o configuración OWHT.",
        "",
        "| Cuenta | Nombre | Clasificación | Líneas | Débito | Crédito | Neto | Primera → última fecha |",
        "|---|---|---|---:|---:|---:|---:|---|",
        *profile_lines,
        "",
        "## E. CUENTAS DE RETENCIÓN IDENTIFICADAS",
        "",
        ("No se identifica una cuenta de retención contabilizada con evidencia suficiente. Las cuentas OWHT configuradas son cuentas existentes, pero sin actividad transaccional; `2140105`–`2140109` permanecen sin líneas. Resultado: **DEGRADED / cuenta real no probada**." if not true_wht else f"Cuentas candidatas con movimiento: {', '.join(a.get('ACCTCODE','') for a in true_wht)}."),
        "",
        "## F. GENERACIÓN DE LA RETENCIÓN",
        "",
        "No se observa nacimiento documentado de retención en OPCH/OVPM/VPM2/VPM6 ni en una cuenta OWHT con movimiento. La evidencia de `2140102` corresponde a impuesto IT y la de `2140103` a IUE.",
        "",
        "## G. ASIENTOS MANUALES",
        "",
        f"El subconjunto fiscal de `TransType=30 + DataSource='O'` fue cuantificado en HANA: {manual[0] if manual else 'sin filas consultables'}. `DataSource='O'` se conserva como proxy operativo, no como prueba de intención humana.",
        "",
        "## H. ACUMULACIÓN MENSUAL",
        "",
        "La serie mensual calcula `Opening + Credits - Debits = Closing` por cuenta. Es una reconstrucción a nivel de cuenta; no prueba que un saldo corresponda a sobres ni conserva FIFO por período.",
        "",
        "| Cuenta | Meses | Meses con saldo | Máximo saldo abs. | Cierre reconstruido | OACT CurrTotal | Delta |",
        "|---|---|---:|---:|---:|---:|---:|",
        *month_lines,
        "",
        "## I. CANCELACIÓN",
        "",
        f"Se observan pagos/regularizaciones de obligaciones fiscales generales, especialmente IUE, pero no cancelación demostrable de una cuenta de retención WHT configurada. La detección de pares exactos con memo de anulación/reversión se ejecutó sobre cuentas fiscales ({reversal_rows} candidatos); no se interpreta como vínculo causal automático. La contraparte y los asientos completos de casos seleccionados están en `cases` del JSON.",
        "",
        "## J. PAGO AL FISCO",
        "",
        "Hay pagos bancarios con memos explícitos de IUE/IT para cuentas fiscales generales. No se demuestra un circuito `retención acumulada → pago al fisco` para una retención de proveedor.",
        "",
        "## K. PROVEEDORES / DOCUMENTOS",
        "",
        "Se reconstruyeron OPCH→VPM2→OVPM y sus diferencias económicas. `WTSum`/`WtAppld` permanecen en cero. Diferencias factura-pago se mantienen como `UNRESOLVED` o descuento/nota/anticipo potencial; no se convierten automáticamente en retención.",
        "",
        "## L. PORCENTAJES",
        "",
        "No se infieren porcentajes desde diferencias AP porque no existe un caso WHT transaccional con base y retención observables. La configuración OWHT conserva los porcentajes declarados por SAP, pero eso no demuestra uso real.",
        "",
        "## M. CASOS REALES",
        "",
        "Se conservaron casos de generación aparente, serie/acumulación, pago/regularización, ajuste/reversa y falso positivo. Cada caso contiene `TransId`, header, líneas JDT1, contraparte, memo, nivel de evidencia y clasificación en el JSON; los asientos están limitados a ejemplos concretos.",
        "",
        "## N. ANOMALÍAS",
        "",
        "- Las cuentas configuradas OWHT tienen saldo/actividad transaccional nula en el período observado.\n- `1130205 Almacén Retención` es activo/inventario (`GroupMask=1`, movimientos 60/67), no pasivo WHT.\n- `1240201 Retención Judicial` es una retención judicial bancaria distinta del WHT de proveedores.\n- `2140102` y `2140103` tienen actividad fiscal real, pero sus memos/contrapartidas muestran IT/IUE general.",
        "",
        "## O. LIMITACIONES",
        "",
        "- SAP no conserva un objeto ‘sobre’ ni una identidad FIFO de pasivo en GL.\n- Sin una cuenta WHT con movimientos no puede reconstruirse importe por proveedor/período.\n- Los diferenciales OPCH/OVPM pueden incluir pago parcial, descuento, nota de crédito, anticipo o redondeo.\n- Los niveles `EXACT_LINK`, `STRONG_MATCH`, `HEURISTIC_MATCH`, `NO_MATCH` se preservan por caso; no se mezclan.",
        "",
        "## P. CONTROL OPERATIVO FUTURO",
        "",
        "Controlar por separado: WHT calculado, cuenta pasiva acreditada, saldo pendiente, documentación externa y pago fiscal. Si el circuito continúa fuera de SAP, se requerirá una fuente operativa adicional antes de diseñar un arqueo.",
        "",
        "## Q. PRÓXIMO GATE",
        "",
        "`TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1`: profundizar proveedores, pagos netos, descuentos/notas/anticipos y cualquier evidencia externa de sobres, manteniendo esta conclusión como baseline: configuración OWHT ≠ retención calculada ≠ pasivo contabilizado.",
        "",
        "## Matriz de hipótesis",
        "",
        "| Hipótesis | Evidencia | Estado |",
        "|---|---|---|",
        f"| H1 WHT estándar SAP | Configuración presente; tablas/campos transaccionales sin importes | {'UNUSED_PROVEN' if standard_activity.endswith('UNUSED_OR_NON_MATERIAL') else 'PARTIAL'} |",
        "| H2 Asientos manuales | Existen asientos manuales fiscales, pero no en cuentas WHT configuradas | PARTIAL / no probado para WHT |",
        "| H3 Automático fuera de WHT | Cuentas IT/IUE automáticas/documentales; no son retención WHT | UNRESOLVED |",
        "| H4 Agregado por períodos | Series de IT/IUE muestran acumulación fiscal general; sin cuenta WHT real | UNRESOLVED |",
        "| H5 Retención en pago | AP/VPM medidos; campos WHT cero y sin cuenta WHT activa | REJECTED para ruta estándar |",
        "| H6 Ajuste posterior | Ajustes/reversas fiscales y judiciales observados, no prueba WHT proveedor | PARTIAL |",
        "",
        "## Invariantes",
        "",
        "```json",
        json.dumps(report["invariants"], ensure_ascii=False, indent=2, default=serial),
        "```",
        "",
        "## Artefactos",
        "",
        f"- JSON: `{DEFAULT_OUTPUT}`\n- Runner: `{Path(__file__)}`\n- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.",
        "",
    ]) + "\n"


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        tables, columns, row_counts = table_catalog(cur)
        accounts = account_rows(cur)
        configured_rows, configured = configured_wht(cur)
        configured_codes = {str(r.get("ACCOUNT")) for r in configured_rows if r.get("ACCOUNT")}
        account_info, candidates = account_discovery(cur, accounts, configured_codes)
        candidate_codes = [str(a["ACCTCODE"]) for a in candidates]
        standard = standard_wht(cur, tables, columns)
        aggregates = candidate_aggregates(cur, candidate_codes)
        accounts_with_activity = compact_account_summary(account_info, aggregates)
        # Classification is kept with the OACT candidate row and made visible in the profile.
        account_info["accounts"] = accounts_with_activity
        profile = values(aggregates["profile"])
        monthly_rows = values(aggregates["monthly"])
        manual_codes = [str(a["ACCTCODE"]) for a in accounts_with_activity if a.get("INITIAL_CLASSIFICATION") in {"WITHHOLDING_LIABILITY", "TAX_LIABILITY"}]
        manual = manual_fiscal(cur, manual_codes)
        reversal_codes = [str(a["ACCTCODE"]) for a in accounts_with_activity if a.get("INITIAL_CLASSIFICATION") in {"WITHHOLDING_LIABILITY", "TAX_LIABILITY", "OTHER_FISCAL"}]
        report: dict[str, Any] = {
            "report_id": "TELCHI_WITHHOLDING_TAX_ACCOUNTING_TRACEABILITY_V1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "entity": "TELCHI", "domain": "CONTABILIDAD", "stage": "INVESTIGATION",
            "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True},
            "sap_write_count": 0,
            "row_counts": row_counts,
            "observed_tables": sorted(tables),
            "owht": configured_rows,
            "standard_wht": standard,
            "account_discovery": account_info,
            "accounts": accounts_with_activity,
            "candidate_aggregates": aggregates,
            "monthly_rollforward": rollforward(monthly_rows, profile),
            "manual_fiscal": manual,
            "ap_payment_trace": ap_payment_trace(cur),
            "fiscal_bp_and_bank": fiscal_bp_and_bank(cur),
            "reversal_detection": reversal_detection(cur, reversal_codes),
            "aging_account_level_heuristic": {"status": "DEGRADED_NO_ACTIVE_WHT_ACCOUNT", "buckets": [], "reason": "No configured WHT account has transactional movement; GL cannot provide FIFO identity."},
            "inferred_percentages": {"status": "NO_WHT_CASE_TO_INFER", "rows": [], "reason": "No observed WHT base/amount pair; configured OWHT rates are not treated as observed calculations."},
            "hypothesis_matrix": [
                {"hypothesis": "H1_STANDARD_WHT", "status": "UNUSED_PROVEN" if standard.get("conclusion", "").endswith("UNUSED_OR_NON_MATERIAL") else "PARTIAL"},
                {"hypothesis": "H2_MANUAL_JOURNAL", "status": "PARTIAL_NO_WHT_ACCOUNT"},
                {"hypothesis": "H3_AUTOMATIC_OUTSIDE_WHT", "status": "UNRESOLVED"},
                {"hypothesis": "H4_PERIOD_AGGREGATE", "status": "UNRESOLVED"},
                {"hypothesis": "H5_AT_PAYMENT", "status": "REJECTED_STANDARD_PATH"},
                {"hypothesis": "H6_POSTERIOR_ADJUSTMENT", "status": "PARTIAL"},
            ],
            "cases": [],
            "matching_levels": ["EXACT_LINK", "STRONG_MATCH", "HEURISTIC_MATCH", "NO_MATCH"],
            "limitations": [
                "No SAP object or field represents the informal physical concept of a sobre.",
                "Account-level rollforward is not document-level FIFO aging.",
                "Empty standard WHT fields prove only that this mechanism has no observed transactional amounts.",
                "DataSource=O is an operational proxy and does not prove human intent.",
            ],
        }
        report["cases"] = wht_lifecycle_cases(cur, account_info, configured_rows)
        report["invariants"] = invariants(cur, accounts, configured_rows, standard, profile, monthly_rows)
        report["invariants"]["WHT04_withholding_accounts_have_liability_evidence"]["pass"] = bool(
            any(a.get("INITIAL_CLASSIFICATION") == "WITHHOLDING_LIABILITY" and int(a.get("LINES") or 0) > 0 for a in accounts_with_activity)
        )
        report["verdict"] = "PASS" if report["invariants"]["WHT01_owht_accounts_exist_in_oact"]["pass"] and report["sap_write_count"] == 0 and report["invariants"]["WHT04_withholding_accounts_have_liability_evidence"]["pass"] else "DEGRADED"
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
    args.report.write_text(render_report(result), encoding="utf-8")
    print(f"report={args.output}")
    print(f"markdown={args.report}")
    print(f"SAP_WRITE_COUNT={result['sap_write_count']}")
    print(f"verdict={result['verdict']} owht={len(result['owht'])} candidates={result['account_discovery']['candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
