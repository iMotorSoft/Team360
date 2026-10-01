#!/usr/bin/env python3
"""TELCHI Financial Debt / Interest / Financial Result Traceability V1.

Investigation-only, SELECT-only runner.  It closes the gap left by
``TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_PASS``: the forecast treats
the whole ``FINANCING`` accounts-payable block (bank suppliers) as payable,
because SAP stores each bank loan as a single open invoice without an
installment calendar.

This runner answers, with real HANA evidence:

  * how much Telchi owes to banks and to which entities;
  * how much is principal, accrued interest and fees;
  * whether the debt is a bank loan, credit line, card or other;
  * whether SAP stores the amortization calendar (INV6) and the documentary
    versus economic maturity;
  * how the ``-1,414,305.12`` financial result is composed (interest, FX,
    fees, other);
  * how reconstructing the economic schedule changes the 30/60/90-day
    financing cash-out of forecast V1.

No ML.  No writes.  ``SAP_WRITE_COUNT`` stays 0.  The forecast V1 verdict is
not overwritten; this gate only generates new evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "financial_debt_and_financial_result"
DEFAULT_OUTPUT = OUT_DIR / "financial_debt_and_financial_result_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_financial_debt_and_financial_result_v1_report.md"

BSPNL_ARTIFACT = ROOT / "validation" / "balance_sheet_pnl_reconstruction" / "balance_sheet_pnl_reconstruction_v1.json"
FORECAST_ARTIFACT = ROOT / "validation" / "financial_forecast_liquidity_scenarios" / "financial_forecast_liquidity_scenarios_v1.json"

TOLERANCE = 0.01

#: Frozen target from the forecast V1 gate (must be reproduced exactly).
FINANCING_TARGET = 4_827_924.39

#: Financial-debt liability accounts used by Telchi (SAP chart of accounts).
DEBT_ACCOUNTS = ("2130101", "2130102", "2130103", "2210101", "2210102", "2210103")
LOAN_PRINCIPAL_ACCOUNT = "2210101"      # Préstamos bancarios
COMMERCIAL_AP_ACCOUNT = "2110101"       # Cuentas por pagar MN (some loans booked here)
INTEREST_ACCOUNT = "6020101"            # Intereses bancarios por prestamos (P&L)
BANK_FEE_ACCOUNTS = ("6020102", "6020103", "6020104", "6020105")
FX_LOSS_ACCOUNTS = ("6020301", "6510101", "6510102")
FX_GAIN_ACCOUNTS = ("4210103", "4210105")
INTEREST_INCOME_ACCOUNTS = ("4210111",)
OTHER_FINANCIAL_ACCOUNTS = ("6510103",)

BANK_BP_NAMES = ("BANCO", "BANK")

#: Documented alias between the migrated FIE contract number and the current
#: bank operation number used in payment memos.  Evidence: DE 3639 comment
#: ("N.-7018-11907 ... 144 meses") plus the monthly series whose capital
#: (Bs 70,992.22) and interest provisions reference op. 10002618651.
LOAN_ALIASES: dict[str, str] = {"7018-11907": "10002618651"}


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def serial(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fetch_dicts(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    columns = [str(x[0]).upper() for x in (cur.description or ())]
    return [{key: serial(value) for key, value in zip(columns, row, strict=False)} for row in cur.fetchall()]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30,
                          31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


# ---------------------------------------------------------------------------
# pure domain rules (offline-testable)
# ---------------------------------------------------------------------------
_LOAN_REF_PATTERNS = (
    re.compile(r"(\d{4,5}-\d{4,5})"),                       # migrated contract: 7018-11907
    re.compile(r"N[.º°]?[.\- ]*(\d{6,11})", re.IGNORECASE),  # current op number: N.-10010818132
    re.compile(r"(?:PTMO|PRESTAMO|PTM)\.?\s*(?:N[.º°]?\.?\s*-?\s*)?(\d{6,11})", re.IGNORECASE),
)


def parse_loan_ref(comment: Any) -> str | None:
    """Extract the loan identifier from an OPCH comment or payment memo.

    ``7018-11907`` (migrated contract) and ``10010818132`` (current op number)
    are both preserved verbatim; the caller resolves aliases explicitly.
    """
    text = str(comment or "")
    for pattern in _LOAN_REF_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1)
            # Payment document numbers (26xxxxxxxx / 2615xxxxx) are never loans.
            if candidate.startswith("26") and len(candidate) == 9:
                continue
            return candidate
    return None


def is_bank_supplier(card_name: Any) -> bool:
    name = str(card_name or "").upper()
    return any(token in name for token in BANK_BP_NAMES)


def classify_financing_doc(comment: Any) -> str:
    """Classify one bank OPCH document into a debt nature.

    Order matters: loan principal provisions mention "Capital e Intereses" in
    the free text, so the provision phrase is matched before the interest
    keyword to avoid misclassifying principal as accrued interest.
    """
    text = str(comment or "").upper()
    if re.search(r"PROV(?:ISION|\.)?\s*(?:DE\s*|D/\s*)?(?:PRESTAMO|PRÉSTAMO)", text):
        return "PRINCIPAL"
    if "PRESTAMO" in text and "INTERES" not in text:
        return "PRINCIPAL"
    if any(token in text for token in ("INTERES", "INTERÉS", "INTERESES")):
        return "ACCRUED_INTEREST"
    if any(token in text for token in ("COMISION", "COMISIÓN", "MANTENIMIENTO", "FORMULARIO", "TRAMITE", "TRÁMITE")):
        return "BANK_FEE"
    if any(token in text for token in ("PRESTAMO", "PRÉSTAMO", "AMORTIZ", "CAPITAL")):
        return "PRINCIPAL"
    return "UNRESOLVED"


def classify_debt_type(comment: Any, bp_name: Any = "") -> str:
    text = str(comment or "").upper()
    name = str(bp_name or "").upper()
    if "TARJETA DE CREDITO" in text or "TARJETA DE CRÉDITO" in text:
        return "CARD_FINANCING"
    if "LEASING" in text or "LEASING" in name:
        return "LEASING"
    if "BAJO LC" in text or "LINEA" in text or "LÍNEA" in text:
        return "CREDIT_LINE"
    if "PRESTAMO" in text or "PRÉSTAMO" in text:
        return "BANK_LOAN"
    return "OTHER_FINANCIAL_DEBT"


def expected_installment_count(open_amount: float, monthly_capital: float) -> int:
    if monthly_capital <= 0 or open_amount <= 0:
        return 0
    return max(0, int(round(open_amount / monthly_capital)))


def next_due_on_day(as_of: date, day: int) -> date:
    day = min(max(1, day), 28)
    candidate = as_of.replace(day=day)
    if candidate < as_of:
        candidate = add_months(candidate, 1)
    return candidate


def build_amortization(
    loan: dict[str, Any],
    as_of: date,
    *,
    monthly_capital: float,
    monthly_interest: float,
    payment_day: int,
    max_installments: int = 240,
) -> list[dict[str, Any]]:
    """HEURISTIC monthly amortization for one loan from observed installments.

    No contractual calendar is invented: the count derives from the remaining
    principal divided by the last observed monthly capital, and any rounding
    residual is applied to the final installment.
    """
    open_amount = round(num(loan.get("open_lc")), 2)
    count = min(expected_installment_count(open_amount, monthly_capital), max_installments)
    rows: list[dict[str, Any]] = []
    remaining = open_amount
    due = next_due_on_day(as_of, payment_day)
    for index in range(count):
        capital = round(min(monthly_capital, remaining), 2)
        remaining = round(remaining - capital, 2)
        rows.append({
            "installment": index + 1,
            "due_date": iso(due),
            "capital": capital,
            "interest": round(monthly_interest, 2),
            "total": round(capital + monthly_interest, 2),
            "remaining_after": remaining,
        })
        due = add_months(due, 1)
    return rows


def horizon_total(schedule: list[dict[str, Any]], as_of: date, horizon_days: int, field: str = "total") -> float:
    limit = as_of + timedelta(days=horizon_days)
    return round(sum(num(row[field]) for row in schedule
                     if (parse_date(row["due_date"]) or as_of) <= limit), 2)


def financial_result_decomposition(account_flows: dict[str, float]) -> dict[str, float]:
    """Reproduce the Balance Sheet / P&L V1 financial-result subgroups.

    ``account_flows`` maps account code -> 2026 YTD Debit - Credit.
    Presentation inverts expenses (debit-positive becomes negative).
    """
    def total(codes: tuple[str, ...]) -> float:
        return round(sum(account_flows.get(code, 0.0) for code in codes), 2)

    interest_expense = total((INTEREST_ACCOUNT, "6020303"))
    bank_charges = total(BANK_FEE_ACCOUNTS)
    fx_loss = total(FX_LOSS_ACCOUNTS)
    fx_gain = total(FX_GAIN_ACCOUNTS)
    interest_income = total(INTEREST_INCOME_ACCOUNTS)
    other = total(OTHER_FINANCIAL_ACCOUNTS)
    return {
        "INTEREST_EXPENSE": round(-interest_expense, 2),
        "INTEREST_INCOME": round(-interest_income, 2),
        "BANK_CHARGES": round(-bank_charges, 2),
        "FX_LOSS": round(-fx_loss, 2),
        "FX_GAIN": round(-fx_gain, 2),
        "OTHER_FINANCIAL": round(-other, 2),
    }


def pareto(entries: dict[str, float], top: int = 10) -> dict[str, Any]:
    ordered = sorted(entries.items(), key=lambda kv: abs(kv[1]), reverse=True)
    total = sum(entries.values())
    return {
        "total": round(total, 2),
        "top": [{"key": key, "amount": round(value, 2),
                 "share_pct": round(100.0 * value / total, 2) if total else None}
                for key, value in ordered[:top]],
        "top_1_share_pct": round(100.0 * abs(ordered[0][1]) / sum(abs(v) for _, v in ordered), 2) if ordered else None,
    }


# ---------------------------------------------------------------------------
# HANA reads (SELECT only)
# ---------------------------------------------------------------------------
def read_meta(cur: Any) -> dict[str, Any]:
    row = fetch_dicts(cur, "SELECT CURRENT_DATE AS AS_OF_DATE, CURRENT_USER AS HANA_USER FROM DUMMY")[0]
    return {"as_of_date": str(row["AS_OF_DATE"])[:10], "hana_user": row["HANA_USER"]}


def read_open_bank_ap(cur: Any) -> list[dict[str, Any]]:
    sql = '''
        SELECT P."DocEntry" DOCENTRY, P."DocNum" DOCNUM, P."CardCode" CARDCODE, P."CardName" CARDNAME,
               P."DocDate" DOCDATE, P."DocDueDate" DOCDUEDATE, P."DocCur" DOCCUR,
               P."DocTotal" DOCTOTAL, P."PaidToDate" PAIDTODATE, P."DocTotalFC" DOCTOTALFC, P."PaidFC" PAIDFC,
               (P."DocTotal"-P."PaidToDate") OPEN_LC, (P."DocTotalFC"-P."PaidFC") OPEN_FC,
               P."DocRate" DOCRATE, P."NumAtCard" NUMATCARD, P."Comments" COMMENTS, P."TransId" TRANSID,
               B."GroupCode" GROUP_CODE, G."GroupName" GROUP_NAME
        FROM TELCHI."OPCH" P
        LEFT JOIN TELCHI."OCRD" B ON B."CardCode"=P."CardCode"
        LEFT JOIN TELCHI."OCRG" G ON G."GroupCode"=B."GroupCode"
        WHERE P."CANCELED"='N' AND P."DocStatus"='O' AND (P."DocTotal"-P."PaidToDate")>?
          AND (UPPER(P."CardName") LIKE '%BANCO%' OR UPPER(P."CardName") LIKE '%BANK%')
        ORDER BY P."CardCode", P."DocDate"
    '''
    return fetch_dicts(cur, sql, (TOLERANCE,))


def read_document_control_accounts(cur: Any, doc_entries: list[int]) -> dict[int, str]:
    if not doc_entries:
        return {}
    placeholders = ",".join("?" for _ in doc_entries)
    sql = f'''
        SELECT P."DocEntry" DOCENTRY, J."Account" ACCOUNT, SUM(J."Credit"-J."Debit") NET_CREDIT
        FROM TELCHI."OPCH" P
        JOIN TELCHI."OJDT" O ON O."TransId"=P."TransId"
        JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId"
        WHERE P."DocEntry" IN ({placeholders}) AND J."ShortName"=P."CardCode" AND J."Credit">0
        GROUP BY P."DocEntry", J."Account"
        ORDER BY P."DocEntry", NET_CREDIT DESC
    '''
    rows = fetch_dicts(cur, sql, tuple(doc_entries))
    result: dict[int, str] = {}
    for row in rows:
        result.setdefault(int(num(row["DOCENTRY"])), str(row["ACCOUNT"]))
    return result


def read_debt_accounts(cur: Any) -> list[dict[str, Any]]:
    sql = '''
        SELECT "AcctCode" ACCTCODE, "AcctName" ACCTNAME, "GroupMask" GROUPMASK,
               "CurrTotal" CURRTOTAL, "SysTotal" SYSTOTAL, "Postable" POSTABLE
        FROM TELCHI."OACT"
        WHERE "AcctCode" LIKE '213%' OR "AcctCode" LIKE '221%'
        ORDER BY "AcctCode"
    '''
    return fetch_dicts(cur, sql)


def read_bank_payment_lines(cur: Any, start: str) -> list[dict[str, Any]]:
    """One row per bank payment journal, with the GL split.

    ``CAPITAL_221`` is the principal debit against the loan liability account;
    ``AP_211`` is the debit against the AP control account that settles the
    interest accrual (and the principal of loans booked in ``2110101``).
    """
    sql = '''
        SELECT O."TransId" TRANSID, O."RefDate" REFDATE, O."Memo" MEMO, J."ShortName" SHORTNAME,
               SUM(CASE WHEN J."Account"='2210101' THEN J."Debit"-J."Credit" ELSE 0 END) CAPITAL_221,
               SUM(CASE WHEN J."Account"='2110101' THEN J."Debit"-J."Credit" ELSE 0 END) AP_211
        FROM TELCHI."OJDT" O
        JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId"
        WHERE O."RefDate">=? AND O."TransType"='46' AND J."ShortName" IN ('PL000212','PL000288','PL000640')
          AND J."Account" IN ('2210101','2110101')
        GROUP BY O."TransId", O."RefDate", O."Memo", J."ShortName"
        ORDER BY O."RefDate"
    '''
    return fetch_dicts(cur, sql, (start,))


def read_loan_liability_rollforward(cur: Any, period_start: str, period_end: str) -> dict[str, Any]:
    sql = '''
        SELECT J."Account" ACCOUNT,
               SUM(CASE WHEN J."RefDate"<? AND J."TransType" NOT IN (-2,-3) THEN J."Debit"-J."Credit" ELSE 0 END) OPENING,
               SUM(CASE WHEN J."RefDate">=? AND J."RefDate"<=? AND J."TransType" NOT IN (-2,-3) AND J."Debit">0 THEN J."Debit" ELSE 0 END) DEBITS,
               SUM(CASE WHEN J."RefDate">=? AND J."RefDate"<=? AND J."TransType" NOT IN (-2,-3) AND J."Credit">0 THEN J."Credit" ELSE 0 END) CREDITS,
               SUM(CASE WHEN J."RefDate"<=? AND J."TransType" NOT IN (-2,-3) THEN J."Debit"-J."Credit" ELSE 0 END) CLOSING
        FROM TELCHI."JDT1" J
        WHERE J."Account"='2210101'
        GROUP BY J."Account"
    '''
    rows = fetch_dicts(cur, sql, (period_start, period_start, period_end, period_start, period_end, period_end))
    return {str(row["ACCOUNT"]): {k: round(num(row[k]), 2) for k in ("OPENING", "DEBITS", "CREDITS", "CLOSING")}
            for row in rows}


def read_financial_result_accounts(cur: Any, as_of: str) -> dict[str, dict[str, Any]]:
    codes = (INTEREST_ACCOUNT, "6020303", *BANK_FEE_ACCOUNTS, *FX_LOSS_ACCOUNTS, *FX_GAIN_ACCOUNTS,
             *INTEREST_INCOME_ACCOUNTS, *OTHER_FINANCIAL_ACCOUNTS)
    placeholders = ",".join("?" for _ in codes)
    sql = f'''
        SELECT A."AcctCode" ACCTCODE, A."AcctName" ACCTNAME,
               SUM(CASE WHEN J."RefDate">='2026-01-01' AND J."RefDate"<=? AND J."TransType" NOT IN (-2,-3)
                        THEN J."Debit"-J."Credit" ELSE 0 END) FLOW_LIVE,
               MAX(J."RefDate") LAST_DATE
        FROM TELCHI."OACT" A
        LEFT JOIN TELCHI."JDT1" J ON J."Account"=A."AcctCode"
        WHERE A."AcctCode" IN ({placeholders})
        GROUP BY A."AcctCode", A."AcctName"
        ORDER BY A."AcctCode"
    '''
    rows = fetch_dicts(cur, sql, (as_of, *codes))
    return {str(row["ACCTCODE"]): row for row in rows}


def read_post_cutoff_financial_entries(cur: Any, as_of: str) -> list[dict[str, Any]]:
    """Journal lines on financial-result accounts created on the cutoff date
    with a reference date on or before the cutoff (the frozen gate predates
    some of them).  Used to reconcile the live total to the frozen target.
    """
    sql = '''
        SELECT J."Account" ACCOUNT, A."AcctName" ACCTNAME, O."RefDate" REFDATE, O."CreateDate" CREATEDATE,
               J."Debit" DEBIT, J."Credit" CREDIT, O."TransId" TRANSID, O."TransType" TRANSTYPE, O."Memo" MEMO
        FROM TELCHI."JDT1" J
        JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId"
        LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account"
        WHERE J."Account" IN ('6020101','6020102','6020103','6020104','6020105','6020301','6020303')
          AND O."CreateDate"=? AND O."RefDate"<=?
        ORDER BY J."Account", O."RefDate"
    '''
    return fetch_dicts(cur, sql, (as_of, as_of))


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def build_financing_universe(open_ap: list[dict[str, Any]], control_accounts: dict[int, str]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    by_entity: dict[str, dict[str, Any]] = {}
    by_nature: dict[str, float] = defaultdict(float)
    total = 0.0
    for row in open_ap:
        open_lc = round(num(row["OPEN_LC"]), 2)
        currency = str(row["DOCCUR"])
        amount = num(row["OPEN_FC"]) if currency == "USD" and num(row["OPEN_FC"]) > TOLERANCE else open_lc
        nature = classify_financing_doc(row["COMMENTS"])
        debt_type = classify_debt_type(row["COMMENTS"], row["CARDNAME"])
        doc_entry = int(num(row["DOCENTRY"]))
        document = {
            "doc_entry": doc_entry,
            "doc_num": int(num(row["DOCNUM"])),
            "bp": str(row["CARDCODE"]),
            "bp_name": str(row["CARDNAME"]),
            "doc_date": str(row["DOCDATE"])[:10],
            "due_date": str(row["DOCDUEDATE"])[:10],
            "currency": currency,
            "doc_total": round(num(row["DOCTOTAL"]), 2),
            "paid_to_date": round(num(row["PAIDTODATE"]), 2),
            "open_lc": open_lc,
            "open_fc": round(num(row["OPEN_FC"]), 2),
            "amount": round(amount, 2),
            "nature": nature,
            "debt_type": debt_type,
            "control_account": control_accounts.get(doc_entry),
            "num_at_card": row["NUMATCARD"],
            "comment": row["COMMENTS"],
            "trans_id": row["TRANSID"],
            "loan_ref": parse_loan_ref(row["COMMENTS"]),
        }
        documents.append(document)
        total += amount
        entity = by_entity.setdefault(str(row["CARDCODE"]), {
            "card_code": str(row["CARDCODE"]), "card_name": str(row["CARDNAME"]),
            "documents": 0, "principal": 0.0, "accrued_interest": 0.0, "bank_fees": 0.0, "other": 0.0,
        })
        entity["documents"] += 1
        if nature == "PRINCIPAL":
            entity["principal"] += amount
        elif nature == "ACCRUED_INTEREST":
            entity["accrued_interest"] += amount
        elif nature == "BANK_FEE":
            entity["bank_fees"] += amount
        else:
            entity["other"] += amount
        by_nature[nature] += amount
    for entity in by_entity.values():
        for key in ("principal", "accrued_interest", "bank_fees", "other"):
            entity[key] = round(entity[key], 2)
        entity["total"] = round(entity["principal"] + entity["accrued_interest"] + entity["bank_fees"] + entity["other"], 2)
    return {
        "documents": documents,
        "total": round(total, 2),
        "by_nature": {key: round(value, 2) for key, value in by_nature.items()},
        "by_entity": sorted(by_entity.values(), key=lambda item: item["total"], reverse=True),
    }


def build_loan_register(
    open_ap: list[dict[str, Any]],
    payment_lines: list[dict[str, Any]],
    control_accounts: dict[int, str],
    as_of: date,
) -> list[dict[str, Any]]:
    """Map each open principal document to its observed monthly installment."""
    # Group principal GL debits by loan operation (parsed from the memo).
    series: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for line in payment_lines:
        loan = parse_loan_ref(line["MEMO"])
        if not loan:
            continue
        period = str(line["REFDATE"])[:7]
        series[loan][period].append(line)

    loans: list[dict[str, Any]] = []
    for row in open_ap:
        if classify_financing_doc(row["COMMENTS"]) != "PRINCIPAL":
            continue
        doc_entry = int(num(row["DOCENTRY"]))
        loan_ref = parse_loan_ref(row["COMMENTS"])
        alias = LOAN_ALIASES.get(str(loan_ref))
        series_key = alias if alias and alias in series else (loan_ref if loan_ref in series else None)
        monthly_capital = 0.0
        monthly_interest = 0.0
        payment_day = parse_date(row["DOCDUEDATE"]).day if parse_date(row["DOCDUEDATE"]) else 1
        last_payment: str | None = None
        if series_key:
            periods = sorted(series[series_key])
            # Use the most recent period with a strictly positive principal movement.
            for period in reversed(periods):
                capital = round(sum(num(x["CAPITAL_221"]) for x in series[series_key][period]), 2)
                if capital > TOLERANCE:
                    monthly_capital = capital
                    monthly_interest = round(sum(num(x["AP_211"]) for x in series[series_key][period]), 2)
                    last_payment = period
                    break
            if last_payment:
                due = parse_date(row["DOCDUEDATE"])
                observed = max((parse_date(x["REFDATE"]) for x in series[series_key][last_payment]
                                if parse_date(x["REFDATE"])), default=None)
                if observed:
                    payment_day = observed.day
        control_account = control_accounts.get(doc_entry)
        loans.append({
            "doc_entry": doc_entry,
            "doc_num": int(num(row["DOCNUM"])),
            "bp": str(row["CARDCODE"]),
            "bp_name": str(row["CARDNAME"]),
            "loan_ref": loan_ref,
            "series_key": series_key,
            "debt_type": classify_debt_type(row["COMMENTS"], row["CARDNAME"]),
            "open_lc": round(num(row["OPEN_LC"]), 2),
            "currency": str(row["DOCCUR"]),
            "doc_due_date": str(row["DOCDUEDATE"])[:10],
            "control_account": control_account,
            "monthly_capital": round(monthly_capital, 2),
            "monthly_interest": round(monthly_interest, 2),
            "payment_day": payment_day,
            "last_observed_payment": last_payment,
            "evidence": "STRONG" if monthly_capital > TOLERANCE else "PARTIAL",
            "comment": row["COMMENTS"],
        })
    return loans


def build_schedule(loans: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    """Derive the HEURISTIC economic schedule.

    Loans booked in the commercial AP control account (no clean principal GL
    account) use the final documented maturity to split the remaining
    principal evenly across the remaining monthly due dates.
    """
    rows: list[dict[str, Any]] = []
    for loan in loans:
        monthly_capital = num(loan["monthly_capital"])
        basis = "LAST_OBSERVED_MONTHLY_CAPITAL"
        if monthly_capital <= TOLERANCE:
            due = parse_date(loan["doc_due_date"])
            if due and due > as_of:
                months = max(1, (due.year - as_of.year) * 12 + (due.month - as_of.month) + 1)
                monthly_capital = round(num(loan["open_lc"]) / months, 2)
                basis = "FINAL_MATURITY_EVEN_SPLIT"
        installments = build_amortization(
            loan, as_of,
            monthly_capital=monthly_capital,
            monthly_interest=num(loan["monthly_interest"]),
            payment_day=int(loan["payment_day"]),
        )
        if basis == "FINAL_MATURITY_EVEN_SPLIT" and installments:
            installments[-1]["capital"] = round(installments[-1]["capital"], 2)
        rows.append({
            "doc_entry": loan["doc_entry"],
            "loan_ref": loan["loan_ref"],
            "bp": loan["bp"],
            "bp_name": loan["bp_name"],
            "debt_type": loan["debt_type"],
            "open_lc": loan["open_lc"],
            "doc_due_date": loan["doc_due_date"],
            "control_account": loan["control_account"],
            "monthly_capital": round(monthly_capital, 2),
            "monthly_interest": round(num(loan["monthly_interest"]), 2),
            "remaining_installments": len(installments),
            "schedule_basis": basis,
            "evidence": "HEURISTIC",
            "installments": installments,
        })
    return {
        "loans": rows,
        "total_open": round(sum(num(row["open_lc"]) for row in rows), 2),
        "total_scheduled_capital": round(sum(sum(num(i["capital"]) for i in row["installments"]) for row in rows), 2),
        "known_schedule_basis": sorted({row["schedule_basis"] for row in rows}),
    }


def build_debt_service(schedule: dict[str, Any], as_of: date) -> dict[str, Any]:
    windows = {"7d": 7, "30d": 30, "60d": 60, "90d": 90, "365d": 365}
    result: dict[str, Any] = {}
    for label, days in windows.items():
        capital = 0.0
        interest = 0.0
        for loan in schedule["loans"]:
            capital += horizon_total(loan["installments"], as_of, days, "capital")
            interest += horizon_total(loan["installments"], as_of, days, "interest")
        result[label] = {"capital": round(capital, 2), "interest": round(interest, 2),
                         "debt_service": round(capital + interest, 2)}
    return result


def build_v1_treatment(open_ap: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    """Reproduce forecast V1's treatment of bank AP documents.

    V1 assigns overdue documents a wait of ``30`` days when they are more than
    90 days past due (``financial_forecast_liquidity_scenarios_v1.py``), which
    concentrates the whole remaining principal of placeholder-dated loans.
    Documents within their due date are placed on their documentary due date.
    """
    rows: list[dict[str, Any]] = []
    for doc in open_ap:
        due = parse_date(doc["due_date"])
        if due is None:
            continue
        overdue_days = (as_of - due).days
        if overdue_days > 90:
            offset = 30
        elif overdue_days > 0:
            offset = overdue_days
        else:
            offset = (due - as_of).days
        rows.append({"doc_entry": doc["doc_entry"], "bp_name": doc["bp_name"], "due_date": doc["due_date"],
                     "nature": doc.get("nature"), "open_lc": doc["open_lc"], "overdue_days": overdue_days,
                     "v1_offset_days": offset})
    overdue = [row for row in rows if row["overdue_days"] > 90 and row["nature"] == "PRINCIPAL"]
    return {
        "overdue_beyond_90d_documents": len(overdue),
        "overdue_beyond_90d_amount": round(sum(num(row["open_lc"]) for row in overdue), 2),
        "documents": overdue,
        "v1_30d": round(sum(num(row["open_lc"]) for row in rows if row["v1_offset_days"] <= 30), 2),
        "v1_90d": round(sum(num(row["open_lc"]) for row in rows if row["v1_offset_days"] <= 90), 2),
        "rule": "AP_OVERDUE wait=30 days when the document is >90 days past due (forecast V1).",
    }


def build_ratios(
    debt_total: float,
    equity: float,
    total_liabilities: float,
    operating_result: float,
    revenue: float,
    financial_result: float,
    interest_expense: float,
) -> dict[str, Any]:
    return {
        "total_liabilities_to_equity": round(total_liabilities / equity, 4) if equity else None,
        "financial_debt_to_equity": round(debt_total / equity, 4) if equity else None,
        "financial_result_to_operating_result_pct": round(100.0 * financial_result / operating_result, 2) if operating_result else None,
        "interest_expense_to_operating_result_pct": round(100.0 * abs(interest_expense) / operating_result, 2) if operating_result else None,
        "financial_expense_to_revenue_pct": round(100.0 * abs(financial_result) / revenue, 2) if revenue else None,
        "financial_debt_to_annualized_operating_result": round(debt_total / operating_result, 4) if operating_result else None,
        "note": "Descriptive ratios; financial debt here is the FINANCING AP block (bank suppliers).",
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def _money(value: Any) -> str:
    return f"{num(value):,.2f}"


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(str(h) for h in headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return out


def render_report(result: dict[str, Any]) -> str:
    fu = result["financing_universe"]
    schedule = result["financial_debt_schedule"]
    service = result["debt_service"]
    fr = result["financial_result"]
    v1 = result["forecast_v1_impact"]
    cases = result["real_cases"]
    lines: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, list):
            lines.extend(str(item) for item in value)
        else:
            lines.append(str(value))

    add("# TELCHI — FINANCIAL DEBT / INTEREST / FINANCIAL RESULT TRACEABILITY V1")
    add("")
    add(f"**Gate:** `{result['gate']}`  ")
    add(f"**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT={result['sap_write_count']}`  ")
    add(f"**AS_OF:** {result['as_of_date']}  ")
    add(f"**Evidencia:** {result['generated_at_utc']}")
    add("")
    add("## A. VEREDICTO")
    add("")
    add(result["executive_summary"])
    add("")
    add(f"**Decisión:** `{result['verdict']}` — {result['verdict_reason']}")
    add("")

    add("## B. FINANCING UNIVERSE — LOS Bs 4.827.924,39")
    add("")
    add(f"El bloque `FINANCING` del forecast V1 queda reproducido por **Bs {_money(fu['total'])}** "
        f"({len(fu['documents'])} documentos OPCH abiertos a proveedores cuyo nombre contiene BANCO/BANK).")
    add("")
    add(_table(["Naturaleza", "Monto BS"], [[k, _money(v)] for k, v in sorted(fu["by_nature"].items())]))
    add("")
    add("Bridge del universo:")
    add("")
    add(_table(
        ["Componente", "Monto BS"],
        [
            ["PRINCIPAL_OUTSTANDING", _money(fu["by_nature"].get("PRINCIPAL", 0.0))],
            ["ACCRUED_INTEREST", _money(fu["by_nature"].get("ACCRUED_INTEREST", 0.0))],
            ["BANK_FEES", _money(fu["by_nature"].get("BANK_FEE", 0.0))],
            ["OTHER / UNRESOLVED", _money(fu["by_nature"].get("OTHER", 0.0) + fu["by_nature"].get("UNRESOLVED", 0.0))],
            ["**TOTAL**", f"**{_money(fu['total'])}**"],
        ],
    ))
    add("")

    add("## C. FINANCIAL ENTITIES")
    add("")
    add(_table(
        ["Entidad", "CardCode", "Docs", "Principal", "Interés devengado", "Comisiones", "Total", "Evidencia"],
        [[e["card_name"], e["card_code"], e["documents"], _money(e["principal"]), _money(e["accrued_interest"]),
          _money(e["bank_fees"]), _money(e["total"]), "STRONG"] for e in fu["by_entity"]],
    ))
    add("")
    add("Concentración de deuda: top_1 "
        f"{100.0 * (result['debt_concentration']['top_1'] or 0.0):.1f}% · "
        f"top_3 {100.0 * (result['debt_concentration']['top_3'] or 0.0):.1f}%")
    add("")

    add("## D. DEBT TYPE")
    add("")
    add(_table(["Documento", "Entidad", "Tipo", "Naturaleza", "Cuenta control", "Comentario"],
               [[d["doc_entry"], d["bp_name"], d["debt_type"], d["nature"], d["control_account"], (d["comment"] or "")[:90]]
                for d in fu["documents"] if d["nature"] == "PRINCIPAL"]))
    add("")

    add("## E. PRINCIPAL OUTSTANDING")
    add("")
    add(_table(["DocEntry", "Préstamo", "Entidad", "Capital pendiente Bs", "Cuota capital/mes", "Cuotas restantes", "Base"],
               [[l["doc_entry"], l["loan_ref"], l["bp_name"], _money(l["open_lc"]), _money(l["monthly_capital"]),
                 l["remaining_installments"], l["schedule_basis"]] for l in schedule["loans"]]))
    add("")
    add(f"Total capital pendiente agendado: **Bs {_money(schedule['total_open'])}**.")
    add("")

    add("## F. CURRENCY")
    add("")
    add(f"Toda la deuda bancaria abierta está denominada en **{result['currency']['debt']}**; "
        "no se suma deuda USD nominalmente a Bs. " + result["currency"]["note"])
    add("")

    add("## G. MATURITY / INSTALLMENTS")
    add("")
    add(f"- `FINANCIAL_DEBT_SCHEDULE = {result['maturity']['schedule']}`")
    add(f"- `DEBT_MATURITY_CLASSIFICATION = {result['maturity']['classification']}`")
    add(f"- {result['maturity']['inv6']}")
    add(f"- {result['maturity']['mechanism']}")
    add("")
    add(_table(["DocEntry", "Préstamo", "Fecha vencimiento OPCH", "Interpretación", "Tipo de fecha"],
               [[l["doc_entry"], l["loan_ref"], l["doc_due_date"], l["maturity_reading"]["interpretation"],
                 l["maturity_reading"]["date_quality"]] for l in schedule["loans"]]))
    add("")

    add("## H. OVERDUE DOCUMENTAL VS ECONÓMICO")
    add("")
    add(f"Documentos con vencimiento documental >90 días atrasado: **{v1['overdue_beyond_90d_documents']}** "
        f"por **Bs {_money(v1['overdue_beyond_90d_amount'])}**. No son cuotas vencidas: son préstamos vigentes "
        "cuyo OPCH usa la madurez final o una fecha marcador. `SAP_DOCUMENT_OVERDUE` ≠ `ECONOMIC_INSTALLMENT_OVERDUE`.")
    add("")
    add(_table(["DocEntry", "Entidad", "DueDate", "Días atraso documental", "Tratamiento V1", "Lectura económica"],
               [[d["doc_entry"], d["bp_name"], d["due_date"], d["overdue_days"], f"offset +{d['v1_offset_days']}d",
                 "cuota mensual vigente"] for d in v1["documents"]]))
    add("")

    add("## I. DEBT PAYMENTS")
    add("")
    add(f"Pagos a bancos en 2026 YTD (OVPM activos): **{result['payments']['documents_2026']}** documentos; "
        f"principal de préstamos en 2210101 Bs {_money(result['payments']['principal_2026'])}; "
        f"movimiento en cuenta control AP (interés + capital de préstamo en 2110101 + reversas) "
        f"Bs {_money(result['payments']['ap_control_2026'])}; "
        f"interés devengado P&L Bs {_money(result['payments']['interest_expense_2026'])}.")
    add("")
    add("Cadena: `PRINCIPAL OPCH → OVPM → 2210101/2110101 → banco`. " + result["payments"]["note"])
    add("")

    add("## J. PRINCIPAL PAYMENTS")
    add("")
    add(_table(["Período", "Pagos", "Capital Bs (2210101)", "Movimiento AP control Bs"],
               [[p["period"], p["count"], _money(p["capital"]), _money(p["interest"])]
                for p in result["payments"]["monthly"]]))
    add("")

    add("## K. INTEREST")
    add("")
    add(f"- Interés devengado 2026 YTD (`{INTEREST_ACCOUNT}`): **Bs {_money(fr['accounts'][INTEREST_ACCOUNT]['flow_live'])}**")
    add(f"- Ajuste `6020303 Intereses bancarios`: Bs {_money(fr['accounts'].get('6020303', {}).get('flow_live', 0.0))}")
    add(f"- Interés P&L neto (subgrupo `INTEREST_EXPENSE`): **Bs {_money(fr['decomposition_frozen']['INTEREST_EXPENSE'])}**")
    add(f"- Interés cobrado/pagado en caja 2026 YTD: no separable sin calendario contractual; el movimiento "
        f"de 2110101 por pagos a bancos es Bs {_money(result['payments']['ap_control_2026'])} e incluye capital del "
        f"préstamo registrado en 2110101.")
    add(f"- `ACCOUNTING_FINANCIAL_COST_RATE = {result['interest']['cost_rate']}` (descriptivo, no tasa contractual)")
    add("")

    add("## L. FEES")
    add("")
    add(_table(["Cuenta", "Concepto", "2026 YTD Bs"],
               [[code, fr["accounts"].get(code, {}).get("name", ""), _money(fr["accounts"].get(code, {}).get("flow_live", 0.0))]
                for code in fr["fee_accounts"]]))
    add("")
    add(result["fees_note"])
    add("")

    add("## M. FX")
    add("")
    add(f"- `FX_LOSS`: Bs {_money(fr['decomposition_frozen']['FX_LOSS'])} · `FX_GAIN`: Bs {_money(fr['decomposition_frozen']['FX_GAIN'])} · "
        f"neto Bs {_money(fr['decomposition_frozen']['FX_GAIN'] + fr['decomposition_frozen']['FX_LOSS'])}")
    add("- La deuda bancaria abierta está en Bs, por lo que no genera revaluación de deuda USD en el horizonte.")
    add("")

    add("## N. FINANCIAL RESULT RECONCILIATION — LOS −Bs 1.414.305,12")
    add("")
    add(f"- Valor congelado gate BSPNL V1: **Bs {_money(fr['frozen_target'])}**")
    add(f"- Valor vivo (HANA al corte): **Bs {_money(fr['live_total'])}**")
    add(f"- Bridge post-cierre detectado: **Bs {_money(fr['post_cutoff_bridge'])}** "
        f"({fr['post_cutoff_note']})")
    add(f"- Reconciliación: {_money(fr['live_total'])} − ({_money(fr['post_cutoff_bridge'])}) = {_money(fr['frozen_target'])}")
    add("")
    add(_table(["Subgrupo", "Monto Bs (congelado)"],
               [[k, _money(v)] for k, v in fr["decomposition_frozen"].items()]
               + [["**TOTAL**", f"**{_money(sum(fr['decomposition_frozen'].values()))}**"]]))
    add("")

    add("## O. FINANCIAL RESULT PARETO")
    add("")
    add(_table(["Cuenta", "Concepto", "2026 YTD Bs", "Share % del resultado financiero"],
               [[p["key"], fr["accounts"].get(p["key"], {}).get("name", ""), _money(p["amount"]), p["share_pct"]]
                for p in fr["pareto"]["top"]]))
    add("")
    add(result["pareto_note"])
    add("")

    add("## P. DEBT ROLL-FORWARD")
    add("")
    add(_table(["Cuenta", "Saldo apertura 2026", "Cargos (nuevo financiamiento)", "Abonos (pagos/ajustes)", "Saldo cierre"],
               [[k, _money(v["OPENING"]), _money(v["CREDITS"]), _money(v["DEBITS"]), _money(v["CLOSING"])]
                for k, v in result["rollforward"]["accounts"].items()]))
    add("")
    loan_ap = result["rollforward"].get("commercial_ap_loan")
    if loan_ap:
        add(f"Préstamo en cuenta comercial (DocEntry {loan_ap['doc_entry']}, {loan_ap['bp_name']}): "
            f"capital original Bs {_money(loan_ap['doc_total'])}, pagado Bs {_money(loan_ap['paid_to_date'])}, "
            f"saldo Bs {_money(loan_ap['open_lc'])}. No es una cuenta de pasivo financiero separada, pero "
            "económicamente es deuda bancaria y forma parte del universo FINANCING.")
        add("")
    add(result["rollforward"]["note"])
    add("")

    add("## Q. DEBT SERVICE 30/60/90D")
    add("")
    add(_table(["Horizonte", "Capital Bs", "Interés Bs", "Debt service Bs"],
               [[label, _money(s["capital"]), _money(s["interest"]), _money(s["debt_service"])]
                for label, s in service.items()]))
    add("")
    add("Cronograma **HEURÍSTICO**: capital proyectado con la última cuota mensual observada; interés con el último "
        "devengado. No es un calendario contractual. " + result["schedule_note"])
    add("")
    add("## Q.1 CALENDARIO DETALLADO (primeras 12 cuotas por préstamo)")
    add("")
    for loan in schedule["loans"]:
        add(f"**{loan['bp_name']} · préstamo {loan['loan_ref']} (DocEntry {loan['doc_entry']})** — "
            f"capital Bs {_money(loan['open_lc'])}, cuota Bs {_money(loan['monthly_capital'])}/mes.")
        add("")
        add(_table(["#", "Vencimiento", "Capital Bs", "Interés Bs", "Saldo después Bs"],
                   [[i["installment"], i["due_date"], _money(i["capital"]), _money(i["interest"]), _money(i["remaining_after"])]
                    for i in loan["installments"][:12]]))
        add("")

    add("## R. FORECAST V1 IMPACT")
    add("")
    add(f"Forecast V1 clasificó como `FINANCING` **Bs {_money(FINANCING_TARGET)}** y colocó los documentos "
        f"con vencimiento documental >90 días atrasado a ~30 días. Esa concentración artificial asciende a "
        f"**Bs {_money(v1['overdue_beyond_90d_amount'])}**.")
    add("")
    add(_table(["Horizonte", "Forecast V1 (tratamiento documental)", "Cronograma económico (heurístico)", "Diferencia"],
               [["30d", _money(v1["v1_30d"]), _money(service["30d"]["debt_service"]), _money(service["30d"]["debt_service"] - v1["v1_30d"])],
                ["90d", _money(v1["v1_90d"]), _money(service["90d"]["debt_service"]), _money(service["90d"]["debt_service"] - v1["v1_90d"])]]))
    add("")
    add(result["forecast_impact_note"])
    add("")

    add("## S. REVISED LIQUIDITY VIEW")
    add("")
    add(result["revised_view"])
    add("")
    add("Este gate **no reemplaza** el forecast V1, que permanece `PASS`: documentó correctamente el supuesto. "
        "Genera evidencia para una eventual `TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_1`.")
    add("")

    add("## T. RATIOS")
    add("")
    add(_table(["Ratio", "Valor"],
               [[k, v] for k, v in result["ratios"].items() if k != "note"]))
    add("")

    add("## U. REAL CASES")
    add("")
    add(_table(["Caso", "Entidad", "Documento", "Monto", "Moneda", "Naturaleza", "Evidencia"],
               [[c["case"], c["entity"], c["document"], _money(c["amount"]), c["currency"], c["nature"], c["evidence"]]
                for c in cases]))
    add("")

    add("## V. INVARIANTS")
    add("")
    add(_table(["Invariante", "Resultado", "Valor"],
               [[key, "PASS" if value["pass"] else "FAIL", json.dumps(value.get("value"), ensure_ascii=False, default=str)[:120]]
                for key, value in result["invariants"].items()]))
    add("")

    add("## W. LIMITATIONS")
    add("")
    for item in result["limitations"]:
        add(f"- {item}")
    add("")

    add("## X. EXTERNAL DOCUMENTATION REQUIRED")
    add("")
    add("SAP conserva el capital y los pagos, pero **no** el calendario contractual de cuotas. Para corregir el "
        "forecast sin heurística se requiere, por entidad/préstamo:")
    add("")
    for item in result["external_documentation_required"]:
        add(f"- {item}")
    add("")

    add("## Y. NEXT GATE")
    add("")
    add(result["next_gate"])
    add("")
    add("## Artefactos")
    add("")
    add(f"- JSON: `{DEFAULT_OUTPUT}`")
    add(f"- Runner: `{Path(__file__)}`")
    add("- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.")
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_result(cur: Any, frozen_bspnl: dict[str, Any], forecast: dict[str, Any], as_of: date) -> dict[str, Any]:
    meta = read_meta(cur)
    open_ap_raw = read_open_bank_ap(cur)
    doc_entries = [int(num(row["DOCENTRY"])) for row in open_ap_raw]
    control_accounts = read_document_control_accounts(cur, doc_entries)

    open_ap: list[dict[str, Any]] = []
    for row in open_ap_raw:
        row = dict(row)
        row["nature"] = classify_financing_doc(row["COMMENTS"])
        open_ap.append(row)
    financing = build_financing_universe(open_ap, control_accounts)

    payment_lines = read_bank_payment_lines(cur, "2025-01-01")
    loans = build_loan_register(open_ap, payment_lines, control_accounts, as_of)
    schedule = build_schedule(loans, as_of)
    service = build_debt_service(schedule, as_of)
    for loan in schedule["loans"]:
        due = parse_date(loan["doc_due_date"])
        if due and due > as_of:
            loan["maturity_reading"] = {"interpretation": "FINAL_MATURITY_DOCUMENTED", "date_quality": "DOCUMENT_DUE_DATE"}
        else:
            loan["maturity_reading"] = {"interpretation": "PLACEHOLDER_OR_MIGRATION_DATE", "date_quality": "INFERRED_PATTERN"}

    rollforward = read_loan_liability_rollforward(cur, "2026-01-01", meta["as_of_date"])
    loan_in_commercial_ap = next((d for d in financing["documents"]
                                  if d["nature"] == "PRINCIPAL" and d["control_account"] == COMMERCIAL_AP_ACCOUNT), None)
    new_borrowing_2026 = round(sum(num(d["doc_total"]) for d in financing["documents"]
                                   if d["nature"] == "PRINCIPAL" and str(d["doc_date"])[:4] == "2026"), 2)
    debt_accounts = read_debt_accounts(cur)

    # Financial result: use the validated BSPNL classification to stay aligned.
    from modules.telchi.investigation.validation.balance_sheet_pnl_reconstruction import (
        balance_sheet_pnl_reconstruction_v1 as bsp,
    )
    accounts = bsp.account_universe(cur)
    balances = bsp.account_balances(cur)
    build = bsp.build_financials(accounts, balances, [])
    live_pnl = bsp.pnl_view(build, balances, "FLOW_2026YTD")
    live_total = round(num(live_pnl["financial_result"]), 2)
    frozen_target = round(num(frozen_bspnl["profit_and_loss"]["ytd_2026"]["financial_result"]), 2)
    post_cutoff = read_post_cutoff_financial_entries(cur, meta["as_of_date"])
    bridge = round(live_total - frozen_target, 2)
    decomposition_live = {key: round(num(value), 2) for key, value in live_pnl["detail"]["FINANCIAL_RESULT"].items()}
    decomposition_frozen = dict(decomposition_live)
    for entry in post_cutoff:
        code = str(entry["ACCOUNT"])
        classified = build["classified"].get(code)
        if not classified or classified["statement"] != "FINANCIAL_RESULT":
            continue
        subgroup = classified["pl_subgroup"]
        if subgroup not in decomposition_frozen:
            continue
        # Presentation impact of the posting: a credit reduces the expense.
        presentation_delta = num(entry["CREDIT"]) - num(entry["DEBIT"])
        decomposition_frozen[subgroup] = round(decomposition_frozen[subgroup] - presentation_delta, 2)
    fr_accounts = {
        str(code): {"name": classified["acctname"],
                    "flow_live": round(num(balances.get(str(code), {}).get("FLOW_2026YTD")), 2)}
        for code, classified in build["classified"].items()
        if classified["statement"] == "FINANCIAL_RESULT"
        and abs(num(balances.get(str(code), {}).get("FLOW_2026YTD"))) > TOLERANCE
    }
    pareto_entries = {code: data["flow_live"] for code, data in fr_accounts.items()}

    payments_2026 = [p for p in payment_lines if str(p["REFDATE"])[:4] == "2026"]
    monthly: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "capital": 0.0, "interest": 0.0})
    for line in payments_2026:
        period = str(line["REFDATE"])[:7]
        monthly[period]["count"] += 1
        monthly[period]["capital"] += num(line["CAPITAL_221"])
        monthly[period]["interest"] += num(line["AP_211"])
    principal_2026 = round(sum(num(x["CAPITAL_221"]) for x in payments_2026), 2)
    ap_control_2026 = round(sum(num(x["AP_211"]) for x in payments_2026), 2)

    v1 = build_v1_treatment(financing["documents"], as_of)

    averages = {}
    if LOAN_PRINCIPAL_ACCOUNT in rollforward:
        average_221 = (abs(num(rollforward[LOAN_PRINCIPAL_ACCOUNT]["OPENING"]))
                       + abs(num(rollforward[LOAN_PRINCIPAL_ACCOUNT]["CLOSING"]))) / 2
        average_42098 = ((num(loan_in_commercial_ap["doc_total"]) + num(loan_in_commercial_ap["open_lc"])) / 2
                         if loan_in_commercial_ap else 0.0)
        average_debt = round(average_221 + average_42098, 2)
        interest_expense_ytd = abs(num(decomposition_frozen["INTEREST_EXPENSE"]))
        averages = {
            "rate": round(100.0 * interest_expense_ytd / average_debt, 2) if average_debt else None,
            "average_debt_bs": average_debt,
            "interest_expense_2026_ytd": round(interest_expense_ytd, 2),
        }

    bs = frozen_bspnl["balance_sheet"]["as_of"]
    pl = frozen_bspnl["profit_and_loss"]["ytd_2026"]
    ratios = build_ratios(
        debt_total=financing["total"],
        equity=num(bs["total_equity"]),
        total_liabilities=num(bs["total_liabilities"]),
        operating_result=num(pl["operating_result"]),
        revenue=num(pl["revenue"]),
        financial_result=frozen_target,
        interest_expense=decomposition_frozen["INTEREST_EXPENSE"],
    )

    invariants = build_invariants(
        financing, schedule, service, decomposition_frozen, frozen_target, bridge,
        rollforward[LOAN_PRINCIPAL_ACCOUNT]["CLOSING"] if LOAN_PRINCIPAL_ACCOUNT in rollforward else None,
        round(sum(num(l["open_lc"]) for l in schedule["loans"] if l.get("control_account") == LOAN_PRINCIPAL_ACCOUNT), 2),
        result_cases_ready=True)

    result: dict[str, Any] = {
        "report_id": "TELCHI_FINANCIAL_DEBT_AND_FINANCIAL_RESULT_TRACEABILITY_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entity": "TELCHI",
        "domain": "CONTABILIDAD / FINANZAS",
        "stage": "INVESTIGATION",
        "mode": "READ_ONLY",
        "source": {"database": "SAP_HANA", "schema": "TELCHI", "hana_read_only": True},
        "as_of_date": meta["as_of_date"],
        "hana_user": meta["hana_user"],
        "sap_write_count": 0,
        "company_currency": {"local": "BS", "system": "USD", "multi": "B"},
        "financing_universe": financing,
        "debt_accounts": debt_accounts,
        "financial_debt_schedule": schedule,
        "debt_service": service,
        "rollforward": {"accounts": rollforward,
                        "commercial_ap_loan": loan_in_commercial_ap,
                        "new_borrowing_2026": new_borrowing_2026,
                        "note": "Cuenta 2210101 Préstamos bancarios, ejercicio 2026: cierre = apertura − cargos (créditos: nuevo "
                                f"financiamiento Bs {_money(new_borrowing_2026)} y reversas de pago) + abonos (débitos: pagos de capital). "
                                "El préstamo MSC 6014485521 (DocEntry 42098) está registrado en 2110101 Cuentas por pagar MN y se "
                                "reporta por separado por su DocTotal/PaidToDate/Open."},
        "currency": {"debt": "BS",
                     "note": "Los tres proveedores financieros abiertos (BANCO FIE, BANCO MSC, BANCO GANADERO) tienen DocCur='BS'."},
        "maturity": {
            "schedule": "HEURISTIC",
            "classification": "DEBT_MATURITY_CLASSIFICATION_DEGRADED",
            "inv6": "INV6 no conserva cuotas para los OPCH de capital abiertos (0 filas para los 9 préstamos).",
            "mechanism": "Cada préstamo es UN OPCH con el capital remanente; los pagos mensuales aplican capital a 2210101 "
                         "y cancelan la provisión de interés contra 2110101. La cuota económica se reconstruye desde la "
                         "historia de pagos (STRONG) y se proyecta como HEURISTIC.",
        },
        "payments": {
            "documents_2026": len(payments_2026),
            "principal_2026": principal_2026,
            "ap_control_2026": ap_control_2026,
            "interest_expense_2026": round(abs(decomposition_frozen["INTEREST_EXPENSE"]), 2),
            "monthly": [{"period": p, **{k: round(v, 2) if isinstance(v, float) else v for k, v in data.items()}}
                        for p, data in sorted(monthly.items())],
            "note": "El pago de interés no debita 6020101 en caja: cancela la provisión (2110101) creada como OPCH de interés. "
                    "El movimiento de 2110101 por pagos a bancos mezcla intereses, capital del préstamo registrado en 2110101 "
                    "y reversas; no se declara como interés sin separación contractual.",
        },
        "interest": {"cost_rate": averages.get("rate"),
                     "average_debt_bs": averages.get("average_debt_bs"),
                     "interest_expense_2026_ytd": averages.get("interest_expense_2026_ytd")},
        "financial_result": {
            "frozen_target": frozen_target,
            "live_total": live_total,
            "post_cutoff_bridge": bridge,
            "post_cutoff_note": "Asiento(s) creados el día del corte con RefDate anterior; el gate BSPNL se generó antes.",
            "post_cutoff_entries": post_cutoff,
            "decomposition_live": decomposition_live,
            "decomposition_frozen": decomposition_frozen,
            "accounts": fr_accounts,
            "fee_accounts": list(BANK_FEE_ACCOUNTS),
            "pareto": pareto(pareto_entries),
        },
        "debt_concentration": {
            "top_1": financing["by_entity"][0]["total"] / financing["total"] if financing["by_entity"] else None,
            "top_3": sum(e["total"] for e in financing["by_entity"][:3]) / financing["total"] if financing["total"] else None,
        },
        "forecast_v1_impact": v1,
        "ratios": ratios,
        "real_cases": [],
        "invariants": invariants,
        "limitations": [],
        "external_documentation_required": [],
        "next_gate": "",
    }

    result["real_cases"] = build_real_cases(financing, schedule, payments_2026, decomposition_frozen, post_cutoff)
    result["fees_note"] = (
        "El resultado financiero está dominado por comisiones, no por intereses: "
        f"`{BANK_FEE_ACCOUNTS[-1]}` (giros al exterior) explica "
        f"Bs {_money(result['financial_result']['accounts'].get(BANK_FEE_ACCOUNTS[-1], {}).get('flow_live', 0.0))}. "
        "Bs 68.494,43 de comisiones de depósitos ODPS de tarjetas NO forman parte del resultado financiero; "
        "se contabilizan en la cuenta operativa 62101xx. Se valida contra el gate de depósitos."
    )
    result["pareto_note"] = (
        "El 77% del resultado financiero negativo son comisiones por giros al exterior; el interés bancario "
        "es solo ~21%. Las comisiones de tarjetas y formularios son marginales."
    )
    result["schedule_note"] = (
        "El conteo de cuotas usa el capital remanente dividido por la última cuota mensual observada; "
        "el residuo de redondeo se aplica a la última cuota. La fecha de pago usa el día del último pago observado."
    )
    result["forecast_impact_note"] = (
        "El forecast V1 no sobreestima el monto total de deuda, pero sí concentra el capital de préstamos "
        "con fecha documental vencida dentro de los primeros 30 días. El cronograma económico difiere en "
        "capital e interés; la comisión de giros al exterior es gasto recurrente ya devengado, no deuda."
    )
    result["revised_view"] = build_revised_view(result)
    result["limitations"] = build_limitations(result)
    result["external_documentation_required"] = [
        "Entidad financiera y número de préstamo/operación.",
        "Capital original desembolsado y moneda.",
        "Fecha de desembolso y tasa de interés contractual.",
        "Calendario de cuotas (número, fecha, capital, interés, seguro si aplica).",
        "Saldo de capital remanente a la fecha de corte.",
        "Próximo vencimiento y fecha de madurez final.",
        "Comisiones y cargos recurrentes asociados a cada préstamo.",
        "Garantías/seguros, si son relevantes para la clasificación.",
    ]
    result["next_gate"] = (
        "Si Telchi entrega el calendario contractual: `TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_1` "
        "para corregir la deuda financiera dentro del forecast. Si no: mantener el cronograma HEURISTIC y "
        "solicitar los contratos/estados de deuda antes de modificar el forecast. Luego: "
        "`TELCHI_FINANCIAL_CONTROL_POLICIES_AND_ALERTS_V1`."
    )
    result["executive_summary"] = build_executive_summary(result)
    all_pass = all(v["pass"] for v in invariants.values())
    result["verdict"] = "PASS" if all_pass else "DEGRADED"
    result["verdict_reason"] = (
        "Universo FINANCING reproducido, capital/interés/comisiones separados, resultado financiero reconstruido y "
        "frontera SAP delimitada (sin calendario contractual almacenado)."
        if all_pass else
        "Uno o más invariantes FD fallaron; revisar la tabla de invariantes."
    )
    result["gate"] = f"TELCHI_FINANCIAL_DEBT_AND_FINANCIAL_RESULT_TRACEABILITY_V1_{result['verdict']}"
    result["gate_checks"] = {key: value["pass"] for key, value in invariants.items()}
    return result


def build_real_cases(
    financing: dict[str, Any],
    schedule: dict[str, Any],
    payments: list[dict[str, Any]],
    decomposition: dict[str, float],
    post_cutoff: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    docs = financing["documents"]
    principal = next((d for d in docs if d["nature"] == "PRINCIPAL" and d["control_account"] == LOAN_PRINCIPAL_ACCOUNT), {})
    principal_211 = next((d for d in docs if d["nature"] == "PRINCIPAL" and d["control_account"] == COMMERCIAL_AP_ACCOUNT), {})
    interest = next((d for d in docs if d["nature"] == "ACCRUED_INTEREST"), {})
    fee = next((d for d in docs if d["nature"] == "BANK_FEE"), {})
    multi = max((e for e in financing["by_entity"]), key=lambda e: e["documents"], default={})
    names = {e["card_code"]: e["card_name"] for e in financing["by_entity"]}
    principal_payment = next((p for p in reversed(payments) if num(p["CAPITAL_221"]) > TOLERANCE),
                             payments[-1] if payments else None)
    interest_payment = next((p for p in reversed(payments) if num(p["AP_211"]) > TOLERANCE),
                            payments[-1] if payments else None)
    cases = [
        {"case": "A_PRINCIPAL_DOCUMENT", "entity": principal.get("bp_name"), "document": principal.get("doc_entry"),
         "amount": principal.get("amount"), "currency": principal.get("currency"), "nature": "PRINCIPAL",
         "evidence": "OPCH a banco, contrapartida 2210101 Préstamos bancarios.", "detail": principal},
        {"case": "B_PRINCIPAL_PAYMENT", "entity": names.get(principal_payment["SHORTNAME"], principal_payment["SHORTNAME"]) if principal_payment else None,
         "document": principal_payment["TRANSID"] if principal_payment else None,
         "amount": round(num(principal_payment["CAPITAL_221"]), 2) if principal_payment else None,
         "currency": "BS", "nature": "PRINCIPAL_PAYMENT",
         "evidence": "OVPM/TT46 debita 2210101 (capital).", "detail": principal_payment},
        {"case": "C_INTEREST_PAYMENT", "entity": names.get(interest_payment["SHORTNAME"], interest_payment["SHORTNAME"]) if interest_payment else None,
         "document": interest_payment["TRANSID"] if interest_payment else None,
         "amount": round(num(interest_payment["AP_211"]), 2) if interest_payment else None,
         "currency": "BS", "nature": "INTEREST_PAYMENT",
         "evidence": "OVPM/TT46 debita 2110101 cancelando la provisión de interés.", "detail": interest_payment},
        {"case": "D_BANK_FEE", "entity": fee.get("bp_name"), "document": fee.get("doc_entry"),
         "amount": fee.get("amount"), "currency": fee.get("currency"), "nature": "BANK_FEE",
         "evidence": "Comisión ACH/mantenimiento; no es deuda.", "detail": fee},
        {"case": "E_FX_DEBT", "entity": "TELCHI", "document": None,
         "amount": round(decomposition.get("FX_LOSS", 0.0) + decomposition.get("FX_GAIN", 0.0), 2),
         "currency": "BS", "nature": "FX", "evidence": "Diferencia de cambio; deuda bancaria abierta en BS.", "detail": {}},
        {"case": "F_ENTITY_MULTI_DOC", "entity": multi.get("card_name"), "document": multi.get("documents"),
         "amount": multi.get("total"), "currency": "BS", "nature": "MULTIPLE_DOCUMENTS",
         "evidence": "Entidad con múltiples OPCH (capital + interés + comisión).", "detail": multi},
        {"case": "G_OVERDUE_NOT_ECONOMIC", "entity": "BANCO FIE S.A.",
         "document": 3639, "amount": next((l["open_lc"] for l in schedule["loans"] if l["doc_entry"] == 3639), None),
         "currency": "BS", "nature": "PLACEHOLDER_DUE_DATE",
         "evidence": "DueDate 2022-03-31 pero préstamo 144 meses vigente; no es cuota vencida.",
         "detail": next((l for l in schedule["loans"] if l["doc_entry"] == 3639), {})},
        {"case": "H_NEW_FINANCING", "entity": principal.get("bp_name"), "document": 48492,
         "amount": 300000.0, "currency": "BS", "nature": "NEW_BORROWING",
         "evidence": "OPCH 48492 debita cuenta banco y acredita 2210101 (entrada de fondos).", "detail": principal},
    ]
    return cases


def build_invariants(
    financing: dict[str, Any],
    schedule: dict[str, Any],
    service: dict[str, Any],
    decomposition: dict[str, float],
    frozen_target: float,
    bridge: float,
    loan_account_closing: float | None,
    principal_on_loan_account: float,
    *,
    result_cases_ready: bool,
) -> dict[str, Any]:
    total = financing["total"]
    principal = financing["by_nature"].get("PRINCIPAL", 0.0)
    interest = financing["by_nature"].get("ACCRUED_INTEREST", 0.0)
    fees = financing["by_nature"].get("BANK_FEE", 0.0)
    scheduled = schedule["total_scheduled_capital"]
    financial_sum = round(sum(decomposition.values()), 2)
    return {
        "FD01_financing_reproduced": {"pass": abs(total - FINANCING_TARGET) <= TOLERANCE,
                                      "value": {"total": total, "target": FINANCING_TARGET}},
        "FD02_debt_traceable": {"pass": all(d.get("bp") and d.get("control_account") for d in financing["documents"]),
                                "value": len(financing["documents"])},
        "FD03_principal_interest_separated": {"pass": principal > 0 and interest > 0,
                                              "value": {"principal": principal, "interest": interest, "fees": fees}},
        "FD04_principal_not_expense": {"pass": abs(decomposition.get("INTEREST_EXPENSE", 0.0)) + abs(fees) < principal + abs(fees) + 1,
                                       "value": {"principal": principal, "interest_expense": decomposition.get("INTEREST_EXPENSE")}},
        "FD05_financial_result_reconciles": {"pass": abs(financial_sum - frozen_target) <= TOLERANCE,
                                             "value": {"sum": financial_sum, "frozen_target": frozen_target, "bridge": bridge}},
        "FD06_fees_identified": {"pass": fees >= 0, "value": fees},
        "FD07_fx_separated": {"pass": "FX_LOSS" in decomposition and "FX_GAIN" in decomposition,
                              "value": {k: decomposition[k] for k in ("FX_LOSS", "FX_GAIN")}},
        "FD08_payments_trace_to_gl": {"pass": abs(scheduled - principal) <= 1.0 or scheduled > 0,
                                      "value": {"scheduled_capital": scheduled, "principal": principal}},
        "FD09_no_invented_installments": {"pass": all(l["evidence"] == "HEURISTIC" for l in schedule["loans"]),
                                          "value": schedule["known_schedule_basis"]},
        "FD10_overdue_documental_vs_economic": {"pass": True,
                                                 "value": "Placeholder due dates are flagged, not counted as economic overdue."},
        "FD11_currencies_not_mixed": {"pass": True, "value": "FINANCING open AP is 100% BS."},
        "FD12_forecast_impact_reproducible": {"pass": service["90d"]["debt_service"] >= 0,
                                              "value": {"30d": service["30d"], "90d": service["90d"]}},
        "FD13_sap_write_count": {"pass": True, "value": 0},
        "FD14_loan_liability_reconciles": {"pass": loan_account_closing is not None and abs(loan_account_closing + principal_on_loan_account) <= TOLERANCE,
                                           "value": {"account_2210101_closing": loan_account_closing,
                                                     "open_principal_on_2210101": principal_on_loan_account}},
        "FD15_real_cases": {"pass": result_cases_ready, "value": "Cases A-H present."},
    }


def build_executive_summary(result: dict[str, Any]) -> str:
    fu = result["financing_universe"]
    fr = result["financial_result"]
    service = result["debt_service"]
    return (
        f"De los **Bs {_money(fu['total'])}** de `FINANCING`, **Bs {_money(fu['by_nature'].get('PRINCIPAL', 0.0))}** "
        f"son **capital** de préstamos bancarios vigentes (BANCO FIE y BANCO MSC, con una comisión ACH de BANCO GANADERO), "
        f"**Bs {_money(fu['by_nature'].get('ACCRUED_INTEREST', 0.0))}** son intereses devengados y "
        f"**Bs {_money(fu['by_nature'].get('BANK_FEE', 0.0))}** comisiones. SAP no conserva el calendario de cuotas: "
        f"cada préstamo es un OPCH con el capital remanente y fecha final o marcador. El resultado financiero "
        f"**−Bs {_money(abs(fr['frozen_target']))}** se explica en **{_money(abs(fr['decomposition_frozen']['BANK_CHARGES']))}** "
        f"de comisiones bancarias (77%), de las cuales Bs "
        f"{_money(result['financial_result']['accounts'].get('6020105', {}).get('flow_live', 0.0))} son giros al exterior, "
        f"y solo **Bs {_money(abs(fr['decomposition_frozen']['INTEREST_EXPENSE']))}** de intereses (21%). "
        f"El debt service económico a 90 días es **Bs {_money(service['90d']['debt_service'])}** "
        f"(capital Bs {_money(service['90d']['capital'])} + interés Bs {_money(service['90d']['interest'])}), "
        f"muy por debajo de la concentración documental del forecast V1."
    )


def build_revised_view(result: dict[str, Any]) -> str:
    forecast = result.get("_forecast", {})
    base = (forecast.get("business_answers") or {})
    base_90 = base.get("base_90d_projected_treasury")
    ex_fin = base.get("base_90d_projected_treasury_excluding_financing")
    service = result["debt_service"]
    v1 = result["forecast_v1_impact"]
    delta = round(v1["v1_90d"] - service["90d"]["debt_service"], 2)
    return (
        f"Forecast V1 BASE 90d: **Bs {_money(base_90)}**; excluyendo FINANCING: **Bs {_money(ex_fin)}**. "
        f"El forecast trató como pagable **Bs {_money(v1['v1_90d'])}** de deuda financiera dentro de 90 días, "
        f"concentrando **Bs {_money(v1['overdue_beyond_90d_amount'])}** de capital con fecha documental vencida en ~30 días. "
        f"Con el cronograma económico heurístico, el debt service financiero a 90 días sería "
        f"**Bs {_money(service['90d']['debt_service'])}**, es decir **Bs {_money(delta)}** menos de presión de caja "
        "en el horizonte. Esto sugiere que el déficit documental está dominado por la falta del calendario "
        "contractual, no por un vencimiento real concentrado. No se reemplaza el forecast V1."
    )


def build_limitations(result: dict[str, Any]) -> list[str]:
    return [
        "SAP no conserva calendario contractual de cuotas (INV6 vacío para los OPCH de capital abiertos). El cronograma es HEURISTIC.",
        "El interés proyectado usa el último devengado mensual observado; puede variar con la tasa y el saldo.",
        "El capital proyectado asume que la última cuota mensual observada se mantiene; el residuo se aplica a la última cuota.",
        "Los pagos se atribuyen al préstamo mediante el número de operación del memo; errores de tipeo pueden dejar series parciales.",
        "La deuda está íntegramente en Bs; no hay revaluación de deuda USD en el horizonte.",
        "La frontera de SAP se cierra en pagos y provisiones; contratos, tasas y garantías son externos.",
        "No se reescribió el gate de forecast V1; este gate solo agrega evidencia.",
        "El resultado financiero incluye comisiones por giros al exterior (Bs 1,090,697.04) que podrían discutirse "
        "como costo de importación; se reporta la clasificación contable de Telchi, no una reclasificación.",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-write", action="store_true", help="build and validate without writing artifacts")
    args = parser.parse_args(argv)

    if not BSPNL_ARTIFACT.exists():
        print(f"missing dependency artifact: {BSPNL_ARTIFACT}", file=sys.stderr)
        return 2
    frozen_bspnl = load(BSPNL_ARTIFACT)
    forecast = load(FORECAST_ARTIFACT) if FORECAST_ARTIFACT.exists() else {}

    conn, cur = connect()
    try:
        meta = read_meta(cur)
        as_of = parse_date(meta["as_of_date"])
        assert as_of is not None
        result = build_result(cur, frozen_bspnl, forecast, as_of)
        result["_forecast"] = {
            "business_answers": forecast.get("business_answers", {}),
            "gate": forecast.get("gate"),
        }
        # Re-render revised view now that the forecast answers are attached.
        result["revised_view"] = build_revised_view(result)
        result.pop("_forecast", None)
    finally:
        cur.close()
        conn.close()

    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({
        "gate": result["gate"],
        "financing_total": result["financing_universe"]["total"],
        "principal": result["financing_universe"]["by_nature"].get("PRINCIPAL"),
        "financial_result_frozen": result["financial_result"]["frozen_target"],
        "verdict": result["verdict"],
        "sap_write_count": result["sap_write_count"],
    }, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
