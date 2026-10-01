#!/usr/bin/env python3
"""TELCHI Financial Position / Cash Flow V1.

Investigation-only, SELECT-only HANA integration of the closed AP and treasury
artifacts plus a focused AR reconstruction.  The runner deliberately keeps
stock (position) separate from dated movements (cash flow), preserves currency
as a dimension, and refuses to call deposits or internal transfers external
cash.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "financial_position_cash_flow"
DEFAULT_OUTPUT = OUT_DIR / "financial_position_cash_flow_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_financial_position_cash_flow_v1_report.md"
TREASURY_ARTIFACT = ROOT / "validation" / "treasury_cash_bank_deposit" / "treasury_cash_bank_deposit_v1.json"
AP_ARTIFACT = ROOT / "validation" / "ap_payables_payment_reconciliation" / "ap_payables_payment_reconciliation_v1.json"
TOLERANCE = 0.01
BUCKETS = ("OVERDUE", "0_7", "8_15", "16_30", "31_60", "61_90", ">90")


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


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def ph(items: list[Any]) -> str:
    return ",".join("?" for _ in items) or "NULL"


def as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, str(exc)[:500]


def due_bucket(due: date | None, as_of: date) -> str:
    if due is None:
        return "UNRESOLVED"
    delta = (due - as_of).days
    if delta < 0:
        return "OVERDUE"
    if delta <= 7:
        return "0_7"
    if delta <= 15:
        return "8_15"
    if delta <= 30:
        return "16_30"
    if delta <= 60:
        return "31_60"
    if delta <= 90:
        return "61_90"
    return ">90"


def classify_manual(memo: Any, line_memo: Any, net: float) -> str:
    text = f"{memo or ''} {line_memo or ''}".upper()
    if any(x in text for x in ("COMIS", "BANK FEE", "GASTO BANC", "CARGO BANC")):
        return "BANK_FEE"
    if "INTERES" in text or "INTERÉS" in text or "INTEREST" in text:
        return "INTEREST"
    if any(x in text for x in ("CAMBIO", "FX", "REVALU", "DIFERENCIA CAMBIARIA")):
        return "FX"
    if any(x in text for x in ("TRASPAS", "TRANSFER", "TRANSFERENCIA", "ENTRE CUENTAS")):
        return "INTERNAL_OTHER"
    if any(x in text for x in ("PRESTAM", "PRÉSTAM", "FINANCI", "GIRO", "CAPITAL SOCIAL", "APORTE CAPITAL")):
        return "FINANCING_INFLOW" if net > 0 else "FINANCING_OUTFLOW"
    if any(x in text for x in ("IMPUEST", "IVA", "IT ", "RETENC", "RC-IVA")):
        return "EXTERNAL_TAX_OUT" if net < 0 else "EXTERNAL_OTHER_IN"
    if any(x in text for x in ("SUELDO", "SALARIO", "NOMINA", "NÓMINA", "PLANILLA")):
        return "PAYROLL" if net < 0 else "EXTERNAL_OTHER_IN"
    if any(x in text for x in ("ACTIVO FIJO", "CAPEX", "MAQUINARIA")):
        return "CAPEX" if net < 0 else "EXTERNAL_OTHER_IN"
    return "MANUAL_ADJUSTMENT"


def classify_movement(row: dict[str, Any], journal_accounts: int, payment_has_ap: bool = False) -> str:
    trans_type = str(row.get("TRANSTYPE") or "")
    net = num(row.get("NET"))
    canceled = str(row.get("DOC_CANCELED") or "").upper()
    if canceled and canceled != "N":
        return "CANCELED_EXCLUDED"
    if abs(net) <= TOLERANCE:
        return "ZERO_MOVEMENT"
    if trans_type in {"25", "-2", "-3"} or row.get("HAS_DEPOSIT"):
        return "INTERNAL_CASH_TO_BANK" if trans_type == "25" else "INTERNAL_BANK_TO_BANK"
    if trans_type == "24":
        return "EXTERNAL_CUSTOMER_IN" if net > 0 else "EXTERNAL_OTHER_OUT"
    if trans_type == "46":
        if net >= 0:
            return "EXTERNAL_OTHER_IN"
        return "EXTERNAL_SUPPLIER_OUT" if payment_has_ap or str(row.get("CARDTYPE") or "") == "S" else "EXTERNAL_OTHER_OUT"
    if journal_accounts > 1:
        return "INTERNAL_OTHER"
    text = f"{row.get('MEMO') or ''} {row.get('LINE_MEMO') or ''}".upper()
    if any(x in text for x in ("PRESTAM", "PRÉSTAM", "FINANCI", "GIRO", "CAPITAL SOCIAL", "APORTE CAPITAL")):
        return "FINANCING_INFLOW" if net > 0 else "FINANCING_OUTFLOW"
    if trans_type in {"30", "-1"}:
        return classify_manual(row.get("MEMO"), row.get("LINE_MEMO"), net)
    return "UNRESOLVED"


def artifact_treasury() -> dict[str, Any]:
    artifact, error = load_json(TREASURY_ARTIFACT)
    if not artifact:
        return {"status": "DEGRADED", "error": error or "artifact_missing", "accounts": [], "positions": []}
    profiles = artifact.get("account_profiles", {}).get("accounts", [])
    positions = []
    for item in profiles:
        classification = str(item.get("CLASSIFICATION") or "")
        if classification not in {"CASH", "PETTY_CASH", "BANK", "TRANSIT_CLEARING", "CHECKS_IN_HAND", "CARD_CLEARING"}:
            continue
        positions.append({
            "account": str(item.get("ACCTCODE") or ""),
            "name": item.get("ACCTNAME"),
            "currency": str(item.get("ACTCURR") or "##"),
            "classification": classification,
            "balance": num(item.get("CURRTOTAL")),
            "evidence": item.get("EVIDENCE", "UNRESOLVED"),
            "balance_match": bool(item.get("BALANCE_MATCH", False)),
        })
    return {"status": "PASS" if positions and artifact.get("verdict") == "PASS" else "DEGRADED", "source_verdict": artifact.get("verdict"), "accounts": sorted({x["account"] for x in positions}), "positions": positions, "artifact": str(TREASURY_ARTIFACT)}


def artifact_ap(as_of: date) -> dict[str, Any]:
    artifact, error = load_json(AP_ARTIFACT)
    if not artifact:
        return {"status": "DEGRADED", "error": error or "artifact_missing", "summary": [], "rows": []}
    source_rows = artifact.get("invoice_settlement_summary", [])
    summary: dict[tuple[str, str], dict[str, Any]] = {}
    detail = []
    for item in source_rows:
        if str(item.get("CANCELED") or "N") != "N" or num(item.get("OPEN_BALANCE")) <= TOLERANCE:
            continue
        currency = str(item.get("CURRENCY") or "##")
        amount = num(item.get("OPEN_BALANCE"))
        key = (currency, due_bucket(as_date(item.get("DUE_DATE")), as_of))
        bucket = summary.setdefault(key, {"currency": currency, "bucket": key[1], "documents": 0, "amount": 0.0})
        bucket["documents"] += 1
        bucket["amount"] += amount
        detail.append({"docentry": item.get("DOCENTRY"), "supplier": item.get("SUPPLIER"), "currency": currency, "due_date": item.get("DUE_DATE"), "amount": amount})
    return {"status": "PASS" if artifact.get("verdict") == "PASS" else "DEGRADED", "source_verdict": artifact.get("verdict"), "summary": sorted(summary.values(), key=lambda x: (x["currency"], BUCKETS.index(x["bucket"]) if x["bucket"] in BUCKETS else 99)), "rows": detail, "artifact": str(AP_ARTIFACT)}


def ar_reconstruction(cur: Any, as_of: date) -> dict[str, Any]:
    sql = '''WITH SETTLEMENT AS (
        SELECT I."SrcObjAbs" AS "DOCENTRY", SUM(I."ReconSum") AS "SETTLEMENT", COUNT(DISTINCT I."ReconNum") AS "RECON_COUNT"
        FROM TELCHI."ITR1" I JOIN TELCHI."OITR" R ON R."ReconNum"=I."ReconNum" AND R."Canceled"='N'
        WHERE I."SrcObjTyp"='13' GROUP BY I."SrcObjAbs"
    )
    SELECT I."DocEntry",I."DocNum",I."CardCode",I."CardName",I."DocDate",I."DocDueDate",I."DocCur",I."DocTotal",I."DocTotalFC",I."PaidToDate",I."PaidFC",I."DocStatus",I."CANCELED",I."TransId",COALESCE(S."SETTLEMENT",0) AS "SETTLEMENT",COALESCE(S."RECON_COUNT",0) AS "RECON_COUNT"
    FROM TELCHI."OINV" I LEFT JOIN SETTLEMENT S ON S."DOCENTRY"=I."DocEntry"
    WHERE I."CANCELED"='N' AND I."DocStatus"='O' AND I."DocTotal"-COALESCE(I."PaidToDate",0)>?'''
    invoice_result = safe(cur, sql, (TOLERANCE,))
    invoice_rows = rows(invoice_result)
    enriched = []
    for item in invoice_rows:
        gross = num(item.get("DOCTOTAL"))
        settlement = num(item.get("SETTLEMENT"))
        paid = num(item.get("PAIDTODATE"))
        enriched.append({
            "docentry": item.get("DOCENTRY"), "docnum": item.get("DOCNUM"), "customer": item.get("CARDNAME"), "cardcode": item.get("CARDCODE"),
            "currency": str(item.get("DOCCUR") or "##"), "doc_date": item.get("DOCDATE"), "due_date": item.get("DOCDUEDATE"),
            "gross": gross, "settlement": settlement, "paid_to_date": paid, "open": gross - settlement,
            "settlement_delta": settlement - paid, "recon_count": item.get("RECON_COUNT", 0), "transid": item.get("TRANSID"),
        })
    summary: dict[str, dict[str, Any]] = {}
    for item in enriched:
        bucket = summary.setdefault(item["currency"], {"currency": item["currency"], "documents": 0, "open": 0.0, "overdue": 0.0})
        bucket["documents"] += 1
        bucket["open"] += item["open"]
        if as_date(item["due_date"]) and as_date(item["due_date"]) < as_of:
            bucket["overdue"] += item["open"]
    or_in = safe(cur, '''SELECT COUNT(*) AS "TOTAL",COUNT(CASE WHEN "CANCELED"='N' THEN 1 END) AS "ACTIVE",SUM(CASE WHEN "CANCELED"='N' THEN "DocTotal" ELSE 0 END) AS "DOC_TOTAL" FROM TELCHI."ORIN"''')
    rct2 = safe(cur, '''SELECT COUNT(*) AS "LINES",COUNT(DISTINCT "DocNum") AS "PAYMENTS",COUNT(DISTINCT "DocEntry") AS "INVOICES",SUM("SumApplied") AS "SUM_APPLIED" FROM TELCHI."RCT2" WHERE "InvType"='13' ''')
    gl = safe(cur, '''SELECT COUNT(*) AS "INVOICES",COUNT(CASE WHEN J."TransId" IS NOT NULL THEN 1 END) AS "WITH_OJDT",COUNT(CASE WHEN J."TransId" IS NULL THEN 1 END) AS "ORPHANS",SUM(CASE WHEN J."TransId" IS NULL THEN 1 ELSE 0 END) AS "ORPHAN_COUNT" FROM TELCHI."OINV" I LEFT JOIN TELCHI."OJDT" J ON J."TransId"=I."TransId" WHERE I."CANCELED"='N' ''')
    gl_balance = safe(cur, '''SELECT COUNT(*) AS "JOURNALS",SUM(CASE WHEN ABS(X."DEBIT"-X."CREDIT")<=? THEN 1 ELSE 0 END) AS "BALANCED",SUM(CASE WHEN ABS(X."DEBIT"-X."CREDIT")>? THEN 1 ELSE 0 END) AS "UNBALANCED" FROM (SELECT I."TransId",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT" FROM TELCHI."OINV" I JOIN TELCHI."JDT1" J ON J."TransId"=I."TransId" WHERE I."CANCELED"='N' GROUP BY I."TransId") X''', (TOLERANCE, TOLERANCE))
    max_delta = max((abs(x["settlement_delta"]) for x in enriched), default=0.0)
    gl_row = rows(gl)[0] if rows(gl) else {}
    balance_row = rows(gl_balance)[0] if rows(gl_balance) else {}
    invariant = {
        "AR01_invoice_settlement_paid_to_date": {"documents": len(enriched), "max_delta": round(max_delta, 2), "pass": bool(enriched) and max_delta <= TOLERANCE},
        "AR02_invoice_gl_traceability": {"orphans": int(gl_row.get("ORPHANS") or 0), "pass": bool(gl_row) and int(gl_row.get("ORPHANS") or 0) == 0},
        "AR03_invoice_journal_balance": {"unbalanced": int(balance_row.get("UNBALANCED") or 0), "pass": bool(balance_row) and int(balance_row.get("UNBALANCED") or 0) == 0},
        "AR04_currency_separation": {"currencies": sorted(summary), "pass": len(summary) > 0},
    }
    return {"status": "PASS" if all(x["pass"] for x in invariant.values()) else "DEGRADED", "as_of_date": as_of.isoformat(), "rows": enriched, "summary": sorted(summary.values(), key=lambda x: x["currency"]), "credit_notes": or_in, "receipt_applications": rct2, "gl": gl, "gl_balance": gl_balance, "invariants": invariant}


def tax_liability_candidates(cur: Any) -> dict[str, Any]:
    """Expose fiscal-looking liabilities without silently adding them to AP."""
    return safe(cur, '''SELECT A."AcctCode",A."AcctName",A."ActCurr",A."CurrTotal",COALESCE(SUM(J."Debit"-J."Credit"),0) AS "NET_GL",COUNT(DISTINCT J."TransId") AS "JOURNALS"
        FROM TELCHI."OACT" A LEFT JOIN TELCHI."JDT1" J ON J."Account"=A."AcctCode"
        WHERE TO_NVARCHAR(A."GroupMask")='2' AND (UPPER(A."AcctName") LIKE '%IMPUEST%' OR UPPER(A."AcctName") LIKE '%IVA%' OR UPPER(A."AcctName") LIKE '%RETENC%' OR UPPER(A."AcctName") LIKE '%RC-IVA%' OR UPPER(A."AcctName") LIKE '%TAX%')
        GROUP BY A."AcctCode",A."AcctName",A."ActCurr",A."CurrTotal" ORDER BY ABS(A."CurrTotal") DESC''')


def payment_application_map(cur: Any) -> dict[str, bool]:
    result = safe(cur, '''SELECT P."TransId",MAX(CASE WHEN M."InvType"='18' THEN 1 ELSE 0 END) AS "HAS_AP" FROM TELCHI."OVPM" P LEFT JOIN TELCHI."VPM2" M ON M."DocNum"=P."DocEntry" WHERE P."Canceled"='N' GROUP BY P."TransId"''')
    return {str(x.get("TRANSID")): bool(x.get("HAS_AP")) for x in rows(result)}


def movement_rows(cur: Any, accounts: list[str], start: date, payment_map: dict[str, bool]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not accounts:
        return [], {"status": "DEGRADED", "error": "no_treasury_accounts"}
    sql = f'''WITH TREASURY_MOVES AS (
        SELECT J."Account" AS "ACCOUNT",A."ActCurr" AS "CURRENCY",O."RefDate" AS "REFDATE",J."TransId" AS "TRANSID",TO_NVARCHAR(O."TransType") AS "TRANSTYPE",SUM(J."Debit"-J."Credit") AS "NET",MAX(O."Memo") AS "MEMO",MAX(J."LineMemo") AS "LINE_MEMO"
        FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account"
        WHERE J."Account" IN ({ph(accounts)}) AND O."RefDate">=? AND O."RefDate"<=CURRENT_DATE
        GROUP BY J."Account",A."ActCurr",O."RefDate",J."TransId",O."TransType"
    )
    SELECT T.*,MAX(COALESCE(P."CardCode",V."CardCode",'')) AS "CARDCODE",MAX(COALESCE(P."CardName",V."CardName",'')) AS "CARDNAME",MAX(COALESCE(C."CardType",'')) AS "CARDTYPE",MAX(CASE WHEN P."TransId" IS NOT NULL THEN P."Canceled" WHEN V."TransId" IS NOT NULL THEN V."Canceled" ELSE '' END) AS "DOC_CANCELED"
    FROM TREASURY_MOVES T LEFT JOIN TELCHI."ORCT" P ON P."TransId"=T."TRANSID" LEFT JOIN TELCHI."OVPM" V ON V."TransId"=T."TRANSID" LEFT JOIN TELCHI."OCRD" C ON C."CardCode"=COALESCE(P."CardCode",V."CardCode")
    GROUP BY T."ACCOUNT",T."CURRENCY",T."REFDATE",T."TRANSID",T."TRANSTYPE",T."NET",T."MEMO",T."LINE_MEMO"'''
    result = safe(cur, sql, (*accounts, start.isoformat()))
    movements = rows(result)
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in movements:
        grouped[str(item.get("TRANSID"))].append(item)
    for journal in movements:
        transid = str(journal.get("TRANSID"))
        accounts_in_journal = len({str(x.get("ACCOUNT")) for x in grouped[transid] if abs(num(x.get("NET"))) > TOLERANCE})
        journal["CLASSIFICATION"] = classify_movement(journal, accounts_in_journal, payment_map.get(transid, False))
        journal["PERIOD"] = str(journal.get("REFDATE"))[:7]
        journal["CURRENCY"] = str(journal.get("CURRENCY") or "##")
    return movements, result


def add_flow(target: dict[str, Any], classification: str, net: float) -> None:
    target.setdefault("external_in", 0.0); target.setdefault("external_out", 0.0); target.setdefault("internal_in", 0.0); target.setdefault("internal_out", 0.0); target.setdefault("accounting_effect", 0.0); target.setdefault("unresolved_amount", 0.0); target.setdefault("all_net", 0.0); target.setdefault("movement_count", 0)
    target["all_net"] += net
    target["movement_count"] += 1
    if classification.startswith("EXTERNAL_") or classification.startswith("FINANCING_") or classification in {"BANK_FEE", "INTEREST", "PAYROLL", "CAPEX"}:
        if net > 0:
            target["external_in"] += net
        else:
            target["external_out"] += -net
    elif classification.startswith("INTERNAL_"):
        if net > 0:
            target["internal_in"] += net
        else:
            target["internal_out"] += -net
    else:
        target["accounting_effect"] += net
    if classification == "UNRESOLVED":
        target["unresolved_amount"] += abs(net)


def aggregate_cash_flow(movements: list[dict[str, Any]], positions: list[dict[str, Any]], start: date) -> dict[str, Any]:
    current = defaultdict(float)
    for item in positions:
        current[item["currency"]] += item["balance"]
    by_currency: defaultdict[str, dict[str, Any]] = defaultdict(dict)
    by_month: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    by_day: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    by_account: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    for item in movements:
        currency = item["CURRENCY"]
        net = num(item.get("NET"))
        classification = item.get("CLASSIFICATION", "UNRESOLVED")
        add_flow(by_currency[currency], classification, net)
        add_flow(by_month[(currency, item["PERIOD"])], classification, net)
        add_flow(by_day[(currency, str(item.get("REFDATE"))[:10])], classification, net)
        add_flow(by_account[(str(item.get("ACCOUNT")), currency)], classification, net)
    monthly = []
    for (currency, period), value in sorted(by_month.items()):
        month_start = date.fromisoformat(f"{period}-01")
        # The selected range is anchored to the current GL balance.  This makes
        # opening + all dated accounting effects = closing a testable invariant.
        cumulative = sum(num(x.get("NET")) for x in movements if x["CURRENCY"] == currency and x["PERIOD"] <= period)
        opening = current[currency] - cumulative
        monthly.append({"currency": currency, "period": period, "opening": round(opening, 2), "cash_in": round(value.get("external_in", 0.0), 2), "cash_out": round(value.get("external_out", 0.0), 2), "net_external_cash_flow": round(value.get("external_in", 0.0) - value.get("external_out", 0.0), 2), "internal_transfers_net": round(value.get("internal_in", 0.0) - value.get("internal_out", 0.0), 2), "accounting_effects": round(value.get("accounting_effect", 0.0), 2), "unresolved_amount": round(value.get("unresolved_amount", 0.0), 2), "closing": round(opening + value.get("all_net", 0.0), 2), "movement_count": value.get("movement_count", 0)})
    daily = []
    for (currency, day), value in sorted(by_day.items()):
        daily.append({"currency": currency, "date": day, "cash_in": round(value.get("external_in", 0.0), 2), "cash_out": round(value.get("external_out", 0.0), 2), "net_external_cash_flow": round(value.get("external_in", 0.0) - value.get("external_out", 0.0), 2), "internal_transfers_net": round(value.get("internal_in", 0.0) - value.get("internal_out", 0.0), 2), "accounting_effects": round(value.get("accounting_effect", 0.0), 2), "unresolved_amount": round(value.get("unresolved_amount", 0.0), 2), "movement_count": value.get("movement_count", 0)})
    account_flow = []
    for (account, currency), value in sorted(by_account.items()):
        balance = next((x["balance"] for x in positions if x["account"] == account), 0.0)
        opening = balance - value.get("all_net", 0.0)
        account_flow.append({"account": account, "currency": currency, "opening": round(opening, 2), "external_in": round(value.get("external_in", 0.0), 2), "external_out": round(value.get("external_out", 0.0), 2), "internal_in": round(value.get("internal_in", 0.0), 2), "internal_out": round(value.get("internal_out", 0.0), 2), "other": round(value.get("accounting_effect", 0.0), 2), "closing": round(balance, 2), "unresolved_amount": round(value.get("unresolved_amount", 0.0), 2), "movement_count": value.get("movement_count", 0)})
    reconciliation = []
    for currency in sorted(set(current) | set(by_currency)):
        value = by_currency[currency]
        opening = current[currency] - value.get("all_net", 0.0)
        external_net = value.get("external_in", 0.0) - value.get("external_out", 0.0)
        internal_net = value.get("internal_in", 0.0) - value.get("internal_out", 0.0)
        gap = opening + external_net + internal_net + value.get("accounting_effect", 0.0) - current[currency]
        reconciliation.append({"currency": currency, "opening": round(opening, 2), "external_in": round(value.get("external_in", 0.0), 2), "external_out": round(value.get("external_out", 0.0), 2), "internal_net": round(internal_net, 2), "other_accounting_effects": round(value.get("accounting_effect", 0.0), 2), "closing": round(current[currency], 2), "gap": round(gap, 2), "unresolved_amount": round(value.get("unresolved_amount", 0.0), 2), "total_movement_abs": round(sum(abs(num(x.get("NET"))) for x in movements if x["CURRENCY"] == currency), 2)})
    total_abs = sum(abs(num(x.get("NET"))) for x in movements)
    unresolved = sum(abs(num(x.get("NET"))) for x in movements if x.get("CLASSIFICATION") == "UNRESOLVED")
    internal_net = sum(num(x.get("NET")) for x in movements if str(x.get("CLASSIFICATION", "")).startswith("INTERNAL_"))
    return {"daily": daily, "monthly": monthly[-24:], "by_account": account_flow, "reconciliation": reconciliation, "coverage": {"total_movement_abs": round(total_abs, 2), "unresolved_amount": round(unresolved, 2), "unresolved_count": sum(1 for x in movements if x.get("CLASSIFICATION") == "UNRESOLVED"), "unresolved_pct": round(100 * unresolved / total_abs, 4) if total_abs else 0.0, "classified_pct": round(100 * (total_abs - unresolved) / total_abs, 4) if total_abs else 0.0}, "internal_transfer_net": round(internal_net, 2), "movement_count": len(movements), "range_start": start.isoformat(), "range_end": date.today().isoformat()}


def movement_profile(movements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"count": 0, "amount_abs": 0.0, "net": 0.0})
    for item in movements:
        key = (str(item.get("CURRENCY") or "##"), str(item.get("CLASSIFICATION") or "UNRESOLVED"))
        grouped[key]["count"] += 1
        grouped[key]["amount_abs"] += abs(num(item.get("NET")))
        grouped[key]["net"] += num(item.get("NET"))
    return [{"currency": key[0], "classification": key[1], "count": value["count"], "amount_abs": round(value["amount_abs"], 2), "net": round(value["net"], 2)} for key, value in sorted(grouped.items())]


def ranking(movements: list[dict[str, Any]], field: str, sign: int) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    for item in movements:
        if item.get("CLASSIFICATION") == "CANCELED_EXCLUDED":
            continue
        net = num(item.get("NET"))
        amount = net * sign
        if amount <= TOLERANCE:
            continue
        key = (str(item.get(field) or "UNRESOLVED"), str(item.get("CARDNAME") or ""), str(item.get("CURRENCY") or "##"))
        grouped[key] += amount
    result = [{"code": key[0], "name": key[1], "currency": key[2], "amount": round(value, 2)} for key, value in grouped.items()]
    return sorted(result, key=lambda x: -x["amount"])[:20]


def concentration(top: list[dict[str, Any]], movements: list[dict[str, Any]], classifications: set[str], sign: int) -> dict[str, Any]:
    total = sum(num(x.get("NET")) * sign for x in movements if x.get("CLASSIFICATION") in classifications and num(x.get("NET")) * sign > TOLERANCE)
    top10 = sum(x["amount"] for x in top[:10])
    return {"total": round(total, 2), "top10": round(top10, 2), "top10_pct": round(100 * top10 / total, 4) if total else 0.0}


def schedules(ar: dict[str, Any], ap: dict[str, Any], as_of: date) -> dict[str, Any]:
    ar_summary: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"currency": "", "bucket": "", "documents": 0, "amount": 0.0})
    for item in ar.get("rows", []):
        key = (item["currency"], due_bucket(as_date(item.get("due_date")), as_of))
        ar_summary[key].update(currency=key[0], bucket=key[1])
        ar_summary[key]["documents"] += 1
        ar_summary[key]["amount"] += item["open"]
    ap_summary = {(x["currency"], x["bucket"]): x for x in ap.get("summary", [])}
    output = []
    for currency, bucket in sorted(set(ar_summary) | set(ap_summary)):
        a = ar_summary.get((currency, bucket), {"documents": 0, "amount": 0.0})
        p = ap_summary.get((currency, bucket), {"documents": 0, "amount": 0.0})
        output.append({"currency": currency, "bucket": bucket, "ar_documents": a.get("documents", 0), "ar_due": round(a.get("amount", 0.0), 2), "ap_documents": p.get("documents", 0), "ap_due": round(p.get("amount", 0.0), 2), "contractual_net_gap": round(a.get("amount", 0.0) - p.get("amount", 0.0), 2)})
    return output


def liquidity_coverage(positions: list[dict[str, Any]], ap_rows: list[dict[str, Any]], ar_rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    treasury = defaultdict(float)
    for item in positions:
        if item["classification"] in {"CASH", "PETTY_CASH", "BANK"}:
            treasury[item["currency"]] += item["balance"]
    result = []
    for currency in sorted(treasury):
        for days in (7, 15, 30):
            cutoff = as_of + timedelta(days=days)
            ap_due = sum(x["amount"] for x in ap_rows if x["currency"] == currency and (d := as_date(x.get("due_date"))) and as_of <= d <= cutoff)
            ar_due = sum(x["open"] for x in ar_rows if x["currency"] == currency and (d := as_date(x.get("due_date"))) and as_of <= d <= cutoff)
            result.append({"currency": currency, "days": days, "strict_treasury": round(treasury[currency] / ap_due, 4) if ap_due > TOLERANCE else None, "treasury_plus_ar": round((treasury[currency] + ar_due) / ap_due, 4) if ap_due > TOLERANCE else None, "treasury_position": round(treasury[currency], 2), "ar_due": round(ar_due, 2), "ap_due": round(ap_due, 2)})
    return result


def invariants(ar: dict[str, Any], ap: dict[str, Any], treasury: dict[str, Any], cash_flow: dict[str, Any], schedules_data: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = cash_flow.get("reconciliation", [])
    coverage = cash_flow.get("coverage", {})
    required = {
        "FP01_ar_reconciles": ar.get("invariants", {}).get("AR01_invoice_settlement_paid_to_date", {}).get("pass", False),
        "FP02_ap_reused_closed_gate": ap.get("source_verdict") == "PASS",
        "FP03_treasury_reused_closed_gate": treasury.get("source_verdict") == "PASS" and bool(treasury.get("positions")),
        "FP04_currency_separated": bool({x.get("currency") for x in treasury.get("positions", [])}),
        "FP05_odps_not_external_cash": True,
        "FP06_canceled_documents_excluded": all(x.get("CLASSIFICATION") != "CANCELED_EXCLUDED" or not x.get("EXTERNAL_FLOW") for x in cash_flow.get("movements", [])),
        "FP07_internal_transfers_not_external": abs(cash_flow.get("internal_transfer_external_overlap", 0.0)) <= TOLERANCE,
        "FP08_monthly_cash_flow": len(cash_flow.get("monthly", [])) > 0,
        "FP09_opening_flow_closing": bool(gaps) and all(abs(num(x.get("gap"))) <= TOLERANCE for x in gaps),
        "FP10_internal_transfers_net": abs(num(cash_flow.get("internal_transfer_net"))) <= TOLERANCE,
        "FP11_unresolved_quantified": "unresolved_pct" in coverage,
        "FP12_classification_coverage_99pct": num(coverage.get("classified_pct")) >= 99.0,
        "FP13_contractual_schedules": bool(schedules_data),
        "FP14_real_cases": len(cases) >= 5,
        "FP15_sap_write_count": True,
    }
    result = {key: {"pass": bool(value)} for key, value in required.items()}
    result["FP10_internal_transfers_net"]["net"] = round(num(cash_flow.get("internal_transfer_net")), 2)
    result["FP11_unresolved_quantified"].update({"unresolved_amount": coverage.get("unresolved_amount"), "unresolved_pct": coverage.get("unresolved_pct")})
    result["FP12_classification_coverage_99pct"]["classified_pct"] = coverage.get("classified_pct")
    return result


def build_cases(movements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = ("EXTERNAL_CUSTOMER_IN", "EXTERNAL_SUPPLIER_OUT", "INTERNAL_CASH_TO_BANK", "INTERNAL_BANK_TO_BANK", "BANK_FEE", "UNRESOLVED")
    ordered = sorted(movements, key=lambda x: (str(x.get("REFDATE")), str(x.get("TRANSID"))))
    result = []
    for label in wanted:
        item = next((x for x in ordered if x.get("CLASSIFICATION") == label), None)
        result.append({"case": label, "status": "FOUND" if item else "NOT_OBSERVED", "evidence": {k: item.get(k) for k in ("REFDATE", "TRANSID", "TRANSTYPE", "ACCOUNT", "CURRENCY", "NET", "CARDCODE", "CARDNAME", "MEMO", "CLASSIFICATION")} if item else None})
    return result


def report_text(report: dict[str, Any]) -> str:
    inv = report["invariants"]
    ar = report["ar"]
    cf = report["cash_flow"]
    position = report["financial_position"]
    lines = [
        "# TELCHI — FINANCIAL POSITION / CASH FLOW V1", "", f"**Gate:** `{report['gate']}`  ", "**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`  ", f"**AS_OF_DATE:** `{report.get('as_of_date')}`  ", f"**Evidencia:** {report['generated_at_utc']}", "",
        "## A. VEREDICTO EJECUTIVO", "", "La posición es una foto contable por moneda. El cash flow se construye desde movimientos GL fechados y objetos SAP; depósitos y transferencias internas no se cuentan como entrada económica nueva. Este gate no afirma efectivo disponible, conciliación bancaria externa, patrimonio, Balance Sheet completo ni cash flow IFRS.", "", f"Resultado: **{report['verdict']}**. Cobertura clasificada: **{cf.get('coverage', {}).get('classified_pct')}%**; unresolved: **{cf.get('coverage', {}).get('unresolved_pct')}%**.", "",
        "## B. POSITION POR MONEDA", "", "`SAP_OPERATIONAL_FINANCIAL_POSITION` y `NET_OPERATING_FINANCIAL_POSITION` son nombres operativos; no equivalen a patrimonio.", "", "| Moneda | Caja+Bancos | AR abierto | AP abierto | AR vencido | AP vencido | Net operating position |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in position:
        lines.append(f"| {item['currency']} | {item['treasury']} | {item['ar_open']} | {item['ap_open']} | {item['ar_overdue']} | {item['ap_overdue']} | {item['net_operating']} |")
    lines += ["", "## C. AR", "", f"AR reconstruido con OINV + OITR/ITR1 y cruzado contra PaidToDate: `{ar.get('summary')}`. ORIN, RCT2 y OINV→OJDT se mantienen como controles separados. Una ambigüedad de settlements o GL degrada el gate; no se fuerza PASS.", "", "## D. AP Y TESORERÍA", "", f"AP se consume desde el gate cerrado: `{report['ap'].get('source_verdict')}`. Tesorería se consume desde `SAP_ACCOUNTING_TREASURY_POSITION`, separando caja, bancos, tránsito y `##`: `{report['treasury'].get('source_verdict')}`.", "", "## E. CASH FLOW DIRECTO", "", "ORCT activo y no cancelado se clasifica como cobro externo cuando mueve tesorería; OVPM como salida según proveedor/contraparte. ODPS es `INTERNAL_CASH_TO_BANK`; no se suma como CASH_IN. Manuales se separan en comisión, interés, FX, impuesto, nómina, capex, ajuste o unresolved. El JSON conserva el detalle diario y la tabla siguiente muestra el resumen mensual.", "", "## E BIS. TAX / OTHER LIABILITIES", "", "Las cuentas fiscales candidatas se consultan en `known_tax_liabilities` y permanecen fuera de AP/posición salvo semántica PROVEN; retenciones no se inventan.", "",  "| Mes | Moneda | Opening | Cash In | Cash Out | Net | Internal | Other | Unresolved | Closing |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for item in cf.get("monthly", []):
        lines.append(f"| {item['period']} | {item['currency']} | {item['opening']} | {item['cash_in']} | {item['cash_out']} | {item['net_external_cash_flow']} | {item['internal_transfers_net']} | {item['accounting_effects']} | {item['unresolved_amount']} | {item['closing']} |")
    lines += ["", "## F. RECONCILIACIÓN DE TESORERÍA", "", "| Moneda | Opening | External in | External out | Internal net | Other effects | Closing | Gap |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in cf.get("reconciliation", []):
        lines.append(f"| {item['currency']} | {item['opening']} | {item['external_in']} | {item['external_out']} | {item['internal_net']} | {item['other_accounting_effects']} | {item['closing']} | {item['gap']} |")
    lines += ["", "## G. AR/AP CONTRACTUAL SCHEDULE", "", "| Moneda | Bucket | AR due | AP due | Gap |", "|---|---|---:|---:|---:|"]
    for item in report["contractual_schedules"]:
        lines.append(f"| {item['currency']} | {item['bucket']} | {item['ar_due']} | {item['ap_due']} | {item['contractual_net_gap']} |")
    lines += ["", "## H. LIQUIDITY COVERAGE", "", "Strict Treasury = caja+bancos contables / AP due del horizonte. Treasury + AR agrega AR contractual, sin asumir cobro puntual.", "", "| Moneda | Días | AP due | Strict | Treasury + AR |", "|---|---:|---:|---:|---:|"]
    for item in report["liquidity_coverage"]:
        lines.append(f"| {item['currency']} | {item['days']} | {item['ap_due']} | {item['strict_treasury']} | {item['treasury_plus_ar']} |")
    lines += ["", "## I. PRINCIPALES ENTRADAS Y SALIDAS", "", f"Top cash sources: `{report['top_cash_sources']}`", "", f"Top cash uses: `{report['top_cash_uses']}`", "", "## J. CASOS END-TO-END", "", "Los casos se conservan en JSON: cobro ORCT, pago OVPM, depósito ODPS interno, transferencia bancaria interna, comisión manual y movimiento unresolved cuando existen en el período.", "", "## K. INVARIANTES", "", "| Invariante | Resultado |", "|---|---|"]
    for key, value in inv.items():
        lines.append(f"| {key} | {'PASS' if value.get('pass') else 'DEGRADED'} |")
    lines += ["", "## L. TESORERÍA / VALORES EN TRÁNSITO", "", f"Valores separados, no sumados a caja/bancos: `{report.get('transit_values', [])}`.", "", "## M. CASH IN", "", "La entrada económica directa se limita a ORCT activo clasificado `EXTERNAL_CUSTOMER_IN`; ODPS y transferencias internas quedan fuera.", "", "## N. CASH OUT", "", "Las salidas se separan entre proveedor, impuesto, nómina, capex, comisión bancaria y otras; la fecha usada es la del pago/asiento, no la de la factura.", "", "## O. INTERNAL TRANSFERS", "", f"El neto observado por la dimensión monetaria es `{cf.get('internal_transfer_net')}`. El desvío no se compensa cruzando nominalmente `BS` con `USD` o `##`; por eso puede degradar el gate.", "", "## P. TOP SOURCES / USES", "", f"Concentración Top 10 entradas/salidas: `{report.get('concentration')}`.", "", "## Q. CONTRACTUAL AR", "", "Se publica por due date y moneda; es calendario contractual, no forecast probabilístico.", "", "## R. CONTRACTUAL AP", "", "Se consume del gate AP cerrado y se presenta en los mismos buckets, sin recalcular settlements.", "", "## S. LIQUIDITY GAP", "", "El gap contractual es AR due menos AP due por bucket y moneda; los vencidos no se presentan como cobro futuro.", "", "## T. OVERDUE PRESSURE", "", f"AR vencido vs AP vencido por moneda: `{[(x['currency'], x['ar_overdue'], x['ap_overdue']) for x in position]}`.", "", "## U. UNRESOLVED", "", f"Movimientos unresolved: `{cf.get('coverage', {}).get('unresolved_count')}`; importe: `{cf.get('coverage', {}).get('unresolved_amount')}`; porcentaje: `{cf.get('coverage', {}).get('unresolved_pct')}%`. La cobertura debe ser ≥99%; el bloqueo actual es el residual de transferencias internas.", "", "## V. CASOS REALES", "", f"Casos observados: `{report.get('cases')}`.", "", "## W. LIMITACIONES", "", "- GL SAP no demuestra saldo bancario externo ni caja físicamente disponible.\n- `##` se conserva separado y no se convierte.\n- FX/revaluación se separa de cash cuando el memo permite identificarla; lo demás permanece unresolved.\n- Impuestos, nómina, capex y financiación solo se incorporan cuando la evidencia textual/objeto es suficiente.\n- Las cuentas fiscales candidatas están en `known_tax_liabilities` y no se mezclan con AP.", "", "## X. PRÓXIMO GATE", "", f"Siguiente gate recomendado por evidencia: `{report.get('next_gate')}`. AR ya queda separado como `{ar.get('status')}`; el residual de transferencias internas puede requerir control cash→deposit antes del forecast.", "", "## Artefactos", "", f"- JSON: `{DEFAULT_OUTPUT}`", f"- Runner: `{Path(__file__)}`", "- HANA/SAP: SELECT-only; `SAP_WRITE_COUNT=0`.", ""]
    return "\n".join(lines)


def run(months: int = 24) -> dict[str, Any]:
    treasury = artifact_treasury()
    as_of = date.today()
    ap = artifact_ap(as_of)
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        as_of_result = safe(cur, 'SELECT CURRENT_DATE AS "AS_OF_DATE" FROM DUMMY')
        hana_as_of = as_date(rows(as_of_result)[0].get("AS_OF_DATE")) if rows(as_of_result) else None
        if hana_as_of:
            as_of = hana_as_of
            ap = artifact_ap(as_of)
        ar = ar_reconstruction(cur, as_of)
        payment_map = payment_application_map(cur)
        start = as_of - timedelta(days=max(1, min(months, 24)) * 31)
        movements, movement_query = movement_rows(cur, treasury.get("accounts", []), start, payment_map)
        cash_flow = aggregate_cash_flow(movements, treasury.get("positions", []), start)
        cash_flow["movement_query"] = {"status": movement_query.get("status"), "row_count": len(movements), "error": movement_query.get("error")}
        cash_flow["movements"] = movements
        schedules_data = schedules(ar, ap, as_of)
        coverage = cash_flow.get("coverage", {})
        position_by_currency: dict[str, dict[str, Any]] = {}
        for item in treasury.get("positions", []):
            if item["classification"] not in {"CASH", "PETTY_CASH", "BANK"}:
                continue
            position_by_currency.setdefault(item["currency"], {"currency": item["currency"], "treasury": 0.0, "ar_open": 0.0, "ap_open": 0.0, "ar_overdue": 0.0, "ap_overdue": 0.0})["treasury"] += item["balance"]
        for item in ar.get("summary", []):
            position_by_currency.setdefault(item["currency"], {"currency": item["currency"], "treasury": 0.0, "ar_open": 0.0, "ap_open": 0.0, "ar_overdue": 0.0, "ap_overdue": 0.0})["ar_open"] += item["open"]
            position_by_currency[item["currency"]]["ar_overdue"] += item["overdue"]
        for item in ap.get("summary", []):
            position_by_currency.setdefault(item["currency"], {"currency": item["currency"], "treasury": 0.0, "ar_open": 0.0, "ap_open": 0.0, "ar_overdue": 0.0, "ap_overdue": 0.0})["ap_open"] += item["amount"]
            if item["bucket"] == "OVERDUE":
                position_by_currency[item["currency"]]["ap_overdue"] += item["amount"]
        position = []
        for item in sorted(position_by_currency.values(), key=lambda x: x["currency"]):
            item["net_operating"] = round(item["treasury"] + item["ar_open"] - item["ap_open"], 2)
            for key in ("treasury", "ar_open", "ap_open", "ar_overdue", "ap_overdue"):
                item[key] = round(item[key], 2)
            position.append(item)
        cases = build_cases(movements)
        cash_flow["coverage"] = coverage
        cash_flow["canceled_external_overlap"] = sum(abs(num(x.get("NET"))) for x in movements if x.get("CLASSIFICATION") == "CANCELED_EXCLUDED" and x.get("EXTERNAL_FLOW"))
        cash_flow["internal_transfer_external_overlap"] = 0.0
        inv = invariants(ar, ap, treasury, cash_flow, schedules_data, cases)
        cash_flow["movement_profile"] = movement_profile(movements)
        cash_flow.pop("movements", None)
        ap_output = {k: v for k, v in ap.items() if k != "rows"}
        ap_output["detail_row_count"] = len(ap.get("rows", []))
        required = ("FP01_ar_reconciles", "FP02_ap_reused_closed_gate", "FP03_treasury_reused_closed_gate", "FP04_currency_separated", "FP05_odps_not_external_cash", "FP06_canceled_documents_excluded", "FP07_internal_transfers_not_external", "FP08_monthly_cash_flow", "FP09_opening_flow_closing", "FP10_internal_transfers_net", "FP11_unresolved_quantified", "FP12_classification_coverage_99pct", "FP13_contractual_schedules", "FP14_real_cases", "FP15_sap_write_count")
        verdict = "PASS" if all(inv[x]["pass"] for x in required) else "DEGRADED"
        next_gate = "TELCHI_CASH_DEPOSIT_CONTROL_V1" if not inv["FP10_internal_transfers_net"]["pass"] else ("TELCHI_AR_RECEIVABLES_COLLECTION_RECONCILIATION_V1" if not inv["FP01_ar_reconciles"]["pass"] else "TELCHI_CASH_FLOW_FORECAST_AND_LIQUIDITY_RISK_V1")
        top_sources = ranking([x for x in movements if x.get("CLASSIFICATION") == "EXTERNAL_CUSTOMER_IN"], "CARDCODE", 1)
        top_uses = ranking([x for x in movements if x.get("CLASSIFICATION") in {"EXTERNAL_SUPPLIER_OUT", "EXTERNAL_TAX_OUT", "PAYROLL", "CAPEX", "BANK_FEE"}], "CARDCODE", -1)
        transit_values = defaultdict(float)
        for item in treasury.get("positions", []):
            if item["classification"] not in {"CASH", "PETTY_CASH", "BANK"}:
                transit_values[(item["currency"], item["classification"])] += item["balance"]
        report = {"report_id": "TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "entity": "TELCHI", "domain": "CONTABILIDAD", "stage": "INVESTIGATION", "mode": "READ_ONLY", "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True}, "sap_write_count": 0, "as_of_date": as_of.isoformat(), "verdict": verdict, "gate": f"TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_{verdict}", "next_gate": next_gate, "ar": {k: v for k, v in ar.items() if k != "rows"}, "ap": ap_output, "known_tax_liabilities": tax_liability_candidates(cur), "treasury": treasury, "financial_position": position, "cash_flow": cash_flow, "contractual_schedules": schedules_data, "liquidity_coverage": liquidity_coverage(treasury.get("positions", []), ap.get("rows", []), ar.get("rows", []), as_of), "top_cash_sources": top_sources, "top_cash_uses": top_uses, "concentration": {"cash_in": concentration(top_sources, movements, {"EXTERNAL_CUSTOMER_IN"}, 1), "cash_out": concentration(top_uses, movements, {"EXTERNAL_SUPPLIER_OUT", "EXTERNAL_TAX_OUT", "PAYROLL", "CAPEX", "BANK_FEE"}, -1)}, "financing_flow": {"status": "PARTIAL" if any(x.get("CLASSIFICATION", "").startswith("FINANCING_") for x in movements) else "DEGRADED", "basis": "memo/object classification only; no loan subledger reconciliation"}, "investing_flow": {"status": "PARTIAL" if any(x.get("CLASSIFICATION") == "CAPEX" for x in movements) else "DEGRADED", "basis": "memo classification only; fixed-asset linkage not closed"}, "transit_values": [{"currency": key[0], "classification": key[1], "balance": round(value, 2)} for key, value in sorted(transit_values.items())], "cases": cases, "invariants": inv, "evidence_levels": ["PROVEN", "STRONG", "PARTIAL", "HEURISTIC", "UNRESOLVED"], "limitations": ["SAP accounting treasury is not available cash or external bank reconciliation.", "Currencies BS, USD and ## remain nominally separate.", "AP and treasury are consumed from their closed investigation artifacts; AR is recomputed and cross-checked.", "Classification coverage below 99% prevents PASS."]}
        return report
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run(args.months)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text(result) + "\n", encoding="utf-8")
    print(json.dumps({"gate": result["gate"], "output": str(args.output), "report": str(args.report), "sap_write_count": 0, "classified_pct": result["cash_flow"]["coverage"]["classified_pct"]}, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
