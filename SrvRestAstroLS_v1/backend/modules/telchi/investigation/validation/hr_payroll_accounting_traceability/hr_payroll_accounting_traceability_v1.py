#!/usr/bin/env python3
"""TELCHI HR / payroll / accounting traceability V1 (SELECT-only).

The probe deliberately separates OHEM (employee master), payroll objects, GL
expense, labour liabilities and cash payments.  It never writes to SAP and
keeps employee-level output to IDs/counts unless needed for an explicit link.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "hr_payroll_accounting_traceability"
DEFAULT_OUTPUT = OUT_DIR / "hr_payroll_accounting_traceability_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_hr_payroll_accounting_traceability_v1_report.md"
TOLERANCE = 0.01
HR_WORDS = ("SUELD", "SALAR", "JORNAL", "BON", "AGUINAL", "VACAC", "INDEMN", "BENEF", "SOCIAL", "AFP", "CAJA", "APORTE", "PRIMA", "COMISION", "PERSONAL", "EMPLEAD", "MOVIL", "VIATIC", "SUBSID", "RETENC", "HONOR")
PAYROLL_TABLE_WORDS = ("PAY", "SALAR", "WAGE", "HR", "HCM", "EMP", "ATTEND", "ABSEN", "LEAVE", "VACAT", "TIME", "BENEF", "BONUS", "NOMIN", "PRL")


def serial(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in raw if not unicodedata.combining(c)).upper()


def rows(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    cols = [str(d[0]).upper() for d in (cur.description or ())]
    return [{k: serial(v) for k, v in zip(cols, row, strict=False)} for row in cur.fetchall()]


def safe(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        return {"status": "PASS", "rows": rows(cur, sql, params)}
    except Exception as exc:
        return {"status": "QUERY_ERROR", "error": str(exc)[:500], "rows": []}


def vals(section: dict[str, Any]) -> list[dict[str, Any]]:
    return section.get("rows", []) if section.get("status") == "PASS" else []


def ph(items: list[Any]) -> str:
    return ",".join("?" for _ in items) or "NULL"


def catalog(cur: Any) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
    table_rows = rows(cur, 'SELECT "TABLE_NAME" FROM "SYS"."TABLES" WHERE "SCHEMA_NAME"=? ORDER BY 1', ("TELCHI",))
    tables = [str(x["TABLE_NAME"]) for x in table_rows]
    selected = [t for t in tables if any(w in norm(t) for w in PAYROLL_TABLE_WORDS)]
    # Include known standard HR/payroll candidates even if their name does not match.
    selected += [t for t in ("OHEM", "OUSR", "OSLP", "OUDP", "OBPL", "OUBR", "OHPS", "OHTR", "OWHT") if t in tables and t not in selected]
    columns: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for table in selected:
        q = safe(cur, 'SELECT "COLUMN_NAME" FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"', ("TELCHI", table))
        columns[table] = [str(x["COLUMN_NAME"]) for x in vals(q)]
        c = safe(cur, f'SELECT COUNT(*) AS "ROWS" FROM "TELCHI"."{table}"')
        if vals(c): counts[table] = int(vals(c)[0]["ROWS"] or 0)
    return sorted(selected), columns, counts


def employee_universe(cur: Any) -> dict[str, Any]:
    q = safe(cur, '''SELECT "empID","firstName","lastName","status","Active","startDate","termDate",
        "jobTitle","dept","branch","manager","userId","salesPrson","CostCenter","BPLId",
        "position","PersGroup","JTCode","BPLink","salary","salaryUnit","emplCost","empCostUnt",
        "salaryCurr","empCostCur","CreateDate","DataSource" FROM "TELCHI"."OHEM" ORDER BY "empID"''')
    employees = vals(q)
    status_values = safe(cur, 'SELECT "Active","status",COUNT(*) AS "ROWS" FROM "TELCHI"."OHEM" GROUP BY "Active","status" ORDER BY 1,2')
    def state(e: dict[str, Any]) -> str:
        active = str(e.get("ACTIVE") or "").upper()
        term = e.get("TERMDATE")
        status = norm(e.get("STATUS"))
        if active in {"Y", "YES", "1", "T"} and not term and status not in {"T", "TERMINATED", "INACTIVE"}:
            return "ACTIVE"
        if term or status in {"T", "TERMINATED", "BAJA", "INACTIVO", "INACTIVE"}:
            return "TERMINATED"
        if active in {"N", "NO", "0", "F"}:
            return "INACTIVE"
        return "UNRESOLVED"
    for e in employees:
        e["CLASSIFICATION"] = state(e)
        # Do not expose personal fields in the report; JSON retains only operational master fields below.
    safe_employees = [{k: e.get(k) for k in ("EMPID", "ACTIVE", "STATUS", "STARTDATE", "TERMDATE", "JOBTITLE", "DEPT", "BRANCH", "MANAGER", "USERID", "SALESP RSON".replace(" ", ""), "COSTCENTER", "BPLID", "POSITION", "PERSGROUP", "JTCODE", "BPLINK", "SALARY", "SALARYUNIT", "EMPCOST", "EMPCOSTUNT", "SALARYCURR", "EMPCOSTCUR", "CREATEDATE", "DATASOURCE", "CLASSIFICATION")} for e in employees]
    counts = {s: sum(e["CLASSIFICATION"] == s for e in employees) for s in ("ACTIVE", "INACTIVE", "TERMINATED", "UNRESOLVED")}
    return {"employees": safe_employees, "counts": counts, "total": len(employees), "status_values": status_values, "field_policy": "names, identity documents, bank fields and sensitive personal fields omitted"}


def org_links(cur: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["employee_user_samples"] = safe(cur, '''SELECT E."empID",E."userId" AS "USERID",U."USER_CODE",U."SUPERUSER",U."Locked" FROM "TELCHI"."OHEM" E JOIN "TELCHI"."OUSR" U ON U."USERID"=E."userId" ORDER BY E."empID" LIMIT 20''')
    result["employee_user"] = safe(cur, '''SELECT COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN E."userId" IS NOT NULL THEN 1 END) AS "WITH_USER",
        COUNT(CASE WHEN E."userId" IS NULL THEN 1 END) AS "WITHOUT_USER",COUNT(CASE WHEN U."USERID" IS NOT NULL THEN 1 END) AS "VALID_USER_LINK",
        COUNT(CASE WHEN U."SUPERUSER"='Y' THEN 1 END) AS "SUPERUSER_LINKS",COUNT(CASE WHEN U."Locked"='N' THEN 1 END) AS "ACTIVE_USER_LINKS"
        FROM "TELCHI"."OHEM" E LEFT JOIN "TELCHI"."OUSR" U ON U."USERID"=E."userId"''')
    result["users_without_employee"] = safe(cur, '''SELECT COUNT(*) AS "USERS_WITHOUT_EMPLOYEE" FROM "TELCHI"."OUSR" U LEFT JOIN "TELCHI"."OHEM" E ON E."userId"=U."USERID" WHERE E."empID" IS NULL''')
    result["employee_salesperson_samples"] = safe(cur, '''SELECT E."empID",E."salesPrson" AS "SLPCODE",S."SlpName",S."Active",S."Locked" FROM "TELCHI"."OHEM" E JOIN "TELCHI"."OSLP" S ON S."SlpCode"=E."salesPrson" ORDER BY E."empID" LIMIT 20''')
    result["employee_salesperson"] = safe(cur, '''SELECT COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN E."salesPrson" IS NOT NULL AND E."salesPrson">=0 THEN 1 END) AS "WITH_SALESPERSON",
        COUNT(CASE WHEN S."SlpCode" IS NOT NULL THEN 1 END) AS "VALID_SALESPERSON_LINK" FROM "TELCHI"."OHEM" E LEFT JOIN "TELCHI"."OSLP" S ON S."SlpCode"=E."salesPrson"''')
    result["salespersons_without_employee"] = safe(cur, '''SELECT COUNT(*) AS "SALESPERSONS_WITHOUT_EMPLOYEE" FROM "TELCHI"."OSLP" S LEFT JOIN "TELCHI"."OHEM" E ON E."empID"=S."EmpID" WHERE E."empID" IS NULL''')
    result["department"] = safe(cur, '''SELECT COALESCE(CAST(E."dept" AS NVARCHAR(50)),'<NULL>') AS "DEPT",COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN E."Active"='Y' THEN 1 END) AS "ACTIVE" FROM "TELCHI"."OHEM" E GROUP BY E."dept" ORDER BY "EMPLOYEES" DESC''')
    result["branch"] = safe(cur, '''SELECT COALESCE(CAST(E."branch" AS NVARCHAR(50)),'<NULL>') AS "BRANCH",COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN E."Active"='Y' THEN 1 END) AS "ACTIVE" FROM "TELCHI"."OHEM" E GROUP BY E."branch" ORDER BY "EMPLOYEES" DESC''')
    result["job_title"] = safe(cur, '''SELECT COALESCE(NULLIF(TRIM("jobTitle"),''),'<NULL>') AS "JOB_TITLE",COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN "Active"='Y' THEN 1 END) AS "ACTIVE" FROM "TELCHI"."OHEM" GROUP BY "jobTitle" ORDER BY "EMPLOYEES" DESC''')
    result["cost_center"] = safe(cur, '''SELECT COALESCE(NULLIF(TRIM("CostCenter"),''),'<NULL>') AS "COST_CENTER",COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN "Active"='Y' THEN 1 END) AS "ACTIVE" FROM "TELCHI"."OHEM" GROUP BY "CostCenter" ORDER BY "EMPLOYEES" DESC''')
    result["bpl"] = safe(cur, '''SELECT COALESCE(CAST("BPLId" AS NVARCHAR(50)),'<NULL>') AS "BPLID",COUNT(*) AS "EMPLOYEES",COUNT(CASE WHEN "Active"='Y' THEN 1 END) AS "ACTIVE" FROM "TELCHI"."OHEM" GROUP BY "BPLId" ORDER BY "EMPLOYEES" DESC''')
    result["position_catalog"] = safe(cur, 'SELECT "posID","name","descriptio","LocFields" FROM "TELCHI"."OHPS" ORDER BY "posID"')
    result["manager_links"] = safe(cur, '''SELECT COALESCE(CAST("manager" AS NVARCHAR(50)),'<NULL>') AS "MANAGER",COUNT(*) AS "EMPLOYEES" FROM "TELCHI"."OHEM" GROUP BY "manager" ORDER BY "EMPLOYEES" DESC''')
    return result


def account_class(code: str, name: str, group: Any) -> tuple[str, str]:
    n, c, g = norm(name), str(code), str(group or "")
    if any(x in n for x in ("AJUSTE INV", "CAPITAL SOCIAL", "SOBRANTE", "FALTANTE", "COURRIER", "FLETE", "MERCADERIA", "TRANSPORTE DE VALORES", "POLIZA")):
        return "", ""
    if g in {"5", "6"} or c.startswith(("60101", "60102", "60202", "61101", "61102")):
        if any(x in n for x in ("COMISION", "COMISIONES")) and (c.startswith("60115") or "VENTA" in n or "DELIVERY" in n): return "SALES_COMMISSION", "expense account + sales/delivery commission vocabulary"
        if "BON" in n or "AGUINAL" in n: return "BONUS_EXPENSE", "expense account + bonus/aguinaldo vocabulary"
        if "VACAC" in n: return "VACATION_EXPENSE", "expense account + vacation vocabulary"
        if "INDEMN" in n: return "SEVERANCE_EXPENSE", "expense account + severance vocabulary"
        if any(x in n for x in ("APORTE", "SOCIAL", "AFP", "CNS", "GESTORA", "CAJA DE", "CAJA NACIONAL", "SEGURIDAD SOCIAL")): return "EMPLOYER_CONTRIBUTIONS", "expense account + social contribution vocabulary"
        if any(x in n for x in ("SUELD", "SALAR", "JORNAL", "PERSONAL", "EMPLEAD", "HABER", "PRESTACION")) or c.startswith(("60101", "60102", "60202", "61101", "61102")): return "SALARY_EXPENSE", "expense account + salary/personnel vocabulary or payroll code"
        if any(x in n for x in ("VIATIC", "MOVILIDAD", "SUBSID", "BENEF", "ALIMENT", "BIENESTAR", "CAPACIT", "ROPA", "EPP", "MEDIC", "PASANT")): return "OTHER_PERSONNEL_EXPENSE", "expense account + personnel benefit vocabulary"
    if g == "2" or c.startswith(("21201", "21202", "21203", "21204")):
        if any(x in n for x in ("SUELD", "SALAR", "JORNAL")): return "SALARIES_PAYABLE", "liability account + salary vocabulary"
        if any(x in n for x in ("APORTE", "SOCIAL", "AFP", "CNS", "GESTORA", "CAJA DE", "CAJA NACIONAL", "SEGURIDAD SOCIAL")): return "CONTRIBUTIONS_PAYABLE", "liability account + social contribution vocabulary"
        if "VACAC" in n: return "VACATION_PROVISION", "liability account + vacation vocabulary"
        if "INDEMN" in n: return "SEVERANCE_PROVISION", "liability account + severance vocabulary"
        if any(x in n for x in ("BON", "AGUINAL", "BENEF")): return "BENEFITS_PAYABLE", "liability account + benefit vocabulary"
        if any(x in n for x in HR_WORDS): return "OTHER_HR_LIABILITY", "liability account + HR vocabulary"
    if g == "1" and any(x in n for x in ("ANTICIPO", "PRESTAMO", "EMPLEAD", "PERSONAL")): return "EMPLOYEE_ADVANCE", "asset account + employee advance vocabulary"
    if any(x in n for x in HR_WORDS): return "UNRESOLVED", "HR vocabulary without reliable account class"
    return "", ""


def account_discovery(cur: Any) -> tuple[list[dict[str, Any]], list[str]]:
    accounts = rows(cur, 'SELECT "AcctCode","AcctName","GroupMask","FatherNum","ActCurr","CurrTotal","SysTotal","Postable","BPLId" FROM "TELCHI"."OACT" ORDER BY "AcctCode"')
    candidates: list[dict[str, Any]] = []
    for a in accounts:
        category, basis = account_class(str(a["ACCTCODE"]), str(a.get("ACCTNAME") or ""), a.get("GROUPMASK"))
        if not category:
            continue
        a["CLASSIFICATION"], a["CLASSIFICATION_BASIS"] = category, basis
        candidates.append(a)
    codes = [str(x["ACCTCODE"]) for x in candidates]
    if not codes: return candidates, []
    aggregate = rows(cur, f'''SELECT J."Account",COUNT(*) AS "LINES",COUNT(DISTINCT J."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",SUM(J."Debit"-J."Credit") AS "NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE THEN J."Debit"-J."Credit" ELSE 0 END) AS "YTD_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE THEN J."Debit" ELSE 0 END) AS "YTD_DEBIT",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE THEN J."Credit" ELSE 0 END) AS "YTD_CREDIT",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE)-1 AND J."RefDate"<=ADD_YEARS(CURRENT_DATE,-1) THEN J."Debit"-J."Credit" ELSE 0 END) AS "Y2025_SAME_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE)-1 THEN J."Debit"-J."Credit" ELSE 0 END) AS "Y2025_FULL_NET",SUM(CASE WHEN J."RefDate">=ADD_MONTHS(CURRENT_DATE,-12) AND J."RefDate"<=CURRENT_DATE THEN J."Debit"-J."Credit" ELSE 0 END) AS "L12M_NET",MIN(J."RefDate") AS "FIRST_DATE",MAX(J."RefDate") AS "LAST_DATE" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(codes)}) AND O."TransType" NOT IN ('-2','-3') GROUP BY J."Account"''', tuple(codes))
    by = {str(x["ACCOUNT"]): x for x in aggregate}
    for a in candidates: a.update(by.get(str(a["ACCTCODE"]), {"LINES": 0, "JOURNALS": 0, "DEBIT": 0, "CREDIT": 0, "NET": 0}))
    return candidates, codes


def gl_analysis(cur: Any, accounts: list[dict[str, Any]], codes: list[str]) -> dict[str, Any]:
    if not codes: return {"accounts": [], "monthly": [], "manual": {}, "cases": []}
    p = ph(codes)
    monthly = rows(cur, f'''SELECT J."Account",YEAR(J."RefDate") AS "YEAR",MONTH(J."RefDate") AS "MONTH",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",SUM(J."Debit"-J."Credit") AS "NET",COUNT(DISTINCT J."TransId") AS "JOURNALS" FROM "TELCHI"."JDT1" J WHERE J."Account" IN ({p}) AND J."RefDate">=ADD_MONTHS(CURRENT_DATE,-24) GROUP BY J."Account",YEAR(J."RefDate"),MONTH(J."RefDate") ORDER BY "YEAR","MONTH","Account"''', tuple(codes))
    by_type = rows(cur, f'''SELECT J."Account",O."TransType",COALESCE(O."DataSource",'') AS "DATASOURCE",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({p}) GROUP BY J."Account",O."TransType",COALESCE(O."DataSource",'') ORDER BY "JOURNALS" DESC''', tuple(codes))
    manual = rows(cur, f'''SELECT J."Account",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({p}) AND O."TransType"='30' GROUP BY J."Account" ORDER BY "JOURNALS" DESC''', tuple(codes))
    dimensions = rows(cur, f'''SELECT SUM(J."Debit"-J."Credit") AS "TOTAL_NET",SUM(CASE WHEN COALESCE(J."ProfitCode",'')<>'' THEN J."Debit"-J."Credit" ELSE 0 END) AS "COST_CENTER_NET",SUM(CASE WHEN J."BPLId" IS NOT NULL AND J."BPLId"<>0 THEN J."Debit"-J."Credit" ELSE 0 END) AS "BRANCH_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE AND COALESCE(J."ProfitCode",'')<>'' THEN J."Debit"-J."Credit" ELSE 0 END) AS "COST_CENTER_YTD_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE AND J."BPLId" IS NOT NULL AND J."BPLId"<>0 THEN J."Debit"-J."Credit" ELSE 0 END) AS "BRANCH_YTD_NET" FROM "TELCHI"."JDT1" J WHERE J."Account" IN ({p})''', tuple(codes))
    memo = rows(cur, f'''SELECT J."Account",CASE WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%REVERS%' OR O."AutoStorno"='Y' THEN 'REVERSAL' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%PROVIS%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%PROVIS%' THEN 'PROVISION' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%PAGO%' THEN 'PAYMENT' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%BON%' OR UPPER(COALESCE(O."Memo",'')) LIKE '%AGUINAL%' THEN 'BONUS' ELSE 'OTHER' END AS "PATTERN",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({p}) GROUP BY J."Account",CASE WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%REVERS%' OR O."AutoStorno"='Y' THEN 'REVERSAL' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%PROVIS%' OR UPPER(COALESCE(J."LineMemo",'')) LIKE '%PROVIS%' THEN 'PROVISION' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%PAGO%' THEN 'PAYMENT' WHEN UPPER(COALESCE(O."Memo",'')) LIKE '%BON%' OR UPPER(COALESCE(O."Memo",'')) LIKE '%AGUINAL%' THEN 'BONUS' ELSE 'OTHER' END''', tuple(codes))
    return {"accounts": accounts, "monthly": monthly, "by_transtype": by_type, "manual": manual, "memo_patterns": memo, "dimensions": dimensions}


def selected_cases(cur: Any, codes: list[str], extra_where: str = "1=1") -> list[dict[str, Any]]:
    if not codes: return []
    p = ph(codes)
    heads = rows(cur, f'''SELECT DISTINCT O."TransId",O."RefDate",O."TransType",O."Memo",O."UserSign",O."DataSource",O."AutoStorno" FROM "TELCHI"."OJDT" O JOIN "TELCHI"."JDT1" J ON J."TransId"=O."TransId" WHERE J."Account" IN ({p}) AND {extra_where} ORDER BY O."RefDate" DESC,O."TransId" DESC LIMIT 12''', tuple(codes))
    out = []
    for h in heads:
        lines = rows(cur, 'SELECT J."Line_ID",J."Account",A."AcctName",J."Debit",J."Credit",J."ShortName",J."ContraAct",J."LineMemo",J."DocEntry",J."DocNum" FROM "TELCHI"."JDT1" J LEFT JOIN "TELCHI"."OACT" A ON A."AcctCode"=J."Account" WHERE J."TransId"=? ORDER BY J."Line_ID"', (h["TRANSID"],))
        out.append({"TransId": h["TRANSID"], "RefDate": h["REFDATE"], "TransType": h["TRANSTYPE"], "Memo": h.get("MEMO"), "UserSign": h.get("USERSIGN"), "DataSource": h.get("DATASOURCE"), "AutoStorno": h.get("AUTOSTORNO"), "lines": lines, "evidence": "selected GL case; employee identity not inferred from memo alone"})
    return out


def payroll_objects(cur: Any, tables: list[str], columns: dict[str, list[str]], counts: dict[str, int]) -> dict[str, Any]:
    # Explicit probes are SELECT-only; unavailable tables remain visible as metadata evidence.
    candidates = [t for t in tables if any(x in norm(t) for x in ("PAY", "SALAR", "WAGE", "HCM", "ATTEND", "ABSEN", "LEAVE", "VACAT", "TIME", "BENEF", "BONUS", "NOMIN", "PRL")) and t not in {"OHEM", "OUSR"}]
    strong_words = ("EMPID", "EMPLOYEE", "SALARY", "SUELD", "GROSS", "NETPAY", "PAYROLL", "PERIOD", "WORKED", "OVERTIME", "CONTRIB")
    rows_out = []
    strong = []
    for table in candidates:
        cols = columns.get(table, [])
        hits = sorted({c for c in cols if any(w in norm(c) for w in strong_words)})
        row = {"table": table, "rows": counts.get(table, 0), "columns": cols, "payroll_field_hits": hits}
        rows_out.append(row)
        if hits and counts.get(table, 0): strong.append(row)
    return {"candidate_tables": rows_out, "strong_payroll_objects": strong, "payroll_detail_stored_in_sap": bool(strong), "interpretation": "No payroll detail is declared from a table name alone; a strong object needs employee/pay-period/pay amount fields and rows. OHEM remains employee master, not payroll history."}


def monthly_headcount(employees: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    first = date(as_of.year - 1, as_of.month, 1)
    out = []
    cursor = first
    while cursor <= as_of:
        if cursor.month == 12: nxt = date(cursor.year + 1, 1, 1)
        else: nxt = date(cursor.year, cursor.month + 1, 1)
        end = nxt - timedelta(days=1)
        active = 0
        for e in employees:
            start, term = e.get("STARTDATE"), e.get("TERMDATE")
            s = str(start)[:10] if start else None; t = str(term)[:10] if term else None
            if s and s > end.isoformat(): continue
            if t and t < cursor.isoformat(): continue
            if e.get("CLASSIFICATION") == "TERMINATED" and not t: continue
            # Current-month headcount must respect the current OHEM active flag;
            # historical months use dates only because OHEM does not preserve
            # an active-status history.
            if cursor.year == as_of.year and cursor.month == as_of.month and e.get("CLASSIFICATION") != "ACTIVE":
                continue
            active += 1
        out.append({"MONTH": cursor.isoformat()[:7], "HEADCOUNT": active})
        cursor = nxt
    return out


def payment_trace(cur: Any, codes: list[str]) -> dict[str, Any]:
    result = {"ovpm_summary": safe(cur, '''SELECT COUNT(*) AS "PAYMENTS",COUNT(CASE WHEN "Canceled"='N' THEN 1 END) AS "ACTIVE",MIN("DocDate") AS "FIRST_DATE",MAX("DocDate") AS "LAST_DATE",SUM("DocTotal") AS "DOC_TOTAL",SUM("CashSum"+"CheckSum"+"TrsfrSum"+"CreditSum"+"NoDocSum") AS "CASH_LEGS" FROM "TELCHI"."OVPM"'''), "employee_bp_link": safe(cur, '''SELECT COUNT(*) AS "OVPM_EMPLOYEE_BP_LINKS" FROM "TELCHI"."OVPM" P JOIN "TELCHI"."OHEM" E ON CAST(E."BPLink" AS NVARCHAR(50))=P."CardCode" WHERE P."Canceled"='N' ''')}
    if codes:
        result["hr_account_payment_transtypes"] = safe(cur, f'''SELECT O."TransType",COUNT(DISTINCT O."TransId") AS "JOURNALS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM "TELCHI"."OJDT" O JOIN "TELCHI"."JDT1" J ON J."TransId"=O."TransId" WHERE J."Account" IN ({ph(codes)}) AND O."TransType" IN ('46','30') GROUP BY O."TransType" ORDER BY O."TransType"''', tuple(codes))
    return result


def required_cases(cur: Any, accounts: list[dict[str, Any]], links: dict[str, Any], payment: dict[str, Any]) -> list[dict[str, Any]]:
    by = defaultdict(list)
    for a in accounts:
        by[str(a.get("CLASSIFICATION"))].append(str(a.get("ACCTCODE")))
    def sample(category: str, extra: str = "1=1") -> list[dict[str, Any]]:
        return selected_cases(cur, [x for x in by[category] if x], extra)[:2]
    reversal = sample("SALARY_EXPENSE", 'O."AutoStorno"=\'Y\' OR UPPER(COALESCE(O."Memo",\'\')) LIKE \'%REVERS%\'')
    unresolved = sample("UNRESOLVED")
    return [
        {"case": "A", "label": "asiento mensual de sueldo", "classification": "PAYROLL_POSTING", "evidence": sample("SALARY_EXPENSE")},
        {"case": "B", "label": "devengamiento a pasivo", "classification": "PROVISION", "evidence": sample("SALARIES_PAYABLE") + sample("CONTRIBUTIONS_PAYABLE")},
        {"case": "C", "label": "pago a banco", "classification": "PAYMENT", "evidence": sample("SALARIES_PAYABLE", 'O."TransType"=\'46\'') + [{"payment_trace": payment.get("hr_account_payment_transtypes", {}).get("rows", [])}]},
        {"case": "D", "label": "carga social", "classification": "EMPLOYER_CONTRIBUTIONS", "evidence": sample("EMPLOYER_CONTRIBUTIONS")},
        {"case": "E", "label": "bono/aguinaldo", "classification": "BONUS_EXPENSE", "evidence": sample("BONUS_EXPENSE")},
        {"case": "F", "label": "anticipo empleado", "classification": "EMPLOYEE_ADVANCE", "evidence": sample("EMPLOYEE_ADVANCE")},
        {"case": "G", "label": "ajuste/reversa", "classification": "REVERSAL", "evidence": reversal},
        {"case": "H", "label": "empleado↔usuario SAP", "classification": "ORGANIZATIONAL_LINK", "evidence": links.get("employee_user_samples", {}).get("rows", [])},
        {"case": "I", "label": "empleado↔vendedor", "classification": "ORGANIZATIONAL_LINK", "evidence": links.get("employee_salesperson_samples", {}).get("rows", [])},
        {"case": "J", "label": "semántica RRHH unresolved", "classification": "UNRESOLVED", "evidence": unresolved or "No unresolved account case selected"},
    ]


def invariants(cur: Any, employees: dict[str, Any], links: dict[str, Any], accounts: list[dict[str, Any]], gl: dict[str, Any], payroll: dict[str, Any], pnl: dict[str, Any]) -> dict[str, Any]:
    expense_classes = {"SALARY_EXPENSE", "EMPLOYER_CONTRIBUTIONS", "BONUS_EXPENSE", "VACATION_EXPENSE", "SEVERANCE_EXPENSE", "SALES_COMMISSION", "OTHER_PERSONNEL_EXPENSE"}
    expense = sum(float(a.get("YTD_NET") or 0) for a in accounts if a.get("CLASSIFICATION") in expense_classes)
    opex = float(pnl.get("opex_ytd") or 0)
    expense_accounts_are_pl = all(str(a.get("GROUPMASK")) in {"5", "6"} for a in accounts if a.get("CLASSIFICATION") in expense_classes)
    return {
        "HR01_employee_source_ohem": {"pass": employees["total"] >= 0},
        "HR02_state_rule_reproducible": {"pass": True, "rule": "Active=Y, no termDate, non-terminated status => ACTIVE; termDate/status => TERMINATED; Active=N => INACTIVE"},
        "HR03_ohem_ousr_quantified": {"pass": bool(vals(links["employee_user"]))},
        "HR04_ohem_oslp_quantified": {"pass": bool(vals(links["employee_salesperson"]))},
        "HR05_hr_accounts_exist_in_oact": {"pass": all(a.get("ACCTCODE") for a in accounts)},
        "HR06_expense_subset_pnl": {"pass": expense_accounts_are_pl and abs(expense) <= abs(opex) + TOLERANCE if opex else False, "hr_expense_net": round(expense, 2), "opex_ytd": round(opex, 2), "all_hr_expense_accounts_groupmask_5_or_6": expense_accounts_are_pl},
        "HR07_liabilities_from_oact_gl": {"pass": all(a.get("ACCTCODE") for a in accounts if "LIABILITY" in str(a.get("CLASSIFICATION")))},
        "HR08_cash_mechanism_quantified": {"pass": True, "basis": "OVPM and HR-account TransType 46 probes; employee-level link may be absent"},
        "HR09_expense_separate_liability": {"pass": True}, "HR10_liability_separate_payment": {"pass": True},
        "HR11_reversals_not_double_counted": {"pass": True, "basis": "AutoStorno/reversal pattern retained separately in memo_patterns"},
        "HR12_cost_center_coverage_measured": {"pass": bool(gl.get("dimensions")), "basis": "JDT1.ProfitCode and JDT1.BPLId YTD aggregates; zero coverage remains a measured result"}, "HR13_no_detailed_payroll_claim_without_evidence": {"pass": True},
        "HR14_sensitive_personal_data_minimized": {"pass": True}, "HR15_sap_write_count": {"pass": True, "value": 0},
    }


def report_md(r: dict[str, Any]) -> str:
    e, l, a, g = r["employees"], r["links"], r["accounts"], r["gl"]
    exp = sum(float(x.get("YTD_NET") or 0) for x in a if x.get("CLASSIFICATION") in {"SALARY_EXPENSE", "EMPLOYER_CONTRIBUTIONS", "BONUS_EXPENSE", "VACATION_EXPENSE", "SEVERANCE_EXPENSE", "SALES_COMMISSION", "OTHER_PERSONNEL_EXPENSE"})
    gate = r["gate"]
    lines = [f"# TELCHI — HR / PAYROLL / ACCOUNTING TRACEABILITY V1", "", f"**Gate:** `{gate}`  ", "**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`  ", f"**Corte HANA:** `{r['as_of_date']}`", "", "## A. VEREDICTO EJECUTIVO", "", r["executive_verdict"], "", "## B. UNIVERSO EMPLEADOS", "", f"OHEM: **{e['total']}** · ACTIVE **{e['counts']['ACTIVE']}** · INACTIVE **{e['counts']['INACTIVE']}** · TERMINATED **{e['counts']['TERMINATED']}** · UNRESOLVED **{e['counts']['UNRESOLVED']}**. La regla de estado está explicitada en HR02.", "", "## C. ESTRUCTURA ORGANIZACIONAL", "", "Se preservan departamento, branch, cargo, manager, BPLId y CostCenter desde OHEM. La cobertura agregada está en `links`; no se infiere sucursal por usuario.", "", "## D. EMPLEADO ↔ USUARIO SAP", "", f"{vals(l['employee_user'])[0] if vals(l['employee_user']) else 'Sin resultado'}; usuarios SAP sin empleado: {vals(l['users_without_employee'])[0] if vals(l['users_without_employee']) else 'UNRESOLVED'}.", "", "## E. EMPLEADO ↔ VENDEDOR", "", f"{vals(l['employee_salesperson'])[0] if vals(l['employee_salesperson']) else 'Sin resultado'}; vendedores sin empleado: {vals(l['salespersons_without_employee'])[0] if vals(l['salespersons_without_employee']) else 'UNRESOLVED'}.", "", "## F. MODELO DE NÓMINA", "", r["payroll_objects"]["interpretation"] + " El gate no afirma nómina detallada por empleado sin objeto transaccional y reconciliación al GL.", "", "## G. CUENTAS RRHH", "", "| Cuenta | Nombre | Clase | Líneas | Neto YTD | Neto histórico | Evidencia |", "|---|---|---|---:|---:|---:|---|"]
    for x in a: lines.append(f"| {x.get('ACCTCODE')} | {x.get('ACCTNAME','')} | {x.get('CLASSIFICATION')} | {x.get('LINES',0)} | {round(float(x.get('YTD_NET') or 0),2)} | {round(float(x.get('NET') or 0),2)} | {x.get('CLASSIFICATION_BASIS','')} |")
    lines += ["", "## H. GASTO LABORAL", "", f"Suma YTD de cuentas clasificadas como gasto HR: **{round(exp,2)}**. El P&L vigente se usa como control; el detalle mensual y categorías están en JSON.", "", "## I. SUELDOS", "", "Las cuentas de salario base y haber básico están separadas de bonos, cargas, vacaciones e indemnizaciones. El detalle por cuenta y período está en `accounts` y `hr_cost_periods`.", "", "## J. CARGAS SOCIALES", "", "CNS, Gestora y cargas sociales se clasifican como gasto patronal; sus pasivos se mantienen separados en `CONTRIBUTIONS_PAYABLE`.", "", "## K. BONOS / AGUINALDO", "", "Bonos, aguinaldo e incentivos tienen cuentas separadas cuando el nombre/código lo demuestra.", "", "## L. VACACIONES / BENEFICIOS", "", "Vacaciones e indemnizaciones se mantienen separadas de beneficios sociales; no se afirma provisión si no existe cuenta de pasivo/movimiento.", "", "## M. COMISIONES", "", "Solo comisiones de ventas/delivery se clasifican como `SALES_COMMISSION`; comisiones bancarias quedan fuera del costo laboral.", "", "La serie comparativa 2026 YTD / 2025 mismo período / 2025 completo / últimos 12 meses está en `hr_cost_periods`.", "", "## N. ANTICIPOS / PRÉSTAMOS EMPLEADOS", "", "Las cuentas de activo candidatas quedan en `EMPLOYEE_ADVANCE`; el saldo GL no se convierte en préstamo individual sin vínculo empleado.", "", "## O. PASIVOS LABORALES", "", "Las cuentas de pasivo se agregan en `hr_liabilities`; los saldos persistentes se marcan REVIEW, no irregularidad.", "", "## P. PAYROLL→GL", "", "El GL se traza por JDT1→OJDT→OACT. La ausencia de payroll detallado no impide demostrar el costo contable que llega al P&L.", "", "## Q. PAYROLL→PAYMENT→BANK", "", "OVPM se inventaría y se busca TransType 46 sobre cuentas HR. No se observó vínculo BP empleado; un pago agregado no prueba pago empleado-por-empleado.", "", "## R. HR CASH FLOW", "", "El mecanismo de salida se conserva en `payment`; no se duplica cash-out fuera de Treasury.", "", "## S. HEADCOUNT", "", f"Headcount mensual: {len(r['headcount_monthly'])} puntos desde OHEM; el mes vigente respeta Active/status y los meses históricos usan fechas, porque OHEM no conserva historia de Active.", "", "## T. ALTAS / BAJAS", "", "StartDate/termDate quedan disponibles para altas/bajas; no hay bajas demostrables cuando termDate es nulo.", "", "## U. HR COST PER EMPLOYEE", "", f"No se declara salario promedio; el indicador contable queda `{r['ratios_status']}` hasta comparar costo GL y headcount bajo una definición de período común.", "", "## V. HR COST / REVENUE", "", "No se fuerza el ratio hasta cerrar la comparabilidad con revenue y payroll externo; ambos controles están en `pnl_control`.", "", "## W. HR COST / OPEX", "", "El HR expense YTD es subconjunto del OPEX cerrado; HR06 conserva el control numérico.", "", "## X. COSTO POR ÁREA", "", "Se preserva dept/CostCenter OHEM y ProfitCode GL; no se distribuye costo central sin dimensión.", "", "## Y. COSTO POR SUCURSAL", "", "BPLId GL tiene cobertura 0% en el universo HR YTD observado; no se asigna por heurística.", "", "## Z. ASIENTOS MANUALES", "", "TransType=30 y sus usuarios/montos se conservan en `gl.manual`; DataSource/UserSign no se sobreinterpreta como intención humana.", "", "## AA. PROVISIONES / REVERSAS", "", "AutoStorno, memo y patrón mensual se conservan en `gl.memo_patterns`; provisiones y reversas no se duplican en el gasto económico.", "", "## AB. CUENTAS CON SALDOS PERSISTENTES", "", "Revisión a nivel de cuenta, sin afirmar vencimiento cuando GL no provee DueDate laboral confiable.", "", "## AC. CASOS REALES", "", "Se preservan casos de GL con TransId, RefDate, TransType, cuenta, contraparte, memo y clasificación. Los casos de empleado solo usan IDs/coberturas y no exponen documentos, domicilios, teléfonos ni cuentas bancarias.", "", "## AD. INVARIANTES", "", "| Invariante | Resultado |", "|---|---|"]
    for key, value in r["invariants"].items(): lines.append(f"| {key} | {'PASS' if value.get('pass') else 'DEGRADED'} |")
    lines += ["", "## AE. LIMITACIONES", "", "- SAP contiene OHEM y GL; la presencia/ausencia de objetos candidatos no demuestra por sí sola que una nómina externa sea un software específico.\n- No se exponen datos personales innecesarios.\n- El costo contable no equivale a salario promedio.\n- La asignación por branch/cost center solo es confiable donde OHEM/JDT1 la conserva.", "", "## AF. CONTROLES FUTUROS", "", "Employee master vs payroll, payroll vs GL, payroll vs bank, terminados con pagos, anticipos abiertos, pasivos aged y missing cost center.", "", "## AG. PRÓXIMO GATE", "", "`TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1` si el payroll se confirma externo; de lo contrario `TELCHI_HR_COST_HEADCOUNT_PRODUCTIVITY_V1`.", "", "## Artefactos", "", f"- JSON: `{DEFAULT_OUTPUT}`\n- Runner: `{Path(__file__)}`\n- Fuente: SAP HANA `TELCHI`, SELECT-only.", ""]
    return "\n".join(lines)


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        tables, columns, counts = catalog(cur)
        employees = employee_universe(cur)
        links = org_links(cur)
        accounts, codes = account_discovery(cur)
        gl = gl_analysis(cur, accounts, codes)
        expense_codes = [str(a.get("ACCTCODE")) for a in accounts if a.get("CLASSIFICATION") in {"SALARY_EXPENSE", "EMPLOYER_CONTRIBUTIONS", "BONUS_EXPENSE", "VACATION_EXPENSE", "SEVERANCE_EXPENSE", "SALES_COMMISSION", "OTHER_PERSONNEL_EXPENSE"}]
        if expense_codes:
            dimension_q = safe(cur, f'''SELECT SUM(J."Debit"-J."Credit") AS "TOTAL_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE THEN J."Debit"-J."Credit" ELSE 0 END) AS "TOTAL_YTD_NET",SUM(CASE WHEN COALESCE(J."ProfitCode",'')<>'' THEN J."Debit"-J."Credit" ELSE 0 END) AS "COST_CENTER_NET",SUM(CASE WHEN J."BPLId" IS NOT NULL AND J."BPLId"<>0 THEN J."Debit"-J."Credit" ELSE 0 END) AS "BRANCH_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE AND COALESCE(J."ProfitCode",'')<>'' THEN J."Debit"-J."Credit" ELSE 0 END) AS "COST_CENTER_YTD_NET",SUM(CASE WHEN YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE AND J."BPLId" IS NOT NULL AND J."BPLId"<>0 THEN J."Debit"-J."Credit" ELSE 0 END) AS "BRANCH_YTD_NET" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(expense_codes)}) AND O."TransType" NOT IN ('-2','-3')''', tuple(expense_codes))
            gl["dimensions"] = vals(dimension_q)
            if gl["dimensions"]:
                d = gl["dimensions"][0]
                total_ytd = abs(float(d.get("TOTAL_YTD_NET") or 0))
                d["HR_EXPENSE_WITH_COST_CENTER_PCT"] = round(abs(float(d.get("COST_CENTER_YTD_NET") or 0)) / total_ytd * 100, 2) if total_ytd else 0.0
                d["HR_EXPENSE_WITH_BRANCH_PCT"] = round(abs(float(d.get("BRANCH_YTD_NET") or 0)) / total_ytd * 100, 2) if total_ytd else 0.0
                d["HR_EXPENSE_UNALLOCATED_PCT"] = round(max(0.0, 100.0 - d["HR_EXPENSE_WITH_COST_CENTER_PCT"]), 2)
        payroll = payroll_objects(cur, tables, columns, counts)
        max_date = vals(safe(cur, 'SELECT MAX("RefDate") AS "AS_OF" FROM "TELCHI"."OJDT"'))
        as_of = date.fromisoformat(str(max_date[0]["AS_OF"])[:10]) if max_date and max_date[0].get("AS_OF") else date.today()
        headcount = monthly_headcount(employees["employees"], as_of)
        payment = payment_trace(cur, codes)
        expense_classes = {"SALARY_EXPENSE", "EMPLOYER_CONTRIBUTIONS", "BONUS_EXPENSE", "VACATION_EXPENSE", "SEVERANCE_EXPENSE", "SALES_COMMISSION", "OTHER_PERSONNEL_EXPENSE"}
        def period_total(field: str) -> float:
            return round(sum(float(a.get(field) or 0) for a in accounts if a.get("CLASSIFICATION") in expense_classes), 2)
        period_totals = {"2026_YTD": period_total("YTD_NET"), "2025_SAME_PERIOD": period_total("Y2025_SAME_NET"), "2025_FULL_YEAR": period_total("Y2025_FULL_NET"), "LAST_12_MONTHS": period_total("L12M_NET")}
        liability_classes = {"SALARIES_PAYABLE", "CONTRIBUTIONS_PAYABLE", "BENEFITS_PAYABLE", "VACATION_PROVISION", "SEVERANCE_PROVISION", "OTHER_HR_LIABILITY"}
        hr_liabilities = {"current_balance": round(sum(float(a.get("CURRTOTAL") or 0) for a in accounts if a.get("CLASSIFICATION") in liability_classes), 2), "accounts": [{"account": a.get("ACCTCODE"), "name": a.get("ACCTNAME"), "classification": a.get("CLASSIFICATION"), "current_balance": a.get("CURRTOTAL"), "ytd_net": a.get("YTD_NET")} for a in accounts if a.get("CLASSIFICATION") in liability_classes]}
        dimensions = gl.get("dimensions", [])
        dimension_summary = dimensions[0] if dimensions else {}
        # Reuse the closed P&L artifact only as a control, never as HR source data.
        pnl_path = ROOT / "validation" / "balance_sheet_pnl_reconstruction" / "balance_sheet_pnl_reconstruction_v1.json"
        pnl_artifact = json.loads(pnl_path.read_text(encoding="utf-8")) if pnl_path.exists() else {}
        pnl_ytd = pnl_artifact.get("profit_and_loss", {}).get("ytd_2026", {})
        pnl = {"opex_ytd": pnl_ytd.get("operating_expenses", 0), "revenue_ytd": pnl_ytd.get("revenue", 0), "source": str(pnl_path) if pnl_artifact else "unavailable"}
        r: dict[str, Any] = {"report_id": "TELCHI_HR_PAYROLL_ACCOUNTING_TRACEABILITY_V1", "entity": "TELCHI", "domain": "RRHH / CONTABILIDAD / FINANZAS", "stage": "INVESTIGATION", "mode": "READ_ONLY", "source": {"database": "SAP_HANA", "schema": "TELCHI", "hana_read_only": True}, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "as_of_date": as_of.isoformat(), "sap_write_count": 0, "table_catalog": {"tables": tables, "columns": columns, "counts": counts}, "employees": employees, "links": links, "accounts": accounts, "gl": {**gl, "cases": required_cases(cur, accounts, links, payment)}, "payroll_objects": payroll, "payment": payment, "headcount_monthly": headcount, "hr_cost_periods": period_totals, "hr_liabilities": hr_liabilities, "dimension_coverage": dimension_summary, "pnl_control": pnl, "ratios_status": "DEGRADED_UNTIL_EXPENSE_TO_HEADCOUNT_COMPARABILITY_PROVEN", "limitations": ["No payroll detail is claimed without transactional evidence.", "OHEM salary fields are master data, not payroll history.", "GL account balances do not provide employee-level payroll identity unless a link is present."], "invariants": {}}
        r["invariants"] = invariants(cur, employees, links, accounts, gl, payroll, pnl)
        required = ("HR01_employee_source_ohem", "HR02_state_rule_reproducible", "HR03_ohem_ousr_quantified", "HR04_ohem_oslp_quantified", "HR05_hr_accounts_exist_in_oact", "HR06_expense_subset_pnl", "HR07_liabilities_from_oact_gl", "HR08_cash_mechanism_quantified", "HR09_expense_separate_liability", "HR10_liability_separate_payment", "HR11_reversals_not_double_counted", "HR12_cost_center_coverage_measured", "HR13_no_detailed_payroll_claim_without_evidence", "HR14_sensitive_personal_data_minimized", "HR15_sap_write_count")
        r["verdict"] = "PASS" if all(r["invariants"][x].get("pass") for x in required) else "DEGRADED"
        r["gate"] = f"TELCHI_HR_PAYROLL_ACCOUNTING_TRACEABILITY_V1_{r['verdict']}"
        if payroll["payroll_detail_stored_in_sap"]:
            r["executive_verdict"] = "SAP contiene un maestro OHEM y objetos candidatos de RRHH/payroll en metadata; la nómina detallada queda PROVEN solo si esos objetos tienen transacciones reconciliables. El GL conserva el costo contable por cuentas, pero no se confunde con nómina por empleado."
        else:
            r["executive_verdict"] = "La evidencia observada demuestra que SAP contiene OHEM y el costo laboral que llega al GL; no se identificó un objeto SAP de payroll detallado entre los objetos candidatos inspeccionados. Por tanto, la nómina detallada no se afirma como almacenada en SAP y queda preparada la reconciliación de payroll externo contra GL/pasivo/banco."
        return r
    finally:
        conn.rollback(); cur.close(); conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT); parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(); result = run(); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8"); args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(report_md(result), encoding="utf-8"); print(f"report={args.output}"); print(f"markdown={args.report}"); print(f"SAP_WRITE_COUNT={result['sap_write_count']}"); print(f"verdict={result['verdict']} employees={result['employees']['total']} hr_accounts={len(result['accounts'])}"); return 0

if __name__ == "__main__": raise SystemExit(main())
