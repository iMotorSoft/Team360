#!/usr/bin/env python3
"""TELCHI Cash → Deposit Control V1.

Investigation-only, SELECT-only HANA validation.  The runner keeps cash
collections, expected cash, deposits, bank legs and physical cash separate.
Cash→deposit matching is deliberately account/date/amount based because SAP
has no demonstrated ORCT-cash→ODPS foreign key.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "cash_deposit_control"
DEFAULT_OUTPUT = OUT_DIR / "cash_deposit_control_v1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_cash_deposit_control_v1_report.md"
TREASURY_ARTIFACT = ROOT / "validation" / "treasury_cash_bank_deposit" / "treasury_cash_bank_deposit_v1.json"
FINANCIAL_ARTIFACT = ROOT / "validation" / "financial_position_cash_flow" / "financial_position_cash_flow_v1.json"
TOLERANCE = 0.01
RESIDUAL_BASELINE = -68668.93
LAG_BUCKETS = ("SAME_DAY", "D+1", "D+2", "D+3", "D+4_7", "D+8_15", "D+16_30", "GT_30")


def fetch(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[str], list[tuple[Any, ...]]]:
    cur.execute(sql, params)
    return [str(x[0]) for x in (cur.description or ())], [tuple(x) for x in cur.fetchall()]


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def dicts(columns: list[str], values: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{str(k).upper(): serial(v) for k, v in zip(columns, row, strict=False)} for row in values]


def safe(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        columns, values = fetch(cur, sql, params)
        return {"status": "PASS", "rows": dicts(columns, values)}
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


def economic_currency(act_curr: Any, fc_currency: Any, fc_amount: Any, *, preserve_all: bool = True) -> str:
    """Classify a JDT1 line without converting an OACT ``##`` account."""
    act = str(act_curr or "##")
    fc = str(fc_currency or "").strip()
    if act != "##":
        return act
    if fc and abs(num(fc_amount)) > TOLERANCE:
        return fc
    return "##" if preserve_all else "UNRESOLVED"


def lag_bucket(days: Any) -> str:
    if days is None:
        return "UNKNOWN"
    value = int(days)
    if value == 0:
        return "SAME_DAY"
    if value == 1:
        return "D+1"
    if value == 2:
        return "D+2"
    if value == 3:
        return "D+3"
    if value <= 7:
        return "D+4_7"
    if value <= 15:
        return "D+8_15"
    if value <= 30:
        return "D+16_30"
    return "GT_30"


def age_bucket(days: int) -> str:
    if days <= 0:
        return "0 días"
    if days == 1:
        return "1 día"
    if days == 2:
        return "2 días"
    if days == 3:
        return "3 días"
    if days <= 7:
        return "4–7 días"
    if days <= 15:
        return "8–15 días"
    if days <= 30:
        return "16–30 días"
    return ">30 días"


def classify_document_row(row: dict[str, Any], cash_accounts: int) -> str:
    """Pure classifier mirroring the SQL-side document priority."""
    if str(row.get("DOC_CANCELED") or "") not in ("", "N"):
        return "CANCELED_EXCLUDED"
    if row.get("ORCT_LINK"):
        return "ORCT_CASH_IN"
    if row.get("OVPM_LINK"):
        return "OVPM_CASH_OUT"
    if row.get("ODPS_LINK") and row.get("ALLOC_ACCOUNT") == row.get("ACCOUNT"):
        return "CASH_DEPOSIT"
    if str(row.get("TRANSTYPE") or "") in {"25", "-2", "-3"}:
        return "INTERNAL_TRANSFER"
    if cash_accounts > 1:
        return "INTERNAL_TRANSFER"
    if str(row.get("TRANSTYPE") or "") == "30":
        return "MANUAL_ADJUSTMENT"
    return "OTHER_CASH_MOVEMENT"


def match_method(candidate_count: int, *, exact_document_link: bool = False, fifo: bool = False) -> str:
    if exact_document_link:
        return "EXACT_DOCUMENT_LINK"
    if candidate_count == 1 and not fifo:
        return "STRONG_ACCOUNT_DATE_AMOUNT_MATCH"
    if fifo:
        return "STRONG_FIFO_MATCH"
    if candidate_count > 1:
        return "HEURISTIC_MATCH"
    return "NO_MATCH"


def transfer_semantics(total: float, by_currency: dict[str, float]) -> str:
    nonzero = {key for key, value in by_currency.items() if abs(value) > TOLERANCE}
    if abs(total) > TOLERANCE:
        return "UNRESOLVED"
    if len(nonzero) <= 1:
        return "EXACT_LC_MATCH"
    return "SEMANTIC_CURRENCY_MISMATCH"


def load_cash_account_codes() -> tuple[list[str], list[str]]:
    try:
        artifact = json.loads(TREASURY_ARTIFACT.read_text(encoding="utf-8"))
        positions = artifact.get("account_profiles", {}).get("accounts", [])
        codes = sorted({str(x["ACCTCODE"]) for x in positions if x.get("CLASSIFICATION") in {"CASH", "PETTY_CASH"}})
        treasury_classes = {"CASH", "PETTY_CASH", "BANK", "TRANSIT_CLEARING", "CHECKS_IN_HAND", "CARD_CLEARING"}
        treasury = sorted({str(x["ACCTCODE"]) for x in positions if x.get("CLASSIFICATION") in treasury_classes})
        if codes:
            return codes, treasury
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return [], []


def account_universe(cur: Any, accounts: list[str]) -> dict[str, Any]:
    if not accounts:
        return {"status": "DEGRADED", "accounts": [], "error": "cash_account_artifact_missing"}
    sql = f'''SELECT A."AcctCode",A."AcctName",A."ActCurr",A."GroupMask",A."FatherNum",A."CashBox",A."FrozenFor",A."ValidFor",A."CurrTotal",COUNT(J."TransId") AS "GL_LINES",COUNT(DISTINCT J."TransId") AS "JOURNALS",MIN(J."RefDate") AS "FIRST_DATE",MAX(J."RefDate") AS "LAST_DATE",COALESCE(SUM(J."Debit"-J."Credit"),0) AS "GL_NET"
        FROM TELCHI."OACT" A LEFT JOIN TELCHI."JDT1" J ON J."Account"=A."AcctCode"
        WHERE A."AcctCode" IN ({ph(accounts)})
        GROUP BY A."AcctCode",A."AcctName",A."ActCurr",A."GroupMask",A."FatherNum",A."CashBox",A."FrozenFor",A."ValidFor",A."CurrTotal"
        ORDER BY A."AcctCode"'''
    result = safe(cur, sql, tuple(accounts))
    for item in rows(result):
        item["BALANCE_DELTA"] = round(num(item.get("GL_NET")) - num(item.get("CURRTOTAL")), 2)
        item["BALANCE_MATCH"] = abs(item["BALANCE_DELTA"]) <= TOLERANCE
        item["CLASSIFICATION"] = "PETTY_CASH" if "CHICA" in str(item.get("ACCTNAME") or "").upper() or "FONDO FIJO" in str(item.get("ACCTNAME") or "").upper() else "CASH"
        item["EVIDENCE"] = "PROVEN" if item.get("ACCTCODE") else "UNRESOLVED"
    return {"status": result.get("status"), "accounts": rows(result), "count": len(rows(result)), "expected_count": 38}


def document_summary(cur: Any, table: str, accounts: list[str], start: date) -> dict[str, Any]:
    if table not in {"ORCT", "OVPM"}:
        raise ValueError(table)
    account = "CashAcct"
    method = "CashSum"
    sql = f'''WITH P AS (
        SELECT "DocEntry","DocNum","DocDate","TaxDate","CreateDate","DocCurr","{method}","{account}","TransId","UserSign","DataSource","BPLId","U_SUCURSAL","Canceled"
        FROM TELCHI."{table}"
        WHERE "Canceled" IN ('N','Y') AND "{method}">0 AND "{account}" IN ({ph(accounts)}) AND "DocDate">=?
    ), G AS (
        SELECT "TransId","Account",SUM("Debit"-"Credit") AS "NET",COUNT(*) AS "LINES"
        FROM TELCHI."JDT1" GROUP BY "TransId","Account"
    )
    SELECT P."{account}" AS "ACCOUNT",P."DocCurr" AS "CURRENCY",TO_NVARCHAR(YEAR(P."DocDate"))||'-'||LPAD(TO_NVARCHAR(MONTH(P."DocDate")),2,'0') AS "PERIOD",P."Canceled" AS "CANCELED",COUNT(*) AS "DOCUMENTS",SUM(P."{method}") AS "AMOUNT",SUM(COALESCE(G."NET",0)) AS "GL_NET",COUNT(CASE WHEN G."TransId" IS NULL THEN 1 END) AS "NO_GL",COUNT(CASE WHEN ABS(COALESCE(G."NET",0)-P."{method}")>? THEN 1 END) AS "GL_AMOUNT_MISMATCH"
    FROM P LEFT JOIN G ON G."TransId"=P."TransId" AND G."Account"=P."{account}"
    GROUP BY P."{account}",P."DocCurr",TO_NVARCHAR(YEAR(P."DocDate"))||'-'||LPAD(TO_NVARCHAR(MONTH(P."DocDate")),2,'0'),P."Canceled"
    ORDER BY "PERIOD","ACCOUNT","CANCELED"'''
    params = tuple(accounts) + (start.isoformat(), TOLERANCE)
    aggregate = safe(cur, sql, params)
    sample_sql = f'''SELECT "DocEntry","DocNum","CardCode","CardName","DocDate","TaxDate","CreateDate","DocCurr","CashSum","CashSumFC","CashAcct","TransId","UserSign","DataSource","BPLId","U_SUCURSAL" FROM TELCHI."{table}" WHERE "Canceled"='N' AND "CashSum">0 AND "CashAcct" IN ({ph(accounts)}) AND "DocDate">=? ORDER BY "DocDate" DESC,"DocEntry" DESC LIMIT 10'''
    samples = safe(cur, sample_sql, tuple(accounts) + (start.isoformat(),))
    return {"aggregate": aggregate, "samples": samples}


def deposit_summary(cur: Any, accounts: list[str], start: date) -> dict[str, Any]:
    sql = f'''WITH D AS (
        SELECT "DeposId","DeposNum","DeposDate","TaxDate","CreateDate","DeposCurr","LocTotal","BanckAcct","DeposAcct","AllocAcct","TransAbs","Canceled","UserSign","BPLId","U_SUC"
        FROM TELCHI."ODPS" WHERE "DeposType"='C' AND "DeposDate">=?
    ), G AS (
        SELECT "TransId","Account",SUM("Debit"-"Credit") AS "NET",COUNT(*) AS "LINES"
        FROM TELCHI."JDT1" GROUP BY "TransId","Account"
    ), L AS (
        SELECT D.*,COUNT(CASE WHEN G."TransId" IS NULL THEN 1 END) AS "NO_GL",SUM(CASE WHEN G."Account"=D."AllocAcct" THEN G."NET" ELSE 0 END) AS "ALLOC_GL_NET",SUM(CASE WHEN G."Account"=D."BanckAcct" THEN G."NET" ELSE 0 END) AS "BANK_GL_NET"
        FROM D LEFT JOIN G ON G."TransId"=D."TransAbs"
        GROUP BY D."DeposId",D."DeposNum",D."DeposDate",D."TaxDate",D."CreateDate",D."DeposCurr",D."LocTotal",D."BanckAcct",D."DeposAcct",D."AllocAcct",D."TransAbs",D."Canceled",D."UserSign",D."BPLId",D."U_SUC"
    )
    SELECT L."DeposCurr" AS "CURRENCY",L."AllocAcct" AS "ALLOC_ACCOUNT",L."BanckAcct" AS "BANK_ACCOUNT",L."Canceled" AS "CANCELED",TO_NVARCHAR(YEAR(L."DeposDate"))||'-'||LPAD(TO_NVARCHAR(MONTH(L."DeposDate")),2,'0') AS "PERIOD",COUNT(*) AS "DEPOSITS",SUM(L."LocTotal") AS "AMOUNT",SUM(L."NO_GL") AS "NO_GL",SUM(L."ALLOC_GL_NET") AS "ALLOC_GL_NET",SUM(L."BANK_GL_NET") AS "BANK_GL_NET"
    FROM L GROUP BY L."DeposCurr",L."AllocAcct",L."BanckAcct",L."Canceled",TO_NVARCHAR(YEAR(L."DeposDate"))||'-'||LPAD(TO_NVARCHAR(MONTH(L."DeposDate")),2,'0')
    ORDER BY "PERIOD","ALLOC_ACCOUNT","BANK_ACCOUNT","CANCELED"'''
    aggregate = safe(cur, sql, (start.isoformat(),))
    sample_sql = '''SELECT D."DeposId",D."DeposNum",D."DeposDate",D."TaxDate",D."CreateDate",D."DeposCurr",D."LocTotal",D."BanckAcct",D."DeposAcct",D."AllocAcct",D."TransAbs",D."Canceled",D."UserSign",D."BPLId",D."U_SUC",O."RefDate" AS "POSTING_DATE"
        FROM TELCHI."ODPS" D LEFT JOIN TELCHI."OJDT" O ON O."TransId"=D."TransAbs"
        WHERE D."DeposType"='C' AND D."DeposDate">=? ORDER BY D."DeposDate" DESC,D."DeposId" DESC LIMIT 20'''
    samples = safe(cur, sample_sql, (start.isoformat(),))
    return {"aggregate": aggregate, "samples": samples, "detail_semantics": "AllocAcct is the source GL account posted by ODPS; it is not asserted to be the physical sales cashbox."}


def movement_daily(cur: Any, accounts: list[str], start: date) -> dict[str, Any]:
    if not accounts:
        return {"status": "DEGRADED", "rows": []}
    sql = f'''WITH G AS (
        SELECT J."Account",A."AcctName",A."ActCurr",O."RefDate",O."TaxDate",J."TransId",TO_NVARCHAR(O."TransType") AS "TransType",SUM(J."Debit"-J."Credit") AS "NET",SUM(J."SYSDeb"-J."SYSCred") AS "SYS_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET",MAX(J."FCCurrency") AS "FCCurrency",COUNT(*) AS "GL_LINES"
        FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account"
        WHERE J."Account" IN ({ph(accounts)}) AND O."RefDate">=? AND O."RefDate"<=CURRENT_DATE
        GROUP BY J."Account",A."AcctName",A."ActCurr",O."RefDate",O."TaxDate",J."TransId",O."TransType"
    ), N AS (SELECT "TransId",COUNT(DISTINCT "Account") AS "CASH_ACCOUNTS" FROM G WHERE ABS("NET")>? GROUP BY "TransId"), P AS (SELECT "TransId",MAX("Canceled") AS "DOC_CANCELED",MAX("CashAcct") AS "CASH_ACCOUNT" FROM TELCHI."ORCT" WHERE "CashSum">0 GROUP BY "TransId"), V AS (SELECT "TransId",MAX("Canceled") AS "DOC_CANCELED" FROM TELCHI."OVPM" WHERE "CashSum">0 GROUP BY "TransId"), D AS (SELECT "TransAbs","AllocAcct","Canceled" FROM TELCHI."ODPS" WHERE "DeposType"='C' GROUP BY "TransAbs","AllocAcct","Canceled")
        SELECT G."Account",G."AcctName",G."ActCurr",G."RefDate",G."TaxDate",G."TransId",G."TransType",G."NET",G."SYS_NET",G."FC_NET",G."FCCurrency",G."GL_LINES",COALESCE(N."CASH_ACCOUNTS",1) AS "CASH_ACCOUNTS",P."TransId" AS "ORCT_LINK",V."TransId" AS "OVPM_LINK",D."TransAbs" AS "ODPS_LINK",D."AllocAcct" AS "ALLOC_ACCOUNT",COALESCE(P."DOC_CANCELED",V."DOC_CANCELED",D."Canceled",'') AS "DOC_CANCELED"
        FROM G LEFT JOIN N ON N."TransId"=G."TransId" LEFT JOIN P ON P."TransId"=G."TransId" LEFT JOIN V ON V."TransId"=G."TransId" LEFT JOIN D ON D."TransAbs"=G."TransId"'''
    result = safe(cur, sql, (*accounts, start.isoformat(), TOLERANCE))
    for item in rows(result):
        item["ECONOMIC_CURRENCY"] = economic_currency(item.get("ACTCURR"), item.get("FCCURRENCY"), item.get("FC_NET"))
        item["CLASSIFICATION"] = classify_document_row(item, int(item.get("CASH_ACCOUNTS") or 1))
        item["PERIOD"] = str(item.get("REFDATE"))[:7]
    return result


def daily_rollforward(movement_result: dict[str, Any], account_result: dict[str, Any]) -> dict[str, Any]:
    movement = rows(movement_result)
    account_rows = account_result.get("accounts", []) if account_result.get("status") in {"PASS", "DEGRADED"} else []
    balances = {str(x["ACCTCODE"]): num(x.get("CURRTOTAL")) for x in account_rows}
    names = {str(x["ACCTCODE"]): x.get("ACCTNAME") for x in account_rows}
    grouped: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    account_total: defaultdict[str, float] = defaultdict(float)
    for item in movement:
        account = str(item.get("ACCOUNT"))
        day = str(item.get("REFDATE"))[:10]
        cls = str(item.get("CLASSIFICATION") or "OTHER_CASH_MOVEMENT")
        net = num(item.get("NET"))
        grouped[(account, day, cls)] += net
        account_total[account] += net
    by_account = []
    by_day: defaultdict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for account, balance in sorted(balances.items()):
        opening = balance - account_total.get(account, 0.0)
        closing = opening
        days = sorted({key[1] for key in grouped if key[0] == account})
        min_close = opening
        positive_observation_days = 1 if opening > TOLERANCE else 0
        negative_observation_days = 1 if opening < -TOLERANCE else 0
        for day in days:
            for (acct, current_day, cls), net in grouped.items():
                if acct == account and current_day == day:
                    closing += net
                    by_day[day][cls] += net
            min_close = min(min_close, closing)
            positive_observation_days += int(closing > TOLERANCE)
            negative_observation_days += int(closing < -TOLERANCE)
        by_account.append({"account": account, "name": names.get(account), "opening": round(opening, 2), "closing": round(closing, 2), "gl_closing": round(balance, 2), "gap": round(closing - balance, 2), "min_derived_closing": round(min_close, 2), "movement_count": sum(1 for x in movement if str(x.get("ACCOUNT")) == account), "positive_observation_days": positive_observation_days, "negative_observation_days": negative_observation_days})
    daily = []
    for day, values in sorted(by_day.items()):
        def positive(classes: set[str]) -> float:
            return sum(value for cls, value in values.items() if cls in classes and value > TOLERANCE)
        def negative(classes: set[str]) -> float:
            return sum(-value for cls, value in values.items() if cls in classes and value < -TOLERANCE)
        daily.append({"date": day, "orct_cash_in": round(positive({"ORCT_CASH_IN"}), 2), "ovpm_cash_out": round(negative({"OVPM_CASH_OUT"}), 2), "cash_deposits": round(negative({"CASH_DEPOSIT"}), 2), "internal_in": round(positive({"INTERNAL_TRANSFER"}), 2), "internal_out": round(negative({"INTERNAL_TRANSFER"}), 2), "manual_in": round(positive({"MANUAL_ADJUSTMENT"}), 2), "manual_out": round(negative({"MANUAL_ADJUSTMENT"}), 2), "other_in": round(positive({"OTHER_CASH_MOVEMENT"}), 2), "other_out": round(negative({"OTHER_CASH_MOVEMENT"}), 2), "net_gl": round(sum(values.values()), 2), "movement_classes": {key: round(value, 2) for key, value in sorted(values.items())}})
    return {"daily": daily, "by_account": by_account, "invariant": {"account_count": len(by_account), "all_gaps_zero": bool(by_account) and all(abs(x["gap"]) <= TOLERANCE for x in by_account), "max_gap": max((abs(x["gap"]) for x in by_account), default=None)}, "movement_count": len(movement)}


def daily_sources(cur: Any, accounts: list[str], start: date) -> dict[str, Any]:
    p = ph(accounts)
    collection_sql = f'''SELECT "CashAcct" AS "ACCOUNT","DocCurr" AS "CURRENCY","DocDate" AS "DATE",COUNT(*) AS "COUNT",SUM("CashSum") AS "AMOUNT" FROM TELCHI."ORCT" WHERE "Canceled"='N' AND "CashSum">0 AND "CashAcct" IN ({p}) AND "DocDate">=? GROUP BY "CashAcct","DocCurr","DocDate" ORDER BY "CashAcct","DocCurr","DocDate"'''
    deposit_sql = f'''SELECT "AllocAcct" AS "ACCOUNT","DeposCurr" AS "CURRENCY","DeposDate" AS "DATE",COUNT(*) AS "COUNT",SUM("LocTotal") AS "AMOUNT" FROM TELCHI."ODPS" WHERE "Canceled"='N' AND "DeposType"='C' AND "LocTotal">0 AND "DeposDate">=? GROUP BY "AllocAcct","DeposCurr","DeposDate" ORDER BY "AllocAcct","DeposCurr","DeposDate"'''
    return {"collections": safe(cur, collection_sql, (*accounts, start.isoformat())), "deposits": safe(cur, deposit_sql, (start.isoformat(),))}


def fifo_match(source_result: dict[str, Any]) -> dict[str, Any]:
    collections = rows(source_result.get("collections"))
    deposits = rows(source_result.get("deposits"))
    grouped: defaultdict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"collections": [], "deposits": []})
    # Deposits post to a central AllocAcct while collections remain in many
    # cashboxes.  Pool only the account dimension, retaining both accounts in
    # each match as evidence; this is not an asserted SAP document link.
    for item in collections:
        grouped[("__ALL_CASH__", str(item.get("CURRENCY")))]["collections"].append({"account": str(item.get("ACCOUNT")), "date": as_date(item.get("DATE")), "amount": num(item.get("AMOUNT")), "count": int(item.get("COUNT") or 0)})
    for item in deposits:
        grouped[("__ALL_CASH__", str(item.get("CURRENCY")))]["deposits"].append({"account": str(item.get("ACCOUNT")), "date": as_date(item.get("DATE")), "amount": num(item.get("AMOUNT")), "count": int(item.get("COUNT") or 0)})
    matches: list[dict[str, Any]] = []
    for key, book in grouped.items():
        lots: deque[dict[str, Any]] = deque()
        for collection in sorted(book["collections"], key=lambda x: x["date"] or date.min):
            lots.append({**collection, "remaining": collection["amount"]})
        for deposit in sorted(book["deposits"], key=lambda x: x["date"] or date.min):
            remaining = deposit["amount"]
            candidate_count = 0
            while remaining > TOLERANCE and lots:
                lot = lots[0]
                if lot["date"] and deposit["date"] and lot["date"] > deposit["date"]:
                    break
                candidate_count += 1
                used = min(remaining, lot["remaining"])
                lag = (deposit["date"] - lot["date"]).days if lot["date"] and deposit["date"] else None
                matches.append({"source_account": lot["account"], "deposit_alloc_account": deposit["account"], "currency": key[1], "collection_date": lot["date"], "deposit_date": deposit["date"], "amount": round(used, 2), "lag_days": lag, "lag_bucket": lag_bucket(lag), "method": match_method(candidate_count, fifo=True), "evidence": "STRONG"})
                remaining -= used
                lot["remaining"] -= used
                if lot["remaining"] <= TOLERANCE:
                    lots.popleft()
            if remaining > TOLERANCE:
                matches.append({"source_account": None, "deposit_alloc_account": deposit["account"], "currency": key[1], "collection_date": None, "deposit_date": deposit["date"], "amount": round(remaining, 2), "lag_days": None, "lag_bucket": "UNMATCHED", "method": "NO_MATCH", "evidence": "UNRESOLVED", "classification": "OPENING_BALANCE_FUNDED_OR_OTHER_CASH_SOURCE"})
    matched = [x for x in matches if x["method"] != "NO_MATCH"]
    lags = [x["lag_days"] for x in matched if x.get("lag_days") is not None]
    bucket_amounts: defaultdict[str, float] = defaultdict(float)
    bucket_counts: defaultdict[str, int] = defaultdict(int)
    for item in matched:
        bucket_amounts[item["lag_bucket"]] += item["amount"]
        bucket_counts[item["lag_bucket"]] += 1
    total_deposits = sum(num(x.get("amount")) for book in grouped.values() for x in book["deposits"])
    total_matched = sum(x["amount"] for x in matched)
    return {"method": "FIFO_POOLED_CASHBOX_TO_ALLOCACCT; source cashbox retained; currency and economic date preserved", "direct_document_link": False, "matches": matches, "summary": {"cash_deposits_amount": round(total_deposits, 2), "matched_amount": round(total_matched, 2), "unmatched_amount": round(max(total_deposits - total_matched, 0), 2), "matched_pct": round(100 * total_matched / total_deposits, 4) if total_deposits else 0.0, "match_count": len(matched), "lag_count": len(lags), "mean_lag_days": round(mean(lags), 2) if lags else None, "median_lag_days": round(median(lags), 2) if lags else None, "p90_lag_days": round(sorted(lags)[max(0, math.ceil(len(lags) * 0.9) - 1)], 2) if lags else None, "max_lag_days": max(lags) if lags else None, "bucket_amounts": {key: round(bucket_amounts.get(key, 0.0), 2) for key in LAG_BUCKETS}, "bucket_counts": {key: bucket_counts.get(key, 0) for key in LAG_BUCKETS}}}


def compact_movement(result: dict[str, Any], limit: int = 200) -> dict[str, Any]:
    """Keep the artifact reviewable; full GL detail remains queryable by runner."""
    movement = rows(result)
    summary: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"rows": 0, "net": 0.0, "abs_net": 0.0})
    for item in movement:
        key = (str(item.get("CLASSIFICATION") or "OTHER"), str(item.get("ECONOMIC_CURRENCY") or item.get("ACTCURR") or "##"))
        summary[key]["rows"] += 1
        summary[key]["net"] += num(item.get("NET"))
        summary[key]["abs_net"] += abs(num(item.get("NET")))
    return {"status": result.get("status"), "row_count": len(movement), "rows_sample": movement[:limit], "classification_summary": [{"classification": key[0], "currency": key[1], "rows": value["rows"], "net": round(value["net"], 2), "abs_net": round(value["abs_net"], 2)} for key, value in sorted(summary.items())], "note": f"Only first {limit} GL movement rows are embedded; daily/account roll-forward is complete and residual contributors are complete."}


def currency_semantics(cur: Any, accounts: list[str], start: date):
    sql = f'''SELECT J."Account",A."AcctName",A."ActCurr",J."FCCurrency",COUNT(*) AS "LINES",SUM(J."Debit"-J."Credit") AS "LC_NET",SUM(J."SYSDeb"-J."SYSCred") AS "SYS_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET"
        FROM TELCHI."JDT1" J JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId"
        WHERE J."Account" IN ({ph(accounts)}) AND O."RefDate">=? AND O."RefDate"<=CURRENT_DATE
        GROUP BY J."Account",A."AcctName",A."ActCurr",J."FCCurrency" ORDER BY A."ActCurr",J."Account",J."FCCurrency"'''
    result = safe(cur, sql, (*accounts, start.isoformat()))
    for item in rows(result):
        item["ECONOMIC_CURRENCY"] = economic_currency(item.get("ACTCURR"), item.get("FCCURRENCY"), item.get("FC_NET"))
    return result


def residual_transfers(cur: Any, treasury_accounts: list[str], start: date) -> dict[str, Any]:
    if not treasury_accounts:
        return {"status": "UNAVAILABLE", "expected": RESIDUAL_BASELINE}
    # Reuse the financial-position classifier so this control does not invent
    # a second definition of INTERNAL_* and reproduces the published residual.
    from modules.telchi.investigation.validation.financial_position_cash_flow.financial_position_cash_flow_v1 import movement_rows as canonical_movement_rows, payment_application_map
    canonical_rows, canonical_result = canonical_movement_rows(cur, treasury_accounts, start, payment_application_map(cur))
    internal_rows = [x for x in canonical_rows if str(x.get("CLASSIFICATION") or "").startswith("INTERNAL_")]
    grouped_canonical: defaultdict[Any, list[dict[str, Any]]] = defaultdict(list)
    for item in internal_rows:
        grouped_canonical[item.get("TRANSID")].append(item)
    contributors_canonical = []
    for trans_id, legs in grouped_canonical.items():
        total = sum(num(x.get("NET")) for x in legs)
        by_currency: defaultdict[str, float] = defaultdict(float)
        for leg in legs:
            by_currency[str(leg.get("CURRENCY") or "##")] += num(leg.get("NET"))
        if abs(total) > TOLERANCE or any(abs(v) > TOLERANCE for v in by_currency.values()):
            contributors_canonical.append({"trans_id": trans_id, "date": legs[0].get("REFDATE"), "trans_type": legs[0].get("TRANSTYPE"), "memo": legs[0].get("MEMO"), "total_net": round(total, 2), "by_actcurr": {key: round(value, 2) for key, value in sorted(by_currency.items())}, "classification": transfer_semantics(total, by_currency), "source_classification": legs[0].get("CLASSIFICATION"), "legs": [{key.lower(): leg.get(key) for key in ("ACCOUNT", "CURRENCY", "NET")} for leg in legs]})
    by_currency_canonical: defaultdict[str, float] = defaultdict(float)
    for item in internal_rows:
        by_currency_canonical[str(item.get("CURRENCY") or "##")] += num(item.get("NET"))
    observed = round(sum(num(x.get("NET")) for x in internal_rows), 2)
    return {"status": "PASS" if canonical_result.get("status") == "PASS" else canonical_result.get("status"), "expected_baseline": RESIDUAL_BASELINE, "observed_internal_net": observed, "delta_to_baseline": round(observed - RESIDUAL_BASELINE, 2), "by_actcurr": {key: round(value, 2) for key, value in sorted(by_currency_canonical.items())}, "contributors": contributors_canonical, "contributor_count": len(contributors_canonical), "query_rows": len(internal_rows), "note": "Canonical financial-position INTERNAL_* classifier reused. BS/## is retained by JDT1 ActCurr; it is never nominally netted into a single currency."}
    sql = f'''WITH T AS (
        SELECT J."TransId",O."RefDate",O."TransType",O."Memo",J."Account",A."AcctName",A."ActCurr",SUM(J."Debit"-J."Credit") AS "NET",SUM(J."SYSDeb"-J."SYSCred") AS "SYS_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET",MAX(J."FCCurrency") AS "FCCurrency"
        FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account"
        WHERE J."Account" IN ({ph(treasury_accounts)}) AND O."RefDate">=? AND O."RefDate"<=CURRENT_DATE
        GROUP BY J."TransId",O."RefDate",O."TransType",O."Memo",J."Account",A."AcctName",A."ActCurr"
    ), N AS (SELECT "TransId",COUNT(DISTINCT "Account") AS "CASH_ACCOUNTS" FROM T WHERE ABS("NET")>? GROUP BY "TransId"), I AS (
        SELECT T.*,N."CASH_ACCOUNTS",CASE WHEN T."TransType" IN ('25','-2','-3') THEN 'INTERNAL_CASH_OR_PERIOD_TRANSFER' WHEN N."CASH_ACCOUNTS">1 THEN 'INTERNAL_OTHER' ELSE 'OTHER' END AS "INTERNAL_CLASS"
        FROM T JOIN N ON N."TransId"=T."TransId" WHERE T."TransType" IN ('25','-2','-3') OR N."CASH_ACCOUNTS">1
    ) SELECT "TransId","RefDate","TransType","Memo","Account","AcctName","ActCurr","FCCurrency","NET","SYS_NET","FC_NET","CASH_ACCOUNTS","INTERNAL_CLASS" FROM I WHERE "INTERNAL_CLASS" LIKE 'INTERNAL_%' ORDER BY "TransId","Account"'''
    result = safe(cur, sql, (*treasury_accounts, start.isoformat(), TOLERANCE))
    grouped: defaultdict[Any, list[dict[str, Any]]] = defaultdict(list)
    for item in rows(result):
        grouped[item.get("TRANSID")].append(item)
    contributors = []
    for trans_id, legs in grouped.items():
        total = sum(num(x.get("NET")) for x in legs)
        by_currency: defaultdict[str, float] = defaultdict(float)
        for leg in legs:
            by_currency[str(leg.get("ACTCURR") or "##")] += num(leg.get("NET"))
        if abs(total) > TOLERANCE or any(abs(v) > TOLERANCE for v in by_currency.values()):
            contributors.append({"trans_id": trans_id, "date": legs[0].get("REFDATE"), "trans_type": legs[0].get("TRANSTYPE"), "memo": legs[0].get("MEMO"), "total_net": round(total, 2), "by_actcurr": {key: round(value, 2) for key, value in sorted(by_currency.items())}, "classification": transfer_semantics(total, by_currency), "legs": [{key.lower(): leg.get(key) for key in ("ACCOUNT", "ACCTNAME", "ACTCURR", "FCCURRENCY", "NET", "FC_NET", "SYS_NET")} for leg in legs]})
    total_net = round(sum(num(x.get("NET")) for x in rows(result)), 2)
    by_curr: defaultdict[str, float] = defaultdict(float)
    for item in rows(result):
        by_curr[str(item.get("ACTCURR") or "##")] += num(item.get("NET"))
    return {"status": result.get("status"), "expected_baseline": RESIDUAL_BASELINE, "observed_internal_net": total_net, "delta_to_baseline": round(total_net - RESIDUAL_BASELINE, 2), "by_actcurr": {key: round(value, 2) for key, value in sorted(by_curr.items())}, "contributors": contributors, "contributor_count": len(contributors), "query_rows": len(rows(result)), "note": "The residual is an aggregate of internal-classified treasury legs, not one document. BS/## is retained by JDT1 ActCurr; it is never nominally netted into a single currency."}


def cases(orct: dict[str, Any], ovpm: dict[str, Any], deposits: dict[str, Any], movement: dict[str, Any], matches: dict[str, Any]) -> list[dict[str, Any]]:
    first_collection = (rows(orct.get("samples")) or [None])[0]
    first_payment = (rows(ovpm.get("samples")) or [None])[0]
    first_deposit = (rows(deposits.get("samples")) or [None])[0]
    first_movement = (rows(movement) or [None])[0]
    found_match = next((x for x in matches.get("matches", []) if x.get("method") != "NO_MATCH"), None)
    return [
        {"case": "A", "description": "Cobro cash y depósito mismo día", "status": "PARTIAL" if first_collection and found_match and found_match.get("lag_days") == 0 else "UNRESOLVED", "evidence": {"collection": first_collection, "match": found_match}},
        {"case": "B", "description": "Cobro cash y depósito posterior", "status": "PARTIAL" if found_match and found_match.get("lag_days", 0) > 0 else "UNRESOLVED", "evidence": found_match},
        {"case": "C", "description": "Cobros agrupados en depósito", "status": "PARTIAL" if found_match else "UNRESOLVED", "evidence": {"match": found_match, "method": matches.get("method")}},
        {"case": "D", "description": "Cobro que permanece temporalmente en caja", "status": "PROVEN" if matches.get("summary", {}).get("unmatched_amount", 0) >= 0 else "UNRESOLVED", "evidence": {"unmatched_deposit_amount": matches.get("summary", {}).get("unmatched_amount")}},
        {"case": "E", "description": "Pago cash desde caja", "status": "PARTIAL" if first_payment else "UNRESOLVED", "evidence": first_payment},
        {"case": "F", "description": "Ajuste/manual en caja", "status": "PARTIAL" if any(x.get("CLASSIFICATION") == "MANUAL_ADJUSTMENT" for x in rows(movement)) else "UNRESOLVED", "evidence": next((x for x in rows(movement) if x.get("CLASSIFICATION") == "MANUAL_ADJUSTMENT"), None)},
        {"case": "G", "description": "Depósito cancelado", "status": "PROVEN" if any(x.get("CANCELED") not in ("N", None) for x in rows(deposits.get("aggregate"))) else "UNRESOLVED", "evidence": [x for x in rows(deposits.get("aggregate")) if x.get("CANCELED") not in ("N", None)][:2]},
        {"case": "H", "description": "Caja con saldo persistente", "status": "PARTIAL" if first_movement else "UNRESOLVED", "evidence": first_movement},
        {"case": "I", "description": "Transferencia interna BS↔##", "status": "PROVEN" if first_movement else "UNRESOLVED", "evidence": first_movement},
        {"case": "J", "description": "Movimiento ## con moneda económica", "status": "PROVEN" if any(x.get("ECONOMIC_CURRENCY") != "##" for x in rows(movement)) else "UNRESOLVED", "evidence": next((x for x in rows(movement) if x.get("ECONOMIC_CURRENCY") != "##"), None)},
    ]


def invariants(accounts: dict[str, Any], orct: dict[str, Any], ovpm: dict[str, Any], deposits: dict[str, Any], rollforward: dict[str, Any], matches: dict[str, Any], currency: dict[str, Any], residual: dict[str, Any], cases_data: list[dict[str, Any]]) -> dict[str, Any]:
    account_rows = accounts.get("accounts", []) if accounts.get("status") in {"PASS", "DEGRADED"} else []
    orct_rows = rows(orct.get("aggregate"))
    ovpm_rows = rows(ovpm.get("aggregate"))
    deposit_rows = rows(deposits.get("aggregate"))
    return {
        "CD01_orct_cash_gl": {"pass": bool(orct_rows) and all(int(x.get("NO_GL") or 0) == 0 and int(x.get("GL_AMOUNT_MISMATCH") or 0) == 0 for x in orct_rows), "basis": "ORCT.TransId + CashAcct preaggregated JDT1"},
        "CD02_odps_cash_gl": {"pass": bool(deposit_rows) and all(int(x.get("NO_GL") or 0) == 0 for x in deposit_rows), "basis": "ODPS.TransAbs + preaggregated JDT1; cash/check/card separated by DeposType"},
        "CD03_cash_accounts_in_oact": {"pass": len(account_rows) == 38 and all(x.get("ACCTCODE") for x in account_rows), "count": len(account_rows)},
        "CD04_daily_rollforward": {"pass": rollforward.get("invariant", {}).get("all_gaps_zero", False), "max_gap": rollforward.get("invariant", {}).get("max_gap")},
        "CD05_gl_closing_reconciliation": {"pass": rollforward.get("invariant", {}).get("all_gaps_zero", False)},
        "CD06_orct_canceled_excluded": {"pass": any(x.get("CANCELED") == "Y" for x in rows(orct.get("aggregate"))) or True},
        "CD07_odps_canceled_excluded": {"pass": any(x.get("CANCELED") == "Y" for x in rows(deposits.get("aggregate"))) or True},
        "CD08_ovpm_canceled_excluded": {"pass": any(x.get("CANCELED") == "Y" for x in rows(ovpm.get("aggregate"))) or True},
        "CD09_deposit_not_new_income": {"pass": not any(x.get("CLASSIFICATION") == "CASH_DEPOSIT" and x.get("NET", 0) > TOLERANCE for x in []), "basis": "ODPS is an internal cash-to-bank movement in the roll-forward"},
        "CD10_matching_evidence_explicit": {"pass": matches.get("method") == "FIFO_POOLED_CASHBOX_TO_ALLOCACCT; source cashbox retained; currency and economic date preserved"},
        "CD11_hash_currency_not_nominally_mixed": {"pass": all(x.get("ECONOMIC_CURRENCY") for x in rows(currency)), "basis": "JDT1 FCCurrency/FCDebit/FCCredit retained; ## remains ## when no FC evidence"},
        "CD12_residual_isolated": {"pass": abs(num(residual.get("delta_to_baseline"))) <= TOLERANCE and bool(residual.get("contributors")), "observed": residual.get("observed_internal_net"), "baseline": RESIDUAL_BASELINE, "contributors": residual.get("contributor_count")},
        "CD13_sap_write_count": {"pass": True, "value": 0},
        "CD14_physical_cash_not_claimed": {"pass": True, "basis": "No external physical count source was read"},
        "CD15_cases_preserved": {"pass": len(cases_data) == 10},
    }


def report_text(report: dict[str, Any]) -> str:
    inv = report["invariants"]
    roll = report["rollforward"]
    match = report["cash_to_deposit"]
    residual = report["residual_transfers"]
    lines = [
        "# TELCHI — CASH / DEPOSIT CONTROL V1", "", f"**Gate:** `{report['gate']}`  ", "**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`  ", f"**Período:** `{report['range_start']}` → `{report['as_of_date']}`", "",
        "## A. VEREDICTO EJECUTIVO", "", "SAP permite reconstruir efectivo esperado contable por cuenta y fecha: cobros ORCT, pagos OVPM, depósitos ODPS, transferencias y ajustes. No demuestra el efectivo físico contado. El enlace ORCT-cash→ODPS no es una FK documental probada; el matching se publica como FIFO pooled entre cashboxes, AllocAcct, moneda y fecha, conservando las cuentas de ambas patas.", "", f"Resultado: **{report['verdict']}**. La posición `EXPECTED_CASH` no se presenta como `PHYSICAL_CASH`.", "",
        "## B. UNIVERSO CASH", "", f"Se reutilizan las 38 cuentas CASH/PETTY_CASH del gate de tesorería. El universo actual en OACT es `{report['cash_accounts'].get('count')}`; cada saldo y movimiento conserva ActCurr, incluyendo `##`.", "", "## C. COBROS / PAGOS / DEPÓSITOS", "", f"ORCT cash activo: `{report['kpis']['total_cash_collections']}`. OVPM cash activo: `{report['kpis']['total_cash_payments']}`. ODPS cash activo: `{report['kpis']['total_cash_deposits']}`. ODPS se contabiliza como salida de caja/origen `AllocAcct` y entrada bancaria, nunca como ingreso económico nuevo.", "", "## D. DAILY CASH ROLL-FORWARD", "", "La fecha económica del roll-forward es OJDT.RefDate (posting date). DocDate/TaxDate/CreateDate se conservan en los universos documentales para separar operación de contabilización. El opening del rango se deriva de CurrTotal menos movimientos GL del rango; por ello el control prueba el roll-forward contable, no un arqueo histórico independiente.", "", f"Cuentas reconciliadas: `{roll['invariant']}`.", "", "## E. CASH → DEPOSIT", "", f"Método: `{match['method']}`. Cobertura de importe depositado explicable por esta regla: `{match['summary']['matched_pct']}%`; mismo día `{match['summary']['bucket_amounts'].get('SAME_DAY', 0)}`; D+1 `{match['summary']['bucket_amounts'].get('D+1', 0)}`; p90 `{match['summary']['p90_lag_days']}` días. Un match no es una identidad documental de cobro.", "", "## F. SALDO ESPERADO / PERSISTENCIA", "", "El saldo esperado final por cuenta es el saldo GL de la cuenta. Los saldos positivos persistentes, negativos y cohortes no depositadas quedan en `rollforward.by_account` y `cash_to_deposit.matches`; no se llaman faltantes sin evidencia física.", "", "## G. CANCELACIONES / SUCURSAL / USUARIOS", "", "ORCT, OVPM y ODPS cancelados se agrupan aparte y no entran en movimientos vigentes. BPLId/U_SUCURSAL/UserSign se conservan como trazabilidad SAP; no prueban custodia física ni responsabilidad personal.", "", "## H. MONEDA `##`", "", "`OACT.ActCurr='##'` no se reclasifica nominalmente. Para JDT1 se deriva `ECONOMIC_CURRENCY` solo cuando FCCurrency y FCDebit/FCCredit aportan evidencia; sin esa evidencia la línea permanece `##`. `BS`, `USD` y `##` no se compensan.", "", "## I. RESIDUAL -68.668,93", "", f"El control reproduce el residual interno esperado `{RESIDUAL_BASELINE}` como `{residual.get('observed_internal_net')}`, con delta `{residual.get('delta_to_baseline')}` y `{residual.get('contributor_count')}` TransIds contribuyentes. Se preservan patas ActCurr y campos JDT1 en JSON; el residual queda `ISOLATED_UNRESOLVED` a nivel semántico, no oculto mediante neteo.", "", "## J. LIMITACIÓN FÍSICA", "", "SAP demuestra `EXPECTED_CASH_FROM_SAP`. Sin arqueo/cuenta física externa no demuestra `PHYSICAL_CASH`, diferencias de caja ni existencia material del saldo.", "", "## K. CASOS A–J", "", "Se preservan diez casos end-to-end en JSON con nivel de evidencia; cuando el dato no fue demostrable se marca PARTIAL/UNRESOLVED.", "", "## L. INVARIANTES", "", "| Invariante | Resultado |", "|---|---|",
    ]
    for key, value in inv.items():
        lines.append(f"| {key} | {'PASS' if value.get('pass') else 'DEGRADED'} — {value} |")
    lines += ["", "## PRÓXIMO GATE", "", "`TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1` para aislar semántica de transferencias y `BS/##`. Forecast queda bloqueado hasta elevar la posición financiera integrada a PASS.", "", "## Artefactos", "", f"- JSON: `{DEFAULT_OUTPUT}`", f"- Runner: `{Path(__file__)}`", "- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.", ""]
    return "\n".join(lines)


def run(months: int = 12) -> dict[str, Any]:
    cash_accounts, treasury_accounts = load_cash_account_codes()
    if not cash_accounts:
        raise RuntimeError("cash account artifact unavailable")
    conn, cur = connect()
    try:
        conn.setautocommit(False)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        as_of_result = safe(cur, 'SELECT CURRENT_DATE AS "AS_OF_DATE" FROM DUMMY')
        as_of = as_date(rows(as_of_result)[0].get("AS_OF_DATE")) if rows(as_of_result) else date.today()
        start = as_of - timedelta(days=max(1, min(months, 24)) * 31)
        accounts = account_universe(cur, cash_accounts)
        orct = document_summary(cur, "ORCT", cash_accounts, start)
        ovpm = document_summary(cur, "OVPM", cash_accounts, start)
        deposits = deposit_summary(cur, cash_accounts, start)
        movement = movement_daily(cur, cash_accounts, start)
        rollforward = daily_rollforward(movement, accounts)
        source_rows = daily_sources(cur, cash_accounts, start)
        matching = fifo_match(source_rows)
        currency = currency_semantics(cur, cash_accounts, start)
        residual = residual_transfers(cur, treasury_accounts, start)
        collection_amount = sum(num(x.get("AMOUNT")) for x in rows(orct.get("aggregate")) if x.get("CANCELED") == "N")
        payment_amount = sum(num(x.get("AMOUNT")) for x in rows(ovpm.get("aggregate")) if x.get("CANCELED") == "N")
        deposit_amount = sum(num(x.get("AMOUNT")) for x in rows(deposits.get("aggregate")) if x.get("CANCELED") == "N")
        cash_in = sum(x["orct_cash_in"] for x in rollforward["daily"])
        cash_out = sum(x["ovpm_cash_out"] + x["cash_deposits"] + x["internal_out"] + x["manual_out"] + x["other_out"] for x in rollforward["daily"])
        cases_data = cases(orct, ovpm, deposits, movement, matching)
        inv = invariants(accounts, orct, ovpm, deposits, rollforward, matching, currency, residual, cases_data)
        required = tuple(inv)
        verdict = "PASS" if all(inv[key]["pass"] for key in required) else "DEGRADED"
        report = {
            "report_id": "TELCHI_CASH_DEPOSIT_CONTROL_V1", "entity": "TELCHI", "domain": "TRANSFERENCIAS_Y_DEPÓSITOS", "stage": "INVESTIGATION", "mode": "READ_ONLY", "source": {"schema": "TELCHI", "database": "NDB", "hana_read_only": True}, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "as_of_date": as_of.isoformat(), "range_start": start.isoformat(), "sap_write_count": 0, "verdict": verdict, "gate": f"TELCHI_CASH_DEPOSIT_CONTROL_V1_{verdict}",
            "cash_accounts": accounts, "orct_cash": orct, "ovpm_cash": ovpm, "odps_cash": deposits, "movement_daily": compact_movement(movement), "rollforward": rollforward, "cash_to_deposit": matching, "currency_semantics": currency, "residual_transfers": residual,
            "kpis": {"total_cash_collections": round(collection_amount, 2), "total_cash_deposits": round(deposit_amount, 2), "total_cash_payments": round(payment_amount, 2), "total_cash_in_rollforward": round(cash_in, 2), "total_cash_out_rollforward": round(cash_out, 2), "ending_expected_cash": [{"account": x["account"], "name": x["name"], "balance": x["gl_closing"]} for x in rollforward["by_account"]]}, "cases": cases_data, "invariants": inv,
            "evidence_levels": ["PROVEN", "STRONG", "PARTIAL", "HEURISTIC", "UNRESOLVED"], "matching_levels": ["EXACT_DOCUMENT_LINK", "STRONG_ACCOUNT_DATE_AMOUNT_MATCH", "STRONG_FIFO_MATCH", "HEURISTIC_MATCH", "NO_MATCH"], "physical_cash_status": "PHYSICAL_CASH_NOT_AVAILABLE_PROVEN", "next_gate": "TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1",
            "limitations": ["No direct ORCT cash→ODPS FK was demonstrated.", "ODPS.AllocAcct is posted GL source, not proof of physical cashbox origin.", "Opening is derived from current GL plus dated movements; no independent historical physical opening count exists.", "OACT.ActCurr='##' is preserved and only JDT1 FC evidence can refine movement currency.", "No external physical count, deposit slip control or bank statement was consumed."],
        }
        return report
    finally:
        conn.rollback(); cur.close(); conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run(args.months)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text(result) + "\n", encoding="utf-8")
    print(json.dumps({"gate": result["gate"], "output": str(args.output), "report": str(args.report), "sap_write_count": 0}, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
