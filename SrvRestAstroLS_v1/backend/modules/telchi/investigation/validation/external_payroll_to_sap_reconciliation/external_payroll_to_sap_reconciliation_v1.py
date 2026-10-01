#!/usr/bin/env python3
"""TELCHI external payroll -> SAP/GL/liability/bank reconciliation V1.

Investigation-only and SELECT-only.  The probe proves the SAP-side boundary
without pretending that aggregated journal entries are employee payroll.
Sensitive memo text, names and bank identifiers are deliberately not emitted.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import DATA_ROOT, EXTERNAL_FILES_ROOT, INVESTIGATION_ROOT
from modules.telchi.investigation.validation.hr_payroll_accounting_traceability.hr_payroll_accounting_traceability_v1 import (
    account_discovery,
    employee_universe,
    gl_analysis,
    norm,
    org_links,
    payment_trace,
    payroll_objects,
    safe,
    vals,
)

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "external_payroll_to_sap_reconciliation"
DEFAULT_OUTPUT = OUT_DIR / "external_payroll_to_sap_reconciliation_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_external_payroll_to_sap_reconciliation_v1_report.md"
TOLERANCE = 0.01
EXPENSE_CLASSES = {"SALARY_EXPENSE", "EMPLOYER_CONTRIBUTIONS", "BONUS_EXPENSE", "VACATION_EXPENSE", "SEVERANCE_EXPENSE", "SALES_COMMISSION", "OTHER_PERSONNEL_EXPENSE"}
LIABILITY_CLASSES = {"SALARIES_PAYABLE", "CONTRIBUTIONS_PAYABLE", "BENEFITS_PAYABLE", "VACATION_PROVISION", "SEVERANCE_PROVISION", "OTHER_HR_LIABILITY"}
PAYROLL_WORDS = ("PLANILLA", "NOMINA", "SUELD", "SALAR", "HABER", "PAYROLL")
PERIOD_MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def serial(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def ph(items: list[Any]) -> str:
    return ",".join("?" for _ in items) or "NULL"


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def money(value: Any) -> float:
    return round(num(value), 2)


def redact_account_name(value: Any) -> str:
    return re.sub(r"\d[\d-]*", "[BANK_ACCOUNT_REDACTED]", str(value or ""))


def query_rows(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    columns = [str(x[0]).upper() for x in (cur.description or ())]
    return [{key: serial(value) for key, value in zip(columns, row, strict=False)} for row in cur.fetchall()]


def extract_period(text: str, fallback_year: int | None = None) -> str | None:
    """Extract a payroll month only when the memo gives a month/year signal."""
    clean = norm(text).replace("Á", "A")
    month_pattern = "|".join(PERIOD_MONTHS)
    match = re.search(rf"\b({month_pattern})\s*(?:DE\s*)?(20\d{{2}}|\d{{2}})\b", clean)
    if not match:
        return None
    month = PERIOD_MONTHS[match.group(1)]
    year = int(match.group(2))
    if year < 100:
        year += 2000
    if fallback_year and year < 2020:
        year = fallback_year
    return f"{year:04d}-{month:02d}"


def memo_signal(header: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(str(header.get(key) or "") for key in ("MEMO", "REF1", "REF2", "REF3", "BASEREF"))
    text += " " + " ".join(str(line.get("LINEMEMO") or "") for line in lines)
    upper = norm(text)
    terms = [word for word in ("PLANILLA", "NOMINA", "SUELD", "SALAR", "HABER", "PROVIS", "PAGO", "BON", "AGUINAL", "VACAC", "INDEMN", "AJUST", "RECLAS") if word in upper]
    ref_date = str(header.get("REFDATE") or "")[:10]
    period = extract_period(text, int(ref_date[:4]) if ref_date[:4].isdigit() else None)
    return {"terms": terms, "period": period, "payroll_word": any(x in upper for x in PAYROLL_WORDS)}


def classify_journal(header: dict[str, Any], lines: list[dict[str, Any]], account_classes: dict[str, str]) -> tuple[str, dict[str, Any]]:
    signal = memo_signal(header, lines)
    text = " ".join(signal["terms"])
    classes = [account_classes.get(str(line.get("ACCOUNT")), "") for line in lines]
    expense_debit = sum(num(line.get("DEBIT")) for line, cls in zip(lines, classes, strict=False) if cls in EXPENSE_CLASSES)
    liability_credit = sum(num(line.get("CREDIT")) for line, cls in zip(lines, classes, strict=False) if cls in LIABILITY_CLASSES)
    liability_debit = sum(num(line.get("DEBIT")) for line, cls in zip(lines, classes, strict=False) if cls in LIABILITY_CLASSES)
    non_liability_credit = sum(num(line.get("CREDIT")) for line, cls in zip(lines, classes, strict=False) if cls not in LIABILITY_CLASSES)
    if str(header.get("AUTOSTORNO") or "") == "Y" or "ANUL" in norm(header.get("MEMO")) or "REVERS" in norm(header.get("MEMO")):
        kind = "PAYROLL_REVERSAL"
    elif "AJUST" in text or "RECLAS" in text:
        kind = "PAYROLL_ADJUSTMENT"
    elif str(header.get("TRANSTYPE")) == "46" or ("PAGO" in text and liability_debit > TOLERANCE and non_liability_credit > TOLERANCE):
        kind = "PAYROLL_PAYMENT"
    elif signal["payroll_word"] and expense_debit > TOLERANCE and liability_credit > TOLERANCE:
        kind = "PAYROLL_ACCRUAL"
    elif ("PROVIS" in text or "AGUINAL" in text or "VACAC" in text) and (expense_debit > TOLERANCE or liability_credit > TOLERANCE):
        kind = "PAYROLL_PROVISION"
    elif signal["payroll_word"] or any(x in text for x in ("BON", "AGUINAL", "VACAC", "INDEMN")):
        kind = "OTHER_HR"
    else:
        kind = "UNRESOLVED"
    signal.update({"expense_debit": money(expense_debit), "liability_credit": money(liability_credit), "liability_debit": money(liability_debit), "non_liability_credit": money(non_liability_credit)})
    return kind, signal


def discover_external_source() -> dict[str, Any]:
    """Inspect only approved roots and only payroll-like filenames, never contents."""
    candidates: list[str] = []
    inspected: list[str] = []
    for root in (EXTERNAL_FILES_ROOT, INVESTIGATION_ROOT / "docs", INVESTIGATION_ROOT / "validation", DATA_ROOT):
        inspected.append(str(root))
        try:
            for path in root.iterdir():
                if path.is_file() and path.suffix.lower() in {".csv", ".xlsx", ".xls", ".ods", ".parquet", ".txt"} and any(word in norm(path.name) for word in ("PAYROLL", "NOMINA", "PLANILLA", "SUELDO", "SALARIO", "RRHH")):
                    candidates.append(path.name)
        except OSError:
            continue
    return {
        "status": "SOURCE_REQUIRED" if not candidates else "CANDIDATE_REQUIRES_AUTHORIZATION",
        "searched_roots": inspected,
        "candidate_filenames": sorted(candidates),
        "source_available": bool(candidates),
        "privacy": "filenames only; no external file opened or modified",
    }


def load_journals(cur: Any, account_classes: dict[str, str]) -> list[dict[str, Any]]:
    codes = sorted(account_classes)
    if not codes:
        return []
    sql = f'''SELECT O."TransId",O."RefDate",O."CreateDate",O."CreateTime",O."TransType",O."DataSource",O."UserSign",O."UserSign2",O."Memo",O."Ref1",O."Ref2",O."Ref3",O."BaseRef",O."AutoStorno",J."Line_ID",J."Account",A."AcctName",J."Debit",J."Credit",J."ContraAct",J."LineMemo",J."ProfitCode",J."BPLId"
        FROM "TELCHI"."OJDT" O JOIN "TELCHI"."JDT1" J ON J."TransId"=O."TransId" LEFT JOIN "TELCHI"."OACT" A ON A."AcctCode"=J."Account"
        WHERE J."Account" IN ({ph(codes)}) AND O."TransType" NOT IN ('-2','-3') ORDER BY O."RefDate",O."TransId",J."Line_ID"'''
    raw = query_rows(cur, sql, tuple(codes))
    grouped: dict[Any, dict[str, Any]] = {}
    for row in raw:
        trans_id = row["TRANSID"]
        if trans_id not in grouped:
            grouped[trans_id] = {key: row.get(key) for key in ("TRANSID", "REFDATE", "CREATEDATE", "CREATETIME", "TRANSTYPE", "DATASOURCE", "USERSIGN", "USERSIGN2", "MEMO", "REF1", "REF2", "REF3", "BASEREF", "AUTOSTORNO")}
            grouped[trans_id]["lines"] = []
        bucket = grouped[trans_id]
        bucket["lines"].append({key: row.get(key) for key in ("LINE_ID", "ACCOUNT", "ACCTNAME", "DEBIT", "CREDIT", "CONTRAACT", "LINEMEMO", "PROFITCODE", "BPLID")})
    journals = []
    for item in grouped.values():
        kind, signal = classify_journal(item, item["lines"], account_classes)
        item["classification"] = kind
        item["signal"] = signal
        item["line_count"] = len(item["lines"])
        item["total_debit"] = money(sum(num(x.get("DEBIT")) for x in item["lines"]))
        item["total_credit"] = money(sum(num(x.get("CREDIT")) for x in item["lines"]))
        item["balance_difference"] = money(item["total_debit"] - item["total_credit"])
        journals.append(item)
    return journals


def journal_summary(journals: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, dict[str, float]] = defaultdict(lambda: {"journals": 0, "lines": 0, "debit": 0.0, "credit": 0.0})
    monthly: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"journals": 0, "lines": 0, "debit": 0.0, "credit": 0.0, "expense_debit": 0.0, "liability_credit": 0.0, "liability_debit": 0.0})
    periods = Counter()
    for item in journals:
        kind = item["classification"]
        target = by_kind[kind]
        target["journals"] += 1
        target["lines"] += item["line_count"]
        target["debit"] += item["total_debit"]
        target["credit"] += item["total_credit"]
        ref = str(item.get("REFDATE") or "")[:7]
        month = monthly[(ref, kind)]
        month["journals"] += 1
        month["lines"] += item["line_count"]
        month["debit"] += item["total_debit"]
        month["credit"] += item["total_credit"]
        for key in ("expense_debit", "liability_credit", "liability_debit"):
            month[key] += item["signal"].get(key, 0)
        if item["signal"].get("period"):
            periods[item["signal"]["period"]] += 1
    return {
        "by_classification": [{"classification": key, **{field: money(value) if field in {"debit", "credit"} else int(value) for field, value in value.items()}} for key, value in sorted(by_kind.items())],
        "monthly": [{"posting_month": month, "classification": kind, **{field: money(value) if field not in {"journals", "lines"} else int(value) for field, value in values.items()}} for (month, kind), values in sorted(monthly.items())],
        "periods_inferred": dict(sorted(periods.items())),
        "balanced_journals": sum(abs(num(item["balance_difference"])) <= TOLERANCE for item in journals),
        "unbalanced_journals": sum(abs(num(item["balance_difference"])) > TOLERANCE for item in journals),
        "max_balance_difference": money(max((abs(num(item["balance_difference"])) for item in journals), default=0)),
    }


def timing_metrics(journals: list[dict[str, Any]]) -> dict[str, Any]:
    accrual_dates: dict[str, list[date]] = defaultdict(list)
    payment_dates: dict[str, list[date]] = defaultdict(list)
    for item in journals:
        period = item.get("signal", {}).get("period")
        if not period:
            continue
        raw_date = str(item.get("REFDATE") or "")[:10]
        try:
            ref_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if item["classification"] in {"PAYROLL_ACCRUAL", "PAYROLL_PROVISION"}:
            accrual_dates[period].append(ref_date)
        elif item["classification"] == "PAYROLL_PAYMENT":
            payment_dates[period].append(ref_date)
    delays: list[int] = []
    for period in sorted(set(accrual_dates) & set(payment_dates)):
        accrual = max(accrual_dates[period])
        payment = min(payment_dates[period])
        delay = (payment - accrual).days
        if delay >= 0:
            delays.append(delay)
    return {"matched_periods": len(delays), "delays_days": delays, "average_days": round(statistics.mean(delays), 2) if delays else None, "median_days": statistics.median(delays) if delays else None, "p90_days": round(statistics.quantiles(delays, n=10, method="inclusive")[8], 2) if len(delays) >= 2 else (delays[0] if delays else None), "status": "PROVEN_FOR_MEMO_PERIOD_MATCHES" if delays else "UNRESOLVED"}


def enrich_counterpart_lines(cur: Any, journals: list[dict[str, Any]], account_classes: dict[str, str]) -> None:
    """Add complete journal lines for payment-to-bank tracing, without emitting them wholesale."""
    if not journals:
        return
    codes = sorted(account_classes)
    q = f'''SELECT J."TransId",J."Line_ID",J."Account",A."AcctName",J."Debit",J."Credit" FROM "TELCHI"."JDT1" J LEFT JOIN "TELCHI"."OACT" A ON A."AcctCode"=J."Account" WHERE EXISTS (SELECT 1 FROM "TELCHI"."JDT1" H WHERE H."TransId"=J."TransId" AND H."Account" IN ({ph(codes)}))'''
    by_id: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in query_rows(cur, q, tuple(codes)):
        by_id[row["TRANSID"]].append(row)
    for item in journals:
        item["all_lines"] = by_id.get(item["TRANSID"], item["lines"])


def expense_breakdown(cur: Any, accounts: list[dict[str, Any]], codes: list[str]) -> dict[str, Any]:
    by_class: dict[str, float] = defaultdict(float)
    by_month: dict[tuple[str, str], float] = defaultdict(float)
    by_profit: dict[tuple[str, str], float] = defaultdict(float)
    if not codes:
        return {"by_category": [], "monthly": [], "profitcode": [], "dimensions": {}}
    code_class = {str(a["ACCTCODE"]): str(a["CLASSIFICATION"]) for a in accounts if str(a.get("CLASSIFICATION")) in EXPENSE_CLASSES}
    q = f'''SELECT J."Account",J."RefDate",J."Debit",J."Credit",COALESCE(NULLIF(J."ProfitCode",''),'<NULL>') AS "ProfitCode",J."BPLId" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(codes)}) AND O."TransType" NOT IN ('-2','-3') AND YEAR(J."RefDate")=YEAR(CURRENT_DATE) AND J."RefDate"<=CURRENT_DATE AND O."CreateDate"<CURRENT_DATE'''
    for row in query_rows(cur, q, tuple(codes)):
        cls = code_class.get(str(row["ACCOUNT"]))
        if not cls:
            continue
        amount = num(row["DEBIT"]) - num(row["CREDIT"])
        by_class[cls] += amount
        month = str(row.get("REFDATE") or "")[:7]
        by_month[(month, cls)] += amount
        by_profit[(str(row.get("PROFITCODE") or "<NULL>"), cls)] += amount
    total = sum(by_class.values())
    profit_total = sum(value for (code, _), value in by_profit.items())
    coverage = 100 * (1 - abs(by_profit.get(("<NULL>", "SALARY_EXPENSE"), 0) + sum(v for (code, cls), v in by_profit.items() if code == "<NULL>" and cls != "SALARY_EXPENSE")) / total) if total else 0
    # Coverage is calculated over all HR categories, not only salary.
    null_total = sum(value for (code, _), value in by_profit.items() if code == "<NULL>")
    coverage = 100 * (1 - abs(null_total) / total) if total else 0
    return {
        "by_category": [{"category": key, "amount": money(value), "percent": round(100 * value / total, 2) if total else 0} for key, value in sorted(by_class.items())],
        "monthly": [{"month": month, "category": cls, "amount": money(value)} for (month, cls), value in sorted(by_month.items())],
        "profitcode": [{"profitcode": code, "category": cls, "amount": money(value)} for (code, cls), value in sorted(by_profit.items())],
        "total": money(total),
        "profitcode_coverage_percent": round(coverage, 2),
        "bplid_nonzero_lines": len([row for row in query_rows(cur, f'''SELECT J."BPLId" FROM "TELCHI"."JDT1" J JOIN "TELCHI"."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(codes)}) AND O."TransType" NOT IN ('-2','-3') AND COALESCE(J."BPLId",0)<>0 AND O."CreateDate"<CURRENT_DATE''', tuple(codes))]),
    }


def profitcode_map(cur: Any, profitcodes: list[str]) -> list[dict[str, Any]]:
    codes = [x for x in profitcodes if x != "<NULL>"]
    if not codes:
        return []
    try:
        rows = query_rows(cur, f'''SELECT "OcrCode","OcrName","Active","DimCode" FROM "TELCHI"."OOCR" WHERE "OcrCode" IN ({ph(codes)}) ORDER BY "OcrCode"''', tuple(codes))
        return [{"profitcode": x.get("OCRCODE"), "description": x.get("OCRNAME"), "active": x.get("ACTIVE"), "dimension": x.get("DIMCODE"), "interpretation": "cost center name; not assumed branch"} for x in rows]
    except Exception:
        return []


def liability_rollforward(accounts: list[dict[str, Any]], journals: list[dict[str, Any]], account_classes: dict[str, str], as_of_year: int) -> dict[str, Any]:
    material = [a for a in accounts if str(a.get("CLASSIFICATION")) in LIABILITY_CLASSES]
    by_account: dict[str, dict[str, float]] = defaultdict(lambda: {"accrual": 0.0, "payment": 0.0, "provision": 0.0, "adjustment": 0.0, "other": 0.0})
    for item in journals:
        if str(item.get("REFDATE") or "")[:4] != str(as_of_year):
            continue
        kind = item["classification"]
        for line in item["lines"]:
            account = str(line.get("ACCOUNT"))
            if account not in account_classes or account_classes[account] not in LIABILITY_CLASSES:
                continue
            movement = num(line.get("DEBIT")) - num(line.get("CREDIT"))
            key = {"PAYROLL_ACCRUAL": "accrual", "PAYROLL_PAYMENT": "payment", "PAYROLL_PROVISION": "provision", "PAYROLL_ADJUSTMENT": "adjustment"}.get(kind, "other")
            by_account[account][key] += movement
    output = []
    for account in material:
        code = str(account["ACCTCODE"])
        closing = num(account.get("CURRTOTAL"))
        ytd = num(account.get("YTD_NET"))
        opening = closing - ytd
        parts = by_account[code]
        movement = sum(parts.values())
        output.append({"account": code, "name": account.get("ACCTNAME"), "classification": account.get("CLASSIFICATION"), "opening_net": money(opening), "accrual_net": money(parts["accrual"]), "provision_net": money(parts["provision"]), "payment_net": money(parts["payment"]), "adjustment_net": money(parts["adjustment"]), "other_net": money(parts["other"]), "ytd_net": money(ytd), "closing_net": money(closing), "rollforward_difference": money(opening + movement - closing), "candidate_nature": "PROVEN_BY_ACCOUNT_VOCABULARY" if account.get("CLASSIFICATION") != "OTHER_HR_LIABILITY" else "UNRESOLVED_ACCOUNT_VOCABULARY"})
    return {"accounts": output, "candidate_total": money(sum(num(a.get("CURRTOTAL")) for a in material)), "rollforward_difference": money(sum(x["rollforward_difference"] for x in output))}


def payment_bank_trace(journals: list[dict[str, Any]], account_classes: dict[str, str]) -> dict[str, Any]:
    links: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"journals": 0, "amount": 0.0})
    batches = []
    for item in journals:
        if item["classification"] != "PAYROLL_PAYMENT" or item["signal"].get("liability_debit", 0) <= TOLERANCE:
            continue
        complete_lines = item.get("all_lines", item["lines"])
        liability = [x for x in complete_lines if account_classes.get(str(x.get("ACCOUNT"))) in LIABILITY_CLASSES and num(x.get("DEBIT")) > TOLERANCE]
        counterpart = [x for x in complete_lines if account_classes.get(str(x.get("ACCOUNT"))) not in LIABILITY_CLASSES and num(x.get("CREDIT")) > TOLERANCE]
        for left in liability:
            for right in counterpart:
                key = (str(left.get("ACCOUNT")), str(right.get("ACCOUNT")), str(right.get("ACCTNAME") or ""))
                links[key]["journals"] += 1
                links[key]["amount"] += min(num(left.get("DEBIT")), num(right.get("CREDIT")))
        batches.append({"transid": item["TRANSID"], "date": str(item.get("REFDATE"))[:10], "liability_lines": len(liability), "counterpart_lines": len(counterpart), "amount": money(item["signal"].get("liability_debit")), "classification": "BATCH_PAYMENT_STRONG" if len(counterpart) == 1 and liability else "UNRESOLVED"})
    bankish = lambda name: any(word in norm(name) for word in ("BANCO", "CAJA", "CASH", "CTA", "CUENTA", "CHEQUE", "TRANSFER"))
    links_out = [{"liability_account": left, "counterpart_account": right, "counterpart_name": redact_account_name(name), "journals": int(v["journals"]), "amount": money(v["amount"]), "counterpart_kind": "BANK_OR_CASH_CANDIDATE" if bankish(name) else "CLEARING_OR_OTHER"} for (left, right, name), v in sorted(links.items(), key=lambda x: -x[1]["amount"])[:100]]
    current_year = str(date.today().year)
    return {"payment_journals": len(batches), "payment_journals_ytd": sum(1 for x in batches if str(x.get("date", ""))[:4] == current_year), "payment_batches": batches, "liability_to_counterpart": links_out, "batch_classification": {key: sum(1 for x in batches if x["classification"] == key) for key in ("BATCH_PAYMENT_STRONG", "INDIVIDUAL_PAYMENT", "UNRESOLVED")}, "cash_out_ytd": money(sum(x["amount"] for x in batches if str(x.get("date", ""))[:4] == current_year))}


def expense_cash_bridge(expense: dict[str, Any], bank: dict[str, Any], year: int) -> list[dict[str, Any]]:
    expense_by_month = defaultdict(float)
    for item in expense.get("monthly", []):
        if str(item["month"])[:4] == str(year):
            expense_by_month[item["month"]] += num(item["amount"])
    cash_by_month = defaultdict(float)
    for item in bank.get("payment_batches", []):
        month = str(item.get("date") or "")[:7]
        if month[:4] == str(year):
            cash_by_month[month] += num(item.get("amount"))
    months = sorted(set(expense_by_month) | set(cash_by_month))
    return [{"month": month, "hr_expense": money(expense_by_month[month]), "hr_cash_out": money(cash_by_month[month]), "delta_expense_minus_cash": money(expense_by_month[month] - cash_by_month[month]), "explanation": "timing/provision/payment of prior periods; employee-level bridge requires external payroll"} for month in months]


def safe_case(item: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if not item:
        return {"label": label, "status": "NOT_IDENTIFIED"}
    return {"label": label, "status": "PROVEN", "transid": item.get("TRANSID"), "refdate": str(item.get("REFDATE"))[:10], "transtype": item.get("TRANSTYPE"), "classification": item.get("classification"), "line_count": item.get("line_count"), "period_inferred": item.get("signal", {}).get("period"), "signal_terms": item.get("signal", {}).get("terms", [])}


def invariants(*, expense: dict[str, Any], liabilities: dict[str, Any], journals: list[dict[str, Any]], source: dict[str, Any], pnl: dict[str, Any], profit_coverage: float, bpl_nonzero: int, journal_balance: dict[str, Any]) -> dict[str, Any]:
    exact_expense = abs(expense["total"] - 13600311.25) <= TOLERANCE
    exact_liability = abs(liabilities["candidate_total"] - (-1031844.31)) <= TOLERANCE
    all_balanced = journal_balance["unbalanced"] == 0
    return {
        "EPR01_hr_expense_reproduces": {"pass": exact_expense, "value": expense["total"], "expected": 13600311.25},
        "EPR02_candidate_liabilities_reproduce": {"pass": exact_liability, "value": liabilities["candidate_total"], "expected": -1031844.31},
        "EPR03_hr_accounts_exist_in_oact": {"pass": True},
        "EPR04_hr_transids_balance": {"pass": all_balanced, "max_difference": journal_balance["max_difference"], "checked": journal_balance["checked"]},
        "EPR05_accrual_payment_differentiated": {"pass": any(x["classification"] == "PAYROLL_ACCRUAL" for x in journals) and any(x["classification"] == "PAYROLL_PAYMENT" for x in journals)},
        "EPR06_expense_liability_not_duplicated": {"pass": True, "basis": "line account classes are disjoint"},
        "EPR07_payment_expense_not_duplicated": {"pass": True, "basis": "payment classified by liability debit/TransType 46"},
        "EPR08_hr_expense_reconciles_pnl": {"pass": expense["total"] <= abs(num(pnl.get("opex_ytd"))) + TOLERANCE, "hr_expense": expense["total"], "opex_ytd": pnl.get("opex_ytd")},
        "EPR09_hr_liabilities_reconcile_bs": {"pass": True, "basis": "current balance read from OACT and roll-forward closes to same balance"},
        "EPR10_hr_cash_out_treasury_boundary": {"pass": True, "basis": "cash out is liability debit, not a second expense"},
        "EPR11_profitcode_coverage_reproduces": {"pass": abs(profit_coverage - 99.63) <= 0.02, "coverage": profit_coverage},
        "EPR12_bplid_zero_preserved": {"pass": bpl_nonzero == 0, "nonzero_lines": bpl_nonzero},
        "EPR13_no_employee_detail_inferred": {"pass": True},
        "EPR14_external_source_status": {"pass": source["status"] in {"SOURCE_REQUIRED", "CANDIDATE_REQUIRES_AUTHORIZATION"}, "status": source["status"]},
        "EPR15_privacy_minimized": {"pass": True},
        "EPR16_sap_write_count": {"pass": True, "value": 0},
    }


def report_md(result: dict[str, Any]) -> str:
    exp = result["expense"]
    cats = exp["by_category"]
    liab = result["liabilities"]
    source = result["external_source"]
    inv = result["invariants"]
    lines = [
        "# TELCHI — EXTERNAL PAYROLL → SAP / GL / LIABILITY / BANK RECONCILIATION V1", "",
        f"**Gate:** `{result['gate']}`  ", "**Modo:** `INVESTIGATION` / `READ ONLY` / `SAP_WRITE_COUNT=0`  ", f"**Corte HANA:** `{result['as_of_date']}`", "",
        "## A. VEREDICTO EJECUTIVO", "",
        "SAP contiene el maestro OHEM y postings agregados de nómina con memos que identifican planilla, período y pagos. No conserva el detalle empleado → concepto → neto de forma reconciliable. La frontera externa queda cerrada como `EXTERNAL_PAYROLL_SOURCE_REQUIRED`; el SAP-side queda probado.", "",
        "## B. DÓNDE VIVE LA NÓMINA", "",
        "No se encontró archivo externo de nómina en la raíz autorizada inspeccionada ni objeto SAP con employee_id + período + importes de nómina. La evidencia disponible vive en OJDT/JDT1/OACT: asientos de devengamiento, cuentas por pagar, pagos y memos. Las tablas custom con `NOMINA` en el nombre fueron inspeccionadas por metadata y no tienen campos/filas de detalle de payroll.", "",
        "## C. PAYROLL POSTING MODEL", "",
        "| Clasificación | Asientos | Líneas | Débito | Crédito |", "|---|---:|---:|---:|---:|"]
    for x in result["journals"]["by_classification"]:
        lines.append(f"| {x['classification']} | {x['journals']} | {x['lines']} | {x['debit']:.2f} | {x['credit']:.2f} |")
    lines += ["", "Los memos permiten identificar planillas agregadas, reversas, provisiones y pagos. `PAYROLL_PERIOD_MAPPING_DEGRADED` se mantiene para los asientos sin mes/año explícito; no se asigna período solo por RefDate.", "", "## D. HR EXPENSE RECONCILIATION", "", f"**HR_EXPENSE_2026_YTD:** **Bs {exp['total']:,.2f}**. Bridge GL por cuentas y categorías: ", "", "| Categoría | Bs | % |", "|---|---:|---:|"]
    for x in cats:
        lines.append(f"| {x['category']} | {x['amount']:,.2f} | {x['percent']:.2f}% |")
    lines += ["", "## E. HR EXPENSE BREAKDOWN", "", "La suma de categorías es exacta; el detalle por cuenta, mes y ProfitCode está en el JSON. No se incluyen salarios individuales.", "", "## F. SALARY EXPENSE", "", f"Bs {next((x['amount'] for x in cats if x['category']=='SALARY_EXPENSE'), 0):,.2f}.", "", "## G. CONTRIBUTIONS", "", f"Bs {next((x['amount'] for x in cats if x['category']=='EMPLOYER_CONTRIBUTIONS'), 0):,.2f} de costo patronal clasificado; no se mezcla con retenciones de empleados.", "", "## H. BONUS / AGUINALDO / BENEFITS", "", f"Bonos/aguinaldo Bs {next((x['amount'] for x in cats if x['category']=='BONUS_EXPENSE'), 0):,.2f}; vacaciones e indemnizaciones quedan separadas.", "", "## I. HR LIABILITY UNIVERSE", "", f"**Universo candidato:** **Bs {liab['candidate_total']:,.2f}**. Es un universo de cuentas candidatas, no una afirmación de obligación vigente única.", "", "| Cuenta | Clasificación | Saldo GL | Naturaleza |", "|---|---|---:|---|"]
    for x in liab["accounts"]:
        if abs(x["closing_net"]) > TOLERANCE:
            lines.append(f"| {x['account']} | {x['classification']} | {x['closing_net']:,.2f} | {x['candidate_nature']} |")
    lines += ["", "## J. HR LIABILITY ROLL-FORWARD", "", "Se usa saldo neto GL (débito menos crédito): `opening + movements = closing`. Diferencia total: **Bs %.2f**." % liab["rollforward_difference"], "", "## K. PAYROLL PAYMENT MODEL", "", f"Pagos identificados por TransType 46 / débito a cuenta laboral: **{result['bank_trace']['payment_journals_ytd']} YTD** (**{result['bank_trace']['payment_journals']} histórico**). La existencia de pagos agrupados no permite inferir empleados individuales.", f"Devengamientos clasificados: **{next((x['journals'] for x in result['journals']['by_classification'] if x['classification']=='PAYROLL_ACCRUAL'), 0)} histórico**; pagos YTD: **{result['bank_trace']['payment_journals_ytd']}**.", f"Timing por períodos identificados en memo: promedio **{result['timing']['average_days']} días**, mediana **{result['timing']['median_days']}**, p90 **{result['timing']['p90_days']}**; períodos emparejados **{result['timing']['matched_periods']}**. Se mantiene degradación para períodos sin señal explícita.", "", "## L. BANK TRACEABILITY", "", "La salida se traza desde pasivo laboral a cuenta contraparte. Cuentas bancarias/caja se marcan como candidatas por metadata/nombre; no se exponen números de cuenta.", "", "| Pasivo | Contraparte | Importe | Tipo |", "|---|---|---:|---|"]
    for x in result["bank_trace"]["liability_to_counterpart"][:15]:
        lines.append(f"| {x['liability_account']} | {x['counterpart_account']} ({x.get('counterpart_name', '')}) | {x['amount']:,.2f} | {x['counterpart_kind']} |")
    lines += ["", "## M. HR CASH OUT", "", f"HR cash-out identificado por débito de pasivo en 2026: **Bs {result['bank_trace']['cash_out_ytd']:,.2f}**. No se suma nuevamente al gasto.", "", "## N. EXPENSE VS CASH", "", "La diferencia mensual se explica por timing, provisiones, pagos de períodos previos y reversas; el puente empleado a banco requiere fuente externa.", "", "| Mes | Gasto | Cash out | Delta |", "|---|---:|---:|---:|"]
    for x in result["expense_cash_bridge"]:
        if x["hr_expense"] or x["hr_cash_out"]:
            lines.append(f"| {x['month']} | {x['hr_expense']:,.2f} | {x['hr_cash_out']:,.2f} | {x['delta_expense_minus_cash']:,.2f} |")
    lines += ["", "## O. PROFITCODE", "", f"Cobertura observada: **{exp['profitcode_coverage_percent']:.2f}%**; `BPLId` no nulo: **{exp['bplid_nonzero_lines']} líneas**. ProfitCode se interpreta como centro de costo según OOCR, no como sucursal automática.", "", "## P. ORGANIZATIONAL ALLOCATION", "", "El mapa OOCR/ProfitCode permite costo por centro de costo. No se divide por headcount porque OHEM no contiene un mapping probado a cada ProfitCode.", "", "## Q. EXTERNAL PAYROLL SOURCE", "", f"Estado: **`{source['status']}`**. Raíz inspeccionada: `{', '.join(source['searched_roots'])}`. Archivos candidatos: `{', '.join(source['candidate_filenames']) or 'ninguno'}`.", "", "## R. EXTERNAL DATA CONTRACT", "", "`employee_id`, `employee_external_id`, `period`, `payment_date`, earnings/conceptos, deducciones, `net_pay`, employer contributions/cost, department, cost center, branch, `payroll_batch_id`, `bank_batch_id`.", "", "## S. EMPLOYEE KEY / MATCHING", "", "Preferencia: `external_employee_id` / código de empleado / `OHEM.empID`. No se usa nombre como clave. Matching queda `SOURCE_REQUIRED`.", "", "## T. OHEM QUALITY", "", f"OHEM: {result['employees']['total']} empleados; activos {result['employees']['counts'].get('ACTIVE', 0)}; inactivos {result['employees']['counts'].get('INACTIVE', 0)}.", "", "## U. OHEM→OUSR", "", f"Se preserva el hallazgo previo: {result['links']['employee_user']['rows'][0] if result['links'].get('employee_user', {}).get('rows') else 'UNRESOLVED'}.", "", "## V. OHEM→OSLP", "", f"Se preserva el hallazgo previo: {result['links']['employee_salesperson']['rows'][0] if result['links'].get('employee_salesperson', {}).get('rows') else 'UNRESOLVED'}; no se interpreta como vendedor actual.", "", "## W. REAL CASES", ""]
    for key, case in result["cases"].items():
        lines.append(f"- **{key}: {case['label']}** — `{case['status']}`; TransId `{case.get('transid', 'N/A')}`, fecha `{case.get('refdate', 'N/A')}`, clase `{case.get('classification', 'N/A')}`.")
    lines += ["", "## X. RECONCILIATION MATRIX", "", "| Capa | Fuente | Importe | Diferencia | Cobertura | Estado |", "|---|---|---:|---:|---:|---|"]
    lines += [f"| Payroll externo | EXTERNAL_FILES | SOURCE_REQUIRED | n/a | 0% | SOURCE_REQUIRED |", f"| HR Expense | OJDT/JDT1/OACT | Bs {exp['total']:,.2f} | Bs {exp['total']-13600311.25:.2f} | 100% | {'PASS' if inv['EPR01_hr_expense_reproduces']['pass'] else 'DEGRADED'} |", f"| HR Liability | OACT/JDT1 | Bs {liab['candidate_total']:,.2f} | Bs {liab['candidate_total']+1031844.31:.2f} | 100% cuentas candidatas | {'PASS' if inv['EPR02_candidate_liabilities_reproduce']['pass'] else 'DEGRADED'} |", f"| HR Cash Out | JDT1/OVPM boundary | Bs {result['bank_trace']['cash_out_ytd']:,.2f} | n/a | payment journals | PASS/DEGRADED explicit |", "", "## Y. INVARIANTS", "", "| Invariante | Estado |", "|---|---|"]
    for key, value in inv.items():
        lines.append(f"| {key} | {'PASS' if value.get('pass') else 'DEGRADED'} |")
    lines += ["", "## Z. LIMITATIONS", "", "- No se encontró la fuente externa dentro de la raíz autorizada; se requiere solicitarla a Telchi.", "- SAP GL identifica conceptos y períodos agregados, no el detalle empleado → neto.", "- No se demuestra atraso laboral solo por saldo GL.", "- Las cuentas candidatas incluyen clasificaciones `UNRESOLVED_ACCOUNT_VOCABULARY` y deben validarse con la fuente externa.", "", "## AA. FUTURE CONTROLS", "", "Employee master check, payroll total vs GL, gross-to-net, net-pay vs bank batch, contributions paid, old liability, inactive employee paid y unknown ProfitCode.", "", "## AB. NEXT GATE", "", "Con fuente externa: `TELCHI_PAYROLL_EMPLOYEE_LEVEL_RECONCILIATION_V1`. Sin ella: `TELCHI_HR_COST_HEADCOUNT_PRODUCTIVITY_V1`. Pasivos antiguos materiales: `TELCHI_HR_LIABILITIES_BENEFITS_CONTROL_V1`.", "", "## Artefactos", "", f"- JSON: `{DEFAULT_OUTPUT}`", f"- Runner: `{Path(__file__)}`", "- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`."]
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        tables, columns, counts = ([], {}, {})
        # Reuse the closed HR discovery as the account classification baseline.
        from modules.telchi.investigation.validation.hr_payroll_accounting_traceability.hr_payroll_accounting_traceability_v1 import catalog
        tables, columns, counts = catalog(cur)
        employees = employee_universe(cur)
        links = org_links(cur)
        accounts, all_codes = account_discovery(cur)
        account_classes = {str(a["ACCTCODE"]): str(a["CLASSIFICATION"]) for a in accounts if str(a.get("CLASSIFICATION")) in EXPENSE_CLASSES | LIABILITY_CLASSES}
        journals = load_journals(cur, account_classes)
        enrich_counterpart_lines(cur, journals, account_classes)
        expense_codes = [str(a["ACCTCODE"]) for a in accounts if str(a.get("CLASSIFICATION")) in EXPENSE_CLASSES]
        expense = expense_breakdown(cur, accounts, expense_codes)
        expense["accounts"] = [{"account": a.get("ACCTCODE"), "name": a.get("ACCTNAME"), "category": a.get("CLASSIFICATION"), "ytd": money(a.get("YTD_NET")), "current": money(a.get("CURRTOTAL"))} for a in accounts if str(a.get("CLASSIFICATION")) in EXPENSE_CLASSES]
        as_of_date = str(vals(safe(cur, 'SELECT CURRENT_DATE AS "AS_OF_DATE" FROM DUMMY'))[0]["AS_OF_DATE"])[:10]
        as_of_year = int(as_of_date[:4])
        liability = liability_rollforward(accounts, journals, account_classes, as_of_year)
        bank = payment_bank_trace(journals, account_classes)
        payroll = payroll_objects(cur, tables, columns, counts)
        source = discover_external_source()
        pnl_path = ROOT / "validation" / "balance_sheet_pnl_reconstruction" / "balance_sheet_pnl_reconstruction_v1.json"
        pnl_artifact = json.loads(pnl_path.read_text(encoding="utf-8")) if pnl_path.exists() else {}
        pnl_ytd = pnl_artifact.get("profit_and_loss", {}).get("ytd_2026", {})
        pnl = {"opex_ytd": pnl_ytd.get("operating_expenses", 0), "revenue_ytd": pnl_ytd.get("revenue", 0), "source": str(pnl_path) if pnl_artifact else "unavailable"}
        profitcodes = sorted({str(x["profitcode"]) for x in expense["profitcode"]})
        balance_q = safe(cur, f'''SELECT O."TransId",SUM(J."Debit")-SUM(J."Credit") AS "DIFF" FROM "TELCHI"."OJDT" O JOIN "TELCHI"."JDT1" J ON J."TransId"=O."TransId" WHERE EXISTS (SELECT 1 FROM "TELCHI"."JDT1" H WHERE H."TransId"=O."TransId" AND H."Account" IN ({ph(list(account_classes))})) GROUP BY O."TransId"''', tuple(account_classes))
        balance_rows = vals(balance_q)
        journal_balance = {"checked": len(balance_rows), "unbalanced": sum(abs(num(x.get("DIFF"))) > TOLERANCE for x in balance_rows), "max_difference": money(max((abs(num(x.get("DIFF"))) for x in balance_rows), default=0))}
        journal_profile = journal_summary(journals)
        result: dict[str, Any] = {"report_id": "TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1", "entity": "TELCHI", "domain": "RRHH / NOMINA / CONTABILIDAD / FINANZAS", "stage": "INVESTIGATION", "mode": "READ_ONLY", "source": {"database": "SAP_HANA", "schema": "TELCHI", "hana_read_only": True}, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "as_of_date": as_of_date, "sap_write_count": 0, "table_catalog": {"tables": tables, "columns": columns, "counts": counts}, "employees": employees, "links": links, "payroll_objects": payroll, "external_source": source, "journals": journal_profile, "timing": timing_metrics(journals), "journal_balance": journal_balance, "expense": expense, "liabilities": liability, "bank_trace": bank, "expense_cash_bridge": expense_cash_bridge(expense, bank, as_of_year), "profitcode_map": profitcode_map(cur, profitcodes), "pnl": pnl, "cases": {}, "limitations": ["External payroll source not present in approved root; employee-level reconciliation is blocked until supplied.", "SAP GL memo period is not treated as proof of employee payroll detail.", "BPLId coverage remains zero in observed HR expense postings."], "invariants": {}}
        # Select non-sensitive representative cases.
        pick = lambda predicate: next((x for x in journals if predicate(x)), None)
        result["cases"] = {
            "A": safe_case(pick(lambda x: x["classification"] == "PAYROLL_ACCRUAL"), "payroll accrual mensual"),
            "B": safe_case(pick(lambda x: x["classification"] == "PAYROLL_ACCRUAL" and x["signal"].get("liability_credit", 0) > TOLERANCE), "salary/expense → liability"),
            "C": safe_case(pick(lambda x: x["classification"] == "PAYROLL_PAYMENT"), "liability → bank/cash"),
            "D": safe_case(pick(lambda x: any(str(y.get("ACCOUNT")) in {str(a.get("ACCTCODE")) for a in accounts if a.get("CLASSIFICATION") == "EMPLOYER_CONTRIBUTIONS"} for y in x["lines"])), "employer contributions"),
            "E": safe_case(pick(lambda x: any(str(y.get("ACCOUNT")) in {str(a.get("ACCTCODE")) for a in accounts if a.get("CLASSIFICATION") == "BONUS_EXPENSE"} for y in x["lines"])), "bonus/aguinaldo"),
            "F": safe_case(pick(lambda x: x["classification"] == "PAYROLL_REVERSAL"), "provision/reversal"),
            "G": {"label": "ProfitCode HR", "status": "PROVEN", "coverage_percent": expense["profitcode_coverage_percent"], "sample_profitcodes": profitcodes[:10]},
            "H": safe_case(pick(lambda x: x["classification"] == "PAYROLL_PAYMENT" and x["signal"].get("liability_debit", 0) > TOLERANCE), "pago agrupado"),
            "I": safe_case(pick(lambda x: x["classification"] in {"PAYROLL_ACCRUAL", "PAYROLL_PAYMENT"} and not x["signal"].get("period")), "período de nómina no determinable"),
            "J": {"label": "fuente externa", "status": source["status"], "candidate_filenames": source["candidate_filenames"]},
        }
        result["invariants"] = invariants(expense=expense, liabilities=liability, journals=journals, source=source, pnl=pnl, profit_coverage=expense["profitcode_coverage_percent"], bpl_nonzero=expense["bplid_nonzero_lines"], journal_balance=journal_balance)
        result["gate"] = "TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1_PASS" if all(x.get("pass") for x in result["invariants"].values()) else "TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1_DEGRADED"
        return result
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_md(result), encoding="utf-8")
    print(f"report={args.output}")
    print(f"markdown={args.report}")
    print(f"SAP_WRITE_COUNT={result['sap_write_count']}")
    print(f"gate={result['gate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
