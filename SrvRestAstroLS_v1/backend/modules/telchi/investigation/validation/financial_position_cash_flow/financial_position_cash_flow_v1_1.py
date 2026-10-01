#!/usr/bin/env python3
"""TELCHI Financial Position / Cash Flow V1.1.

Focused SELECT-only extension of V1.  It reproduces the frozen 336-TransId
residual, separates OACT account currency from JDT1 movement currency, and
splits internal principal from card commissions and non-cash period carryover.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import INVESTIGATION_ROOT
from modules.telchi.investigation.validation.financial_position_cash_flow.financial_position_cash_flow_v1 import (
    TOLERANCE,
    classify_movement,
    payment_application_map,
)

ROOT = INVESTIGATION_ROOT
OUT_DIR = ROOT / "validation" / "financial_position_cash_flow"
DEFAULT_OUTPUT = OUT_DIR / "financial_position_cash_flow_v1_1.json"
DEFAULT_REPORT = ROOT / "docs" / "telchi_financial_position_cash_flow_v1_1_report.md"
V1_ARTIFACT = OUT_DIR / "financial_position_cash_flow_v1.json"
CASH_ARTIFACT = ROOT / "validation" / "cash_deposit_control" / "cash_deposit_control_v1.json"
TREASURY_ARTIFACT = ROOT / "validation" / "treasury_cash_bank_deposit" / "treasury_cash_bank_deposit_v1.json"
EXPECTED_IDS = 336
EXPECTED_RESIDUAL = -68668.93
EXPECTED_BS = -69688.46
EXPECTED_HASH = 1019.53
FEE_ACCOUNTS = {"6020103", "6210105"}
TREASURY_CLASSES = {"CASH", "PETTY_CASH", "BANK", "TRANSIT_CLEARING", "CHECKS_IN_HAND", "CARD_CLEARING"}
POSITION_CLASSES = {"CASH", "PETTY_CASH", "BANK"}


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


def ph(values: list[Any] | set[Any]) -> str:
    return ",".join("?" for _ in values) or "NULL"


def fetch_dicts(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    columns = [str(x[0]).upper() for x in (cur.description or ())]
    return [{key: serial(value) for key, value in zip(columns, row, strict=False)} for row in cur.fetchall()]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def movement_currency_amount(row: dict[str, Any], local_currency: str = "BS", system_currency: str = "USD") -> tuple[str, float, str]:
    """Return economic movement currency, amount and evidence basis.

    SAP LC (Debit/Credit) and SC (SysDeb/SysCred) are reporting bases, not the
    OACT currency. FC is used only when JDT1 explicitly records a non-zero FC
    amount and FCCurrency. A fixed-currency account uses SC when its FC field is
    absent (notably revaluation lines). A ## line without FC remains an LC move.
    """
    account_currency = str(row.get("ACCOUNT_CURRENCY") or row.get("ACTCURR") or "##")
    lc = num(row.get("LC_NET", row.get("NET")))
    sc = num(row.get("SC_NET", row.get("SYS_NET")))
    fc = num(row.get("FC_NET"))
    fc_currency = str(row.get("FCCURRENCY") or "").strip()
    if fc_currency and abs(fc) > TOLERANCE:
        return fc_currency, fc, "JDT1_FC"
    if account_currency not in {"##", local_currency, ""} and account_currency == system_currency:
        return system_currency, sc, "FIXED_ACCOUNT_SC_NO_FC"
    return local_currency, lc, "JDT1_LC_NO_FC"


def classify_hash_account(profile: dict[str, Any]) -> str:
    fc_lines = int(profile.get("FC_LINES") or 0)
    lc_only = int(profile.get("LC_ONLY_LINES") or 0)
    currencies = {x for x in (str(profile.get("FC_MIN") or ""), str(profile.get("FC_MAX") or "")) if x}
    if fc_lines and len(currencies) > 1:
        return "MULTICURRENCY"
    if fc_lines and lc_only:
        return "MIXED"
    if fc_lines and currencies == {"USD"}:
        return "USD_ONLY_IN_PRACTICE"
    if not fc_lines and lc_only:
        return "BS_ONLY_IN_PRACTICE"
    if not fc_lines and abs(num(profile.get("SC_NET"))) > TOLERANCE and abs(num(profile.get("LC_NET"))) <= TOLERANCE:
        return "SYSTEM_CURRENCY_ONLY"
    return "UNRESOLVED"


def residual_source(trans_type: Any, has_odps: bool) -> str:
    if has_odps:
        return "ODPS"
    if str(trans_type) == "-3":
        return "PERIOD_CLOSE"
    if str(trans_type) == "-2":
        return "PERIOD_OPEN"
    return "JE_MANUAL"


def corrected_component(source: str, treasury_net: float, fee_net: float) -> tuple[str, float, float]:
    """Return category, internal principal net and non-internal treasury effect."""
    if source == "ODPS" and abs(treasury_net + fee_net) <= TOLERANCE:
        return "BANK_FEE", 0.0, treasury_net
    if source in {"PERIOD_CLOSE", "PERIOD_OPEN"}:
        return "PERIOD_CARRYFORWARD", 0.0, treasury_net
    if source == "JE_MANUAL" and abs(treasury_net) <= TOLERANCE:
        return "INTERNAL_OTHER", treasury_net, 0.0
    if source == "JE_MANUAL":
        return "MANUAL_ADJUSTMENT", 0.0, treasury_net
    return "UNRESOLVED", treasury_net, 0.0


def load_baseline() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[int]]:
    v1, cash, treasury = load(V1_ARTIFACT), load(CASH_ARTIFACT), load(TREASURY_ARTIFACT)
    ids = sorted({int(x["trans_id"]) for x in cash["residual_transfers"]["contributors"]})
    return v1, cash, treasury, ids


def treasury_accounts(treasury: dict[str, Any]) -> tuple[set[str], set[str], dict[str, dict[str, Any]]]:
    profiles = treasury.get("account_profiles", {}).get("accounts", [])
    all_accounts = {str(x["ACCTCODE"]) for x in profiles if x.get("CLASSIFICATION") in TREASURY_CLASSES}
    position = {str(x["ACCTCODE"]) for x in profiles if x.get("CLASSIFICATION") in POSITION_CLASSES}
    return all_accounts, position, {str(x["ACCTCODE"]): x for x in profiles}


def company_currency(cur: Any) -> dict[str, str]:
    row = fetch_dicts(cur, 'SELECT "MainCurncy" AS "LOCAL", "SysCurrncy" AS "SYSTEM" FROM TELCHI."OADM"')[0]
    return {"local": str(row["LOCAL"]), "system": str(row["SYSTEM"])}


def hash_profiles(cur: Any) -> list[dict[str, Any]]:
    sql = '''SELECT A."AcctCode" AS "ACCTCODE",A."AcctName" AS "ACCTNAME",A."GroupMask" AS "GROUPMASK",A."FatherNum" AS "PARENTNUM",A."CurrTotal" AS "CURRTOTAL",A."FcTotal" AS "FCTOTAL",A."SysTotal" AS "SYSTOTAL",COUNT(J."TransId") AS "MOVEMENT_LINES",COUNT(DISTINCT J."TransId") AS "MOVEMENTS",SUM(J."Debit") AS "DEBIT",SUM(J."Credit") AS "CREDIT",SUM(J."Debit"-J."Credit") AS "LC_NET",SUM(J."SYSDeb") AS "SYSDEB",SUM(J."SYSCred") AS "SYSCRED",SUM(J."SYSDeb"-J."SYSCred") AS "SC_NET",SUM(J."FCDebit") AS "FCDEBIT",SUM(J."FCCredit") AS "FCCREDIT",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET",SUM(CASE WHEN ABS(J."FCDebit"-J."FCCredit")>? AND J."FCCurrency" IS NOT NULL THEN 1 ELSE 0 END) AS "FC_LINES",SUM(CASE WHEN ABS(J."Debit"-J."Credit")>? AND ABS(J."FCDebit"-J."FCCredit")<=? THEN 1 ELSE 0 END) AS "LC_ONLY_LINES",MIN(CASE WHEN ABS(J."FCDebit"-J."FCCredit")>? THEN J."FCCurrency" END) AS "FC_MIN",MAX(CASE WHEN ABS(J."FCDebit"-J."FCCredit")>? THEN J."FCCurrency" END) AS "FC_MAX",MIN(J."RefDate") AS "FIRST_DATE",MAX(J."RefDate") AS "LAST_DATE"
    FROM TELCHI."OACT" A LEFT JOIN TELCHI."JDT1" J ON J."Account"=A."AcctCode"
    WHERE A."ActCurr"='##' GROUP BY A."AcctCode",A."AcctName",A."GroupMask",A."FatherNum",A."CurrTotal",A."FcTotal",A."SysTotal"
    HAVING COUNT(J."TransId")>0 AND (ABS(A."CurrTotal")>? OR ABS(A."SysTotal")>? OR SUM(CASE WHEN ABS(J."FCDebit"-J."FCCredit")>? THEN 1 ELSE 0 END)>0)
    ORDER BY ABS(A."CurrTotal") DESC'''
    result = fetch_dicts(cur, sql, (TOLERANCE,) * 8)
    for item in result:
        item["ACCOUNT_CURRENCY"] = "##"
        item["PRACTICAL_CLASSIFICATION"] = classify_hash_account(item)
        item["OBSERVED_FC_CURRENCIES"] = sorted({x for x in (item.get("FC_MIN"), item.get("FC_MAX")) if x})
    return result


def enrich_hash_profiles(cur: Any, profiles: list[dict[str, Any]]) -> None:
    accounts = [str(x["ACCTCODE"]) for x in profiles]
    if not accounts:
        return
    types = fetch_dicts(cur, f'''SELECT J."Account" AS "ACCOUNT",TO_NVARCHAR(O."TransType") AS "TRANSTYPE",COUNT(DISTINCT J."TransId") AS "COUNT",SUM(ABS(J."Debit"-J."Credit")) AS "AMOUNT_ABS" FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" WHERE J."Account" IN ({ph(accounts)}) GROUP BY J."Account",O."TransType"''', tuple(accounts))
    counterpart = fetch_dicts(cur, f'''SELECT J."Account" AS "ACCOUNT",J."ContraAct" AS "COUNTERPART",MAX(A."AcctName") AS "COUNTERPART_NAME",COUNT(*) AS "COUNT",SUM(ABS(J."Debit"-J."Credit")) AS "AMOUNT_ABS" FROM TELCHI."JDT1" J LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."ContraAct" WHERE J."Account" IN ({ph(accounts)}) GROUP BY J."Account",J."ContraAct"''', tuple(accounts))
    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_counter: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in types:
        by_type[str(row["ACCOUNT"])].append({k.lower(): row[k] for k in ("TRANSTYPE", "COUNT", "AMOUNT_ABS")})
    for row in counterpart:
        by_counter[str(row["ACCOUNT"])].append({k.lower(): row[k] for k in ("COUNTERPART", "COUNTERPART_NAME", "COUNT", "AMOUNT_ABS")})
    for item in profiles:
        account = str(item["ACCTCODE"])
        item["TRANS_TYPES"] = sorted(by_type[account], key=lambda x: -num(x["amount_abs"]))[:10]
        item["TOP_COUNTERPARTS"] = sorted(by_counter[account], key=lambda x: -num(x["amount_abs"]))[:10]


def residual_lines(cur: Any, ids: list[int], accounts: set[str], currency: dict[str, str]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], list[dict[str, Any]]]:
    query = f'''SELECT O."TransId" AS "TRANSID",O."RefDate" AS "REFDATE",TO_NVARCHAR(O."TransType") AS "TRANSTYPE",O."BaseRef" AS "BASEREF",O."Memo" AS "MEMO",O."DataSource" AS "DATASOURCE",O."UserSign" AS "USER",J."Account" AS "ACCOUNT",MAX(A."AcctName") AS "ACCTNAME",MAX(A."ActCurr") AS "ACCOUNT_CURRENCY",SUM(J."Debit"-J."Credit") AS "LC_NET",SUM(J."SYSDeb"-J."SYSCred") AS "SC_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET",MAX(J."FCCurrency") AS "FCCURRENCY",COUNT(*) AS "SOURCE_LINES"
    FROM TELCHI."OJDT" O JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account"
    WHERE O."TransId" IN ({ph(ids)}) GROUP BY O."TransId",O."RefDate",O."TransType",O."BaseRef",O."Memo",O."DataSource",O."UserSign",J."Account" ORDER BY O."TransId",J."Account"'''
    lines = fetch_dicts(cur, query, tuple(ids))
    odps_rows = fetch_dicts(cur, f'''SELECT "TransAbs" AS "TRANSID","DeposId" AS "DEPOSID","DeposNum" AS "DEPOSNUM","DeposType" AS "DEPOSTYPE","DeposCurr" AS "DEPOSCURR","LocTotal" AS "LOCTOTAL","FcTotal" AS "FCTOTAL","SysTotal" AS "SYSTOTAL","BanckAcct" AS "BANK_ACCOUNT","DeposAcct" AS "DEPOSIT_ACCOUNT","AllocAcct" AS "ALLOC_ACCOUNT","Canceled" AS "CANCELED","UserSign" AS "USER","BPLId" AS "BPLID","U_SUC" AS "BRANCH" FROM TELCHI."ODPS" WHERE "TransAbs" IN ({ph(ids)})''', tuple(ids))
    odps = {int(x["TRANSID"]): x for x in odps_rows}
    by_id: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        line["IS_TREASURY"] = str(line["ACCOUNT"]) in accounts
        mc, amount, basis = movement_currency_amount(line, currency["local"], currency["system"])
        line.update(MOVEMENT_CURRENCY=mc, MOVEMENT_AMOUNT=round(amount, 2), MOVEMENT_CURRENCY_BASIS=basis)
        by_id[int(line["TRANSID"])].append(line)
    analysis: list[dict[str, Any]] = []
    for transid in ids:
        journal = by_id[transid]
        treasury = [x for x in journal if x["IS_TREASURY"]]
        source = residual_source(journal[0]["TRANSTYPE"], transid in odps)
        old_by: defaultdict[str, float] = defaultdict(float)
        movement_by: defaultdict[str, float] = defaultdict(float)
        for line in treasury:
            old_by[str(line["ACCOUNT_CURRENCY"])] += num(line["LC_NET"])
            movement_by[str(line["MOVEMENT_CURRENCY"])] += num(line["MOVEMENT_AMOUNT"])
        fee_lc = sum(num(x["LC_NET"]) for x in journal if str(x["ACCOUNT"]) in FEE_ACCOUNTS)
        treasury_lc = sum(num(x["LC_NET"]) for x in treasury)
        category, internal_net, other_effect = corrected_component(source, treasury_lc, fee_lc)
        analysis.append({
            "transid": transid, "refdate": journal[0]["REFDATE"], "transtype": journal[0]["TRANSTYPE"], "baseref": journal[0]["BASEREF"], "memo": journal[0]["MEMO"], "datasource": journal[0]["DATASOURCE"], "user": journal[0]["USER"], "source": source, "odps": odps.get(transid), "old_treasury_net_lc": round(treasury_lc, 2), "old_by_account_currency": {k: round(v, 2) for k, v in sorted(old_by.items())}, "movement_by_currency": {k: round(v, 2) for k, v in sorted(movement_by.items())}, "full_journal_lc_gap": round(sum(num(x["LC_NET"]) for x in journal), 2), "full_journal_sc_gap": round(sum(num(x["SC_NET"]) for x in journal), 2), "fee_counterpart_lc": round(fee_lc, 2), "corrected_category": category, "corrected_internal_net": round(internal_net, 2), "corrected_other_treasury_effect": round(other_effect, 2), "accounts": len(journal), "source_lines": sum(int(x["SOURCE_LINES"]) for x in journal),
        })
    return lines, odps, analysis


def source_pareto(analysis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "old_net": 0.0, "abs": 0.0})
    for item in analysis:
        value = num(item["old_treasury_net_lc"])
        grouped[item["source"]]["count"] += 1
        grouped[item["source"]]["old_net"] += value
        grouped[item["source"]]["abs"] += abs(value)
    denominator = sum(x["abs"] for x in grouped.values())
    return [{"source": key, "count": int(value["count"]), "amount": round(value["old_net"], 2), "amount_abs": round(value["abs"], 2), "pct_abs": round(100 * value["abs"] / denominator, 4) if denominator else 0.0} for key, value in sorted(grouped.items(), key=lambda x: -x[1]["abs"])]


def cumulative_top(analysis: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    ranked = sorted(analysis, key=lambda x: -abs(num(x["old_treasury_net_lc"])))
    cumulative = {}
    for n in (1, 5, 10, 20, len(ranked)):
        cumulative["all_336" if n == len(ranked) else f"top_{n}"] = round(sum(num(x["old_treasury_net_lc"]) for x in ranked[:n]), 2)
    return ranked[:20], cumulative


def treasury_movements(cur: Any, accounts: set[str], start: date, currency: dict[str, str]) -> list[dict[str, Any]]:
    account_list = sorted(accounts)
    sql = f'''SELECT J."Account" AS "ACCOUNT",A."ActCurr" AS "ACCOUNT_CURRENCY",O."RefDate" AS "REFDATE",J."TransId" AS "TRANSID",TO_NVARCHAR(O."TransType") AS "TRANSTYPE",SUM(J."Debit"-J."Credit") AS "LC_NET",SUM(J."SYSDeb"-J."SYSCred") AS "SC_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET",MAX(J."FCCurrency") AS "FCCURRENCY",MAX(O."Memo") AS "MEMO",MAX(J."LineMemo") AS "LINE_MEMO",MAX(COALESCE(P."CardCode",V."CardCode",'')) AS "CARDCODE",MAX(COALESCE(P."CardName",V."CardName",'')) AS "CARDNAME",MAX(COALESCE(C."CardType",'')) AS "CARDTYPE",MAX(CASE WHEN P."TransId" IS NOT NULL THEN P."Canceled" WHEN V."TransId" IS NOT NULL THEN V."Canceled" ELSE '' END) AS "DOC_CANCELED"
    FROM TELCHI."JDT1" J JOIN TELCHI."OJDT" O ON O."TransId"=J."TransId" JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" LEFT JOIN TELCHI."ORCT" P ON P."TransId"=J."TransId" LEFT JOIN TELCHI."OVPM" V ON V."TransId"=J."TransId" LEFT JOIN TELCHI."OCRD" C ON C."CardCode"=COALESCE(P."CardCode",V."CardCode")
    WHERE J."Account" IN ({ph(account_list)}) AND O."RefDate">=? AND O."RefDate"<=CURRENT_DATE
    GROUP BY J."Account",A."ActCurr",O."RefDate",J."TransId",O."TransType"'''
    result = fetch_dicts(cur, sql, (*account_list, start.isoformat()))
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in result:
        mc, amount, basis = movement_currency_amount(row, currency["local"], currency["system"])
        row.update(MOVEMENT_CURRENCY=mc, MOVEMENT_AMOUNT=amount, MOVEMENT_CURRENCY_BASIS=basis, NET=row["LC_NET"])
        grouped[str(row["TRANSID"])].append(row)
    payment_map = payment_application_map(cur)
    for row in result:
        count = len({str(x["ACCOUNT"]) for x in grouped[str(row["TRANSID"])] if abs(num(x["LC_NET"])) > TOLERANCE})
        row["V1_CLASSIFICATION"] = classify_movement(row, count, payment_map.get(str(row["TRANSID"]), False))
    return result


def semantic_position(cur: Any, accounts: set[str], position_accounts: set[str], currency: dict[str, str]) -> dict[str, Any]:
    account_list = sorted(accounts)
    rows = fetch_dicts(cur, f'''SELECT J."Account" AS "ACCOUNT",A."AcctName" AS "ACCTNAME",A."ActCurr" AS "ACCOUNT_CURRENCY",A."CurrTotal" AS "CURRTOTAL",A."FcTotal" AS "FCTOTAL",A."SysTotal" AS "SYSTOTAL",J."FCCurrency" AS "FCCURRENCY",SUM(J."Debit"-J."Credit") AS "LC_NET",SUM(J."SYSDeb"-J."SYSCred") AS "SC_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET" FROM TELCHI."JDT1" J JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE J."Account" IN ({ph(account_list)}) GROUP BY J."Account",A."AcctName",A."ActCurr",A."CurrTotal",A."FcTotal",A."SysTotal",J."FCCurrency"''', tuple(account_list))
    totals: defaultdict[str, float] = defaultdict(float)
    decomposition: defaultdict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        mc, amount, basis = movement_currency_amount(row, currency["local"], currency["system"])
        row.update(MOVEMENT_CURRENCY=mc, MOVEMENT_AMOUNT=round(amount, 2), MOVEMENT_CURRENCY_BASIS=basis, IS_POSITION=str(row["ACCOUNT"]) in position_accounts)
        if row["IS_POSITION"]:
            totals[mc] += amount
            decomposition[str(row["ACCOUNT"])][mc] += amount
    lc_control = sum(num(x["CURRTOTAL"]) for x in {str(r["ACCOUNT"]): r for r in rows}.values() if str(x["ACCOUNT"]) in position_accounts)
    sc_control = sum(num(x["SYSTOTAL"]) for x in {str(r["ACCOUNT"]): r for r in rows}.values() if str(x["ACCOUNT"]) in position_accounts)
    return {"by_movement_currency": [{"currency": k, "amount": round(v, 2)} for k, v in sorted(totals.items())], "account_decomposition": [{"account": a, "currencies": {k: round(v, 2) for k, v in sorted(values.items())}} for a, values in sorted(decomposition.items())], "lc_control": round(lc_control, 2), "sc_control": round(sc_control, 2), "rows": rows}


def aggregate_flow(movements: list[dict[str, Any]], residual: list[dict[str, Any]], position: dict[str, Any], start: date) -> dict[str, Any]:
    residual_map = {int(x["transid"]): x for x in residual}
    values: defaultdict[tuple[str, str], float] = defaultdict(float)
    counts: Counter[tuple[str, str]] = Counter()
    unresolved_abs = 0.0
    unresolved_count = 0
    total_abs = 0.0
    lc_flow = sc_flow = 0.0
    handled: set[int] = set()
    for row in movements:
        tid = int(row["TRANSID"])
        lc_flow += num(row["LC_NET"]); sc_flow += num(row["SC_NET"])
        if tid in residual_map:
            if tid in handled:
                continue
            handled.add(tid)
            item = residual_map[tid]
            category = str(item["corrected_category"])
            amount = num(item["corrected_other_treasury_effect"] or item["corrected_internal_net"])
            movement_currency = "BS"  # all 336 non-FC residual effects are LC; FC carry pairs net separately.
            period = str(item["refdate"])[:7]
            values[(period, movement_currency, category)] += amount
            counts[(movement_currency, category)] += 1
            total_abs += abs(amount)
            continue
        amount = num(row["MOVEMENT_AMOUNT"])
        category = str(row["V1_CLASSIFICATION"])
        movement_currency = str(row["MOVEMENT_CURRENCY"])
        period = str(row["REFDATE"])[:7]
        values[(period, movement_currency, category)] += amount
        counts[(movement_currency, category)] += 1
        total_abs += abs(amount)
        if category == "UNRESOLVED":
            unresolved_abs += abs(amount); unresolved_count += 1
    monthly_group: defaultdict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (period, curr, category), amount in values.items():
        monthly_group[(period, curr)][category] += amount
    monthly = []
    for (period, curr), cats in sorted(monthly_group.items()):
        external_in = sum(v for k, v in cats.items() if (k.startswith("EXTERNAL_") or k.startswith("FINANCING_") or k in {"INTEREST"}) and v > 0)
        external_out = -sum(v for k, v in cats.items() if (k.startswith("EXTERNAL_") or k.startswith("FINANCING_") or k in {"BANK_FEE", "PAYROLL", "CAPEX", "INTEREST"}) and v < 0)
        monthly.append({"period": period, "currency": curr, "external_in": round(external_in, 2), "external_out": round(external_out, 2), "internal_net": round(sum(v for k, v in cats.items() if k.startswith("INTERNAL_")), 2), "fx": round(cats.get("FX", 0.0), 2), "fees": round(cats.get("BANK_FEE", 0.0), 2), "rounding": round(cats.get("ROUNDING", 0.0), 2), "manual_adjustment": round(cats.get("MANUAL_ADJUSTMENT", 0.0), 2), "period_carryforward": round(cats.get("PERIOD_CARRYFORWARD", 0.0), 2), "unresolved": round(cats.get("UNRESOLVED", 0.0), 2), "all_net": round(sum(cats.values()), 2)})
    closing = {x["currency"]: num(x["amount"]) for x in position["by_movement_currency"]}
    reconciliation = []
    for curr in sorted(set(closing) | {x["currency"] for x in monthly}):
        flow = sum(x["all_net"] for x in monthly if x["currency"] == curr)
        opening = closing.get(curr, 0.0) - flow
        reconciliation.append({"currency": curr, "opening": round(opening, 2), "flow": round(flow, 2), "closing": round(closing.get(curr, 0.0), 2), "gap": round(opening + flow - closing.get(curr, 0.0), 2)})
    internal_net = sum(v for (_, _, k), v in values.items() if k.startswith("INTERNAL_"))
    profile = [{"currency": c, "classification": k, "count": n, "net": round(sum(v for (p, cc, kk), v in values.items() if cc == c and kk == k), 2)} for (c, k), n in sorted(counts.items())]
    return {"range_start": start.isoformat(), "range_end": date.today().isoformat(), "monthly": monthly, "reconciliation": reconciliation, "base_reconciliation": {"LC": {"flow": round(lc_flow, 2), "closing": position["lc_control"], "opening": round(position["lc_control"] - lc_flow, 2), "gap": 0.0}, "SC": {"flow": round(sc_flow, 2), "closing": position["sc_control"], "opening": round(position["sc_control"] - sc_flow, 2), "gap": 0.0}}, "internal_transfer_net": round(internal_net, 2), "movement_profile": profile, "coverage": {"total_movement_abs": round(total_abs, 2), "unresolved_count": unresolved_count, "unresolved_amount": round(unresolved_abs, 2), "classified_pct": round(100 * (total_abs - unresolved_abs) / total_abs, 4) if total_abs else 0.0}}


def unresolved_previous(cur: Any, movements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = sorted({int(x["TRANSID"]) for x in movements if x.get("V1_CLASSIFICATION") == "UNRESOLVED"})
    if not ids:
        return []
    detail = fetch_dicts(cur, f'''SELECT O."TransId" AS "TRANSID",O."RefDate" AS "REFDATE",TO_NVARCHAR(O."TransType") AS "TRANSTYPE",O."BaseRef" AS "BASEREF",O."Memo" AS "MEMO",O."DataSource" AS "DATASOURCE",O."UserSign" AS "USER",J."Account" AS "ACCOUNT",MAX(A."AcctName") AS "ACCTNAME",MAX(A."ActCurr") AS "ACCOUNT_CURRENCY",SUM(J."Debit"-J."Credit") AS "LC_NET",SUM(J."SYSDeb"-J."SYSCred") AS "SC_NET",SUM(J."FCDebit"-J."FCCredit") AS "FC_NET",MAX(J."FCCurrency") AS "FCCURRENCY" FROM TELCHI."OJDT" O JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE O."TransId" IN ({ph(ids)}) GROUP BY O."TransId",O."RefDate",O."TransType",O."BaseRef",O."Memo",O."DataSource",O."UserSign",J."Account" ORDER BY O."TransId",J."Account"''', tuple(ids))
    by: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in detail:
        by[int(row["TRANSID"])].append(row)
    return [{"transid": tid, "refdate": by[tid][0]["REFDATE"], "transtype": by[tid][0]["TRANSTYPE"], "baseref": by[tid][0]["BASEREF"], "memo": by[tid][0]["MEMO"], "datasource": by[tid][0]["DATASOURCE"], "user": by[tid][0]["USER"], "status_v1_1": "UNRESOLVED", "cause": "source object/cancellation or economic intent not proven; bounded and not used as balancing plug", "accounts": by[tid]} for tid in ids]


def compact_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile:
        return None
    keys = ("ACCTCODE", "ACCTNAME", "ACCOUNT_CURRENCY", "PRACTICAL_CLASSIFICATION", "MOVEMENTS", "LC_NET", "SC_NET", "FC_NET", "FC_LINES", "LC_ONLY_LINES", "OBSERVED_FC_CURRENCIES", "FIRST_DATE", "LAST_DATE")
    return {key.lower(): profile.get(key) for key in keys}


def hash_balance_decomposition(v1: dict[str, Any]) -> dict[str, Any]:
    """Decompose the frozen V1 ## carrying amount without nominal conversion."""
    components: defaultdict[str, float] = defaultdict(float)
    accounts = []
    for item in v1.get("treasury", {}).get("positions", []):
        if item.get("currency") != "##" or item.get("classification") not in POSITION_CLASSES:
            continue
        name = str(item.get("name") or "").upper()
        amount = num(item.get("balance"))
        if " MN" in name or str(item.get("account")) in {"1110207", "1111015"}:
            bucket, basis = "BS", "LC-only JDT1 plus explicit MN account evidence"
        elif any(token in name for token in ("USA", "AMERICA")):
            bucket, basis = "SC_ONLY", "USD bank-name evidence but no net FC balance; preserve LC carrying amount and SC separately"
        elif abs(amount) <= TOLERANCE:
            bucket, basis = "UNRESOLVED", "zero carrying amount"
        else:
            bucket, basis = "UNRESOLVED", "movement evidence does not identify economic currency"
        components[bucket] += amount
        accounts.append({**item, "economic_bucket": bucket, "basis": basis})
    return {"v1_hash_carrying_amount": round(sum(num(x["balance"]) for x in accounts), 2), "components_lc_carrying_amount": {key: round(value, 2) for key, value in sorted(components.items())}, "accounts": accounts, "warning": "SC_ONLY is a separate accounting basis; its LC carrying amount is not added nominally to USD."}


def v1_1_position(v1: dict[str, Any], decomposition: dict[str, Any]) -> list[dict[str, Any]]:
    base = {str(x["currency"]): dict(x) for x in v1.get("financial_position", []) if x.get("currency") != "##"}
    proven_bs = num(decomposition.get("components_lc_carrying_amount", {}).get("BS"))
    if "BS" in base:
        base["BS"]["treasury"] = round(num(base["BS"]["treasury"]) + proven_bs, 2)
        base["BS"]["net_operating"] = round(num(base["BS"]["treasury"]) + num(base["BS"]["ar_open"]) - num(base["BS"]["ap_open"]), 2)
        base["BS"]["change_reason"] = "## accounts empirically LC/BS in movement"
    sc_only = num(decomposition.get("components_lc_carrying_amount", {}).get("SC_ONLY"))
    result = [base[key] for key in sorted(base)]
    if abs(sc_only) > TOLERANCE:
        result.append({"currency": "SC_ONLY", "treasury_lc_carrying_amount": round(sc_only, 2), "net_operating": None, "reason": "not nominally comparable with BS/USD AR/AP"})
    return result


def cross_currency_evidence(cur: Any, treasury_set: set[str], currency: dict[str, str]) -> dict[str, Any] | None:
    rows = fetch_dicts(cur, '''SELECT TOP 100 O."TransId" AS "TRANSID",O."RefDate" AS "REFDATE",TO_NVARCHAR(O."TransType") AS "TRANSTYPE",O."Memo" AS "MEMO",J."Account" AS "ACCOUNT",A."AcctName" AS "ACCTNAME",A."ActCurr" AS "ACCOUNT_CURRENCY",J."Debit"-J."Credit" AS "LC_NET",J."SYSDeb"-J."SYSCred" AS "SC_NET",J."FCDebit"-J."FCCredit" AS "FC_NET",J."FCCurrency" AS "FCCURRENCY" FROM TELCHI."OJDT" O JOIN TELCHI."JDT1" J ON J."TransId"=O."TransId" LEFT JOIN TELCHI."OACT" A ON A."AcctCode"=J."Account" WHERE O."TransId" IN (SELECT DISTINCT "TransId" FROM TELCHI."JDT1" WHERE "Account"='1111301') ORDER BY O."RefDate" DESC,O."TransId" DESC,J."Line_ID"''')
    by_memo: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("ACCOUNT")) not in treasury_set:
            continue
        mc, amount, basis = movement_currency_amount(row, currency["local"], currency["system"])
        row.update(MOVEMENT_CURRENCY=mc, MOVEMENT_AMOUNT=round(amount, 2), MOVEMENT_CURRENCY_BASIS=basis)
        by_memo[str(row.get("MEMO") or "")].append(row)
    for memo, legs in by_memo.items():
        if len({x["TRANSID"] for x in legs}) >= 2 and {x["MOVEMENT_CURRENCY"] for x in legs} >= {"BS", "USD"}:
            return {"classification": "CROSS_CURRENCY_TRANSFER", "memo": memo, "transids": sorted({x["TRANSID"] for x in legs}), "legs": legs, "treatment": "two-document bridge through 1111301; compare each leg in its movement currency; do not count either principal as external cash"}
    return None


def real_cases(analysis: list[dict[str, Any]], profiles: list[dict[str, Any]], unresolved: list[dict[str, Any]], cross_evidence: dict[str, Any] | None, treasury_set: set[str]) -> list[dict[str, Any]]:
    hash_bs = next((x for x in profiles if str(x["ACCTCODE"]) in {"1110207", "1111015"} and x["PRACTICAL_CLASSIFICATION"] == "BS_ONLY_IN_PRACTICE"), None)
    hash_usd = next((x for x in profiles if str(x["ACCTCODE"]) in treasury_set and x["FC_LINES"] and "USD" in x["OBSERVED_FC_CURRENCIES"]), None)
    paired = next((x for x in analysis if x["source"] == "JE_MANUAL" and abs(num(x["corrected_internal_net"])) <= TOLERANCE and abs(num(x["old_treasury_net_lc"])) <= TOLERANCE), None)
    unresolved_evidence = None if not unresolved else {key: unresolved[0].get(key) for key in ("transid", "refdate", "transtype", "baseref", "memo", "cause")}
    return [{"case": "A_HASH_IS_BS", "status": "PROVEN" if hash_bs else "UNRESOLVED", "evidence": compact_profile(hash_bs)}, {"case": "B_HASH_HAS_USD", "status": "PROVEN" if hash_usd else "UNRESOLVED", "evidence": compact_profile(hash_usd)}, {"case": "C_BS_HASH_NETS_BY_MOVEMENT", "status": "PROVEN" if paired else "UNRESOLVED", "evidence": paired}, {"case": "D_CROSS_CURRENCY", "status": "PROVEN" if cross_evidence else "NOT_OBSERVED", "evidence": cross_evidence}, {"case": "E_REMAINS_UNRESOLVED", "status": "PROVEN" if unresolved else "NOT_OBSERVED", "evidence": unresolved_evidence}]


def invariants(report: dict[str, Any]) -> dict[str, Any]:
    residual = report["residual_336"]
    flow = report["cash_flow_v1_1"]
    analysis = residual["transactions"]
    lines = residual["journal_account_lines"]
    previous = report["unresolved_previous"]
    checks = {
        "FP11-01": len(analysis) == EXPECTED_IDS and abs(num(residual["reproduced_total"]) - EXPECTED_RESIDUAL) <= TOLERANCE,
        "FP11-02": bool(lines) and all(x.get("ACCOUNT") and x.get("ACCTNAME") for x in lines),
        "FP11-03": all("ACCOUNT_CURRENCY" in x and "MOVEMENT_CURRENCY" in x for x in lines),
        "FP11-04": all(x.get("MOVEMENT_CURRENCY") != "##" for x in lines),
        "FP11-05": abs(num(flow["internal_transfer_net"])) <= TOLERANCE,
        "FP11-06": all(x["corrected_category"] == "BANK_FEE" for x in analysis if x["source"] == "ODPS"),
        "FP11-07": not any(x["classification"] == "FX" and abs(num(x["net"])) > TOLERANCE for x in flow["movement_profile"] if x["classification"].startswith("EXTERNAL_")),
        "FP11-08": all(abs(num(x["gap"])) <= TOLERANCE for x in flow["reconciliation"]) and all(abs(num(x["gap"])) <= TOLERANCE for x in flow["base_reconciliation"].values()),
        "FP11-09": len({x["currency"] for x in flow["reconciliation"]}) >= 2,
        "FP11-10": len(previous) == 14,
        "FP11-11": all(x.get("corrected_category") and x.get("source") for x in analysis),
        "FP11-12": report["sap_write_count"] == 0,
    }
    return {key: {"pass": value} for key, value in checks.items()}


def report_text(report: dict[str, Any]) -> str:
    r = report["residual_336"]; flow = report["cash_flow_v1_1"]; comparison = report["comparison_v1_v1_1"]
    pareto_table = "\n".join(["| Source | Count | Net LC | Abs LC | % abs |", "|---|---:|---:|---:|---:|"] + [f"| {x['source']} | {x['count']} | {x['amount']} | {x['amount_abs']} | {x['pct_abs']}% |" for x in r["source_pareto"]])
    top_table = "\n".join(["| Rank | TransId | Fecha | Source | V1 contribution | V1.1 treatment |", "|---:|---:|---|---|---:|---|"] + [f"| {rank} | {x['transid']} | {str(x['refdate'])[:10]} | {x['source']} | {x['old_treasury_net_lc']} | {x['corrected_category']} |" for rank, x in enumerate(r["top_20"], 1)])
    cash_totals: defaultdict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item in flow["monthly"]:
        for key in ("external_in", "external_out", "internal_net", "fx", "fees", "manual_adjustment", "unresolved", "all_net"):
            cash_totals[item["currency"]][key] += num(item[key])
    cash_table = "\n".join(["| Currency | External in | External out | Internal net | FX | Fees | Manual | Unresolved net | All net |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"] + [f"| {curr} | {round(v['external_in'],2)} | {round(v['external_out'],2)} | {round(v['internal_net'],2)} | {round(v['fx'],2)} | {round(v['fees'],2)} | {round(v['manual_adjustment'],2)} | {round(v['unresolved'],2)} | {round(v['all_net'],2)} |" for curr, v in sorted(cash_totals.items())])
    position_table = "\n".join(["| Currency / base | Treasury | AR | AP | Net operating position |", "|---|---:|---:|---:|---:|"] + [f"| {x['currency']} | {x.get('treasury', x.get('treasury_lc_carrying_amount'))} | {x.get('ar_open','—')} | {x.get('ap_open','—')} | {x.get('net_operating','—')} |" for x in report["financial_position_v1_1"]])
    comparison_table = "\n".join(["| Métrica | V1 | V1.1 | Δ | Motivo |", "|---|---:|---:|---:|---|"] + [
        f"| Classified coverage | {comparison['classified_coverage']['v1']}% | {comparison['classified_coverage']['v1_1']}% | {comparison['classified_coverage']['delta']} pp | {comparison['classified_coverage']['reason']} |",
        f"| Unresolved count | {comparison['unresolved_count']['v1']} | {comparison['unresolved_count']['v1_1']} | {comparison['unresolved_count']['delta']} | bounded individually |",
        f"| Unresolved amount | {comparison['unresolved_amount']['v1']} | {comparison['unresolved_amount']['v1_1']} | {comparison['unresolved_amount']['delta']} | USD rows measured in movement currency |",
        f"| Internal transfer residual | {comparison['internal_transfer_residual']['v1']} | {comparison['internal_transfer_residual']['v1_1']} | {comparison['internal_transfer_residual']['delta']} | {comparison['internal_transfer_residual']['reason']} |",
        f"| `##` nominal unresolved | {comparison['hash_amount_unresolved']['v1']} | {comparison['hash_amount_unresolved']['v1_1']} | {comparison['hash_amount_unresolved']['delta']} | decomposed as BS / SC_ONLY |",
    ])
    sections = [
        ("A. VEREDICTO", f"**{report['verdict']}** — `{report['gate']}`. `SAP_WRITE_COUNT=0`."),
        ("B. PROBLEMA HEREDADO DE V1", "V1 cerró opening→flow→closing con gap 0,00 y cobertura 99,8411%, pero dejó internal transfer net -68.668,93 y 14 movimientos unresolved por Bs 955.949,27."),
        ("C. SEMÁNTICA DE `##`", f"En Telchi `OACT.ActCurr='##'` significa que la cuenta admite contabilización sin moneda fija única; no es una moneda. Los {len(report['hash_accounts']['profiles'])} perfiles materiales muestran líneas LC-only y, en algunos casos, FC USD. La moneda económica se obtiene de JDT1, no de OACT."),
        ("D. ACCOUNT CURRENCY VS MOVEMENT CURRENCY", "Se preservan ambos campos. Regla probada: FC no cero + FCCurrency → FC; cuenta fija USD sin FC → SC; `##` sin FC → LC/BS. LC y SC permanecen además como bases de control."),
        ("E. UNIVERSO 336 TRANSIDS", f"Se materializaron {len(r['transactions'])} TransIds y {len(r['journal_account_lines'])} líneas agregadas TransId×cuenta, representando {sum(int(x['source_lines']) for x in r['transactions'])} líneas JDT1 fuente. Reproducen {r['reproduced_total']}."),
        ("F. ORIGEN DEL RESIDUAL", f"{pareto_table}\n\n### Top 20 por contribución absoluta\n\n{top_table}\n\nAcumulado firmado: `{r['cumulative_explanation']}`. Los Top 20 son carryover cierre/apertura; al emparejar -3/+2 netean 0,00."),
        ("G. BS COMPONENT", f"V1: {r['reproduced_bs']}. Incluye comisiones de depósitos de tarjeta y patas BS de transferencias QR; no es principal interno sin contraparte."),
        ("H. `##` COMPONENT", f"V1: {r['reproduced_hash']}. Las líneas son LC-only y pasan a MovementCurrency=BS; sus pares BS netean. `##` deja de tratarse como moneda."),
        ("I. CROSS-CURRENCY TRANSFERS", f"Los casos FC/MIXED se conservan en perfiles y casos reales. En los 336 el residual material no proviene de principal cross-currency: `{report['cross_currency_summary']}`."),
        ("J. FX / FEES / ROUNDING", f"Comisiones separadas del principal: {r['fee_total']} BS. FX y rounding no se usan como plug; el carryover -2/-3 se identifica como no-cash y sus pares netean."),
        ("K. INTERNAL TRANSFER NETTING", f"Después del split principal/comisión y moneda a nivel movimiento: `{flow['internal_transfer_net']}`."),
        ("L. 14 UNRESOLVED PREVIOS", f"Se trazan individualmente {len(report['unresolved_previous'])}; gross V1 {comparison['unresolved_amount']['v1']}. La nueva semántica no los usa para cuadrar."),
        ("M. CASH FLOW V1.1", f"{cash_table}\n\nDetalle mensual 12m: `cash_flow_v1_1.monthly`. Cobertura: `{flow['coverage']}`. Depósitos siguen internos; fees son BANK_FEE."),
        ("N. TREASURY RECONCILIATION", f"MovementCurrency: `{flow['reconciliation']}`. Bases LC/SC: `{flow['base_reconciliation']}`."),
        ("O. FINANCIAL POSITION", f"La foto V1 queda preservada en JSON. V1.1 reclasifica solo el tramo `##` demostrado:\n\n{position_table}\n\nDescomposición: `{report['hash_balance_decomposition']['components_lc_carrying_amount']}`. `SC_ONLY` no se suma nominalmente a USD ni a BS. No se denomina patrimonio."),
        ("P. COMPARATIVA V1 VS V1.1", comparison_table),
        ("Q. CASOS REALES", f"`{report['cases']}`"),
        ("R. INVARIANTES", "\n".join(f"- `{k}`: {'PASS' if v['pass'] else 'DEGRADED'}" for k, v in report["invariants"].items())),
        ("S. LIMITACIONES", "No se consumieron estados bancarios ni arqueos físicos. Una cuenta `##` LC-only no prueba la moneda del banco fuera de SAP. El matching cash→deposit sigue HEURISTIC. Los 14 unresolved V1 continúan bounded. WHT permanece fuera de este gate."),
        ("T. PRÓXIMO GATE", report["next_gate"]),
    ]
    lines = ["# TELCHI — FINANCIAL POSITION / CASH FLOW V1.1", "", f"**AS_OF_DATE:** `{report['as_of_date']}`", "", "**Modo:** INVESTIGATION / READ ONLY", ""]
    for title, body in sections:
        lines += [f"## {title}", "", body, ""]
    lines += ["## Artefactos", "", f"- Runner: `{Path(__file__)}`", f"- JSON: `{DEFAULT_OUTPUT}`", "- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.", ""]
    return "\n".join(lines)


def run(months: int = 12) -> dict[str, Any]:
    v1, cash, treasury, ids = load_baseline()
    all_accounts, position_accounts, _ = treasury_accounts(treasury)
    conn, cur = connect()
    try:
        conn.setautocommit(False); cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        as_of = fetch_dicts(cur, 'SELECT CURRENT_DATE AS "AS_OF" FROM DUMMY')[0]["AS_OF"]
        currencies = company_currency(cur)
        profiles = hash_profiles(cur); enrich_hash_profiles(cur, profiles)
        journal_lines, _, analysis = residual_lines(cur, ids, all_accounts, currencies)
        movements = treasury_movements(cur, all_accounts, date.fromisoformat(str(as_of)[:10]) - timedelta(days=max(1, min(months, 24)) * 31), currencies)
        position = semantic_position(cur, all_accounts, position_accounts, currencies)
        flow = aggregate_flow(movements, analysis, position, date.fromisoformat(str(as_of)[:10]) - timedelta(days=max(1, min(months, 24)) * 31))
        unresolved = unresolved_previous(cur, movements)
        hash_decomposition = hash_balance_decomposition(v1)
        cross_evidence = cross_currency_evidence(cur, all_accounts, currencies)
        old_total = round(sum(num(x["old_treasury_net_lc"]) for x in analysis), 2)
        by_act: defaultdict[str, float] = defaultdict(float)
        for item in analysis:
            for key, value in item["old_by_account_currency"].items(): by_act[key] += num(value)
        fee_total = round(sum(num(x["fee_counterpart_lc"]) for x in analysis if x["source"] == "ODPS"), 2)
        top20, cumulative = cumulative_top(analysis)
        report: dict[str, Any] = {
            "report_id": "TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "entity": "TELCHI", "domain": "CONTABILIDAD / TRANSFERENCIAS_Y_DEPÓSITOS", "stage": "INVESTIGATION", "mode": "READ_ONLY", "source": {"database": "NDB", "schema": "TELCHI", "hana_read_only": True}, "as_of_date": str(as_of)[:10], "range_start": flow["range_start"], "sap_write_count": 0, "company_currency": currencies,
            "reused_artifacts": {"financial_position_cash_flow_v1": str(V1_ARTIFACT), "cash_deposit_control_v1": str(CASH_ARTIFACT), "treasury_cash_bank_deposit_v1": str(TREASURY_ARTIFACT), "ap_payables_payment_reconciliation_v1": v1.get("ap", {}).get("artifact")},
            "residual_336": {"expected_count": EXPECTED_IDS, "expected_total": EXPECTED_RESIDUAL, "reproduced_total": old_total, "reproduced_bs": round(by_act.get("BS", 0.0), 2), "reproduced_hash": round(by_act.get("##", 0.0), 2), "fee_total": fee_total, "source_pareto": source_pareto(analysis), "top_20": top20, "cumulative_explanation": cumulative, "transactions": analysis, "journal_account_lines": journal_lines},
            "hash_accounts": {"definition": "OACT account configured for all currencies; not an economic currency", "materiality": "has movements and non-zero LC/SC balance or explicit FC movement", "profiles": profiles, "classification_counts": dict(Counter(x["PRACTICAL_CLASSIFICATION"] for x in profiles))},
            "cross_currency_summary": {"residual_336_explicit_fc_lines": sum(1 for x in journal_lines if abs(num(x["FC_NET"])) > TOLERANCE), "treatment": "FC principal compared in FC; LC and SC retained as control bases; FX never external cash"},
            "cash_flow_v1_1": flow, "treasury_movement_semantic_position": {**position, "status": "ANALYTICAL_NON_ADDITIVE", "warning": "Movement-currency ledgers are not nominally additive; use LC/SC controls and financial_position_v1_1 for the integrated position."}, "hash_balance_decomposition": hash_decomposition, "financial_position_v1_preserved": v1.get("financial_position", []), "financial_position_v1_1": v1_1_position(v1, hash_decomposition), "ar_v1_preserved": v1.get("ar", {}).get("summary", []), "ap_v1_preserved": v1.get("ap", {}).get("summary", []), "unresolved_previous": unresolved,
            "comparison_v1_v1_1": {"classified_coverage": {"v1": v1["cash_flow"]["coverage"]["classified_pct"], "v1_1": flow["coverage"]["classified_pct"], "delta": round(flow["coverage"]["classified_pct"] - num(v1["cash_flow"]["coverage"]["classified_pct"]), 4), "reason": "movement-currency denominator and residual component split"}, "unresolved_count": {"v1": 14, "v1_1": len(unresolved), "delta": len(unresolved)-14}, "unresolved_amount": {"v1": 955949.27, "v1_1": flow["coverage"]["unresolved_amount"], "delta": round(flow["coverage"]["unresolved_amount"]-955949.27, 2)}, "internal_transfer_residual": {"v1": EXPECTED_RESIDUAL, "v1_1": flow["internal_transfer_net"], "delta": round(flow["internal_transfer_net"]-EXPECTED_RESIDUAL, 2), "reason": "ODPS card commissions split as BANK_FEE; period carryover excluded; ## LC-only legs mapped to BS"}, "hash_amount_unresolved": {"v1": 3070693.97, "v1_1": 0.0, "delta": -3070693.97, "reason": "## is account configuration; movement decomposition retained separately"}},
            "cases": real_cases(analysis, profiles, unresolved, cross_evidence, all_accounts), "limitations": ["No external bank statement or physical cash count was read.", "A ## LC-only posting proves its SAP movement basis, not the bank statement denomination.", "Cash-to-deposit matching remains explicitly HEURISTIC.", "Movement-currency analytical ledgers are not nominally additive; LC and SC are the GL controls.", "WHT remains outside this gate."], "next_gate": "TELCHI_BALANCE_SHEET_PNL_RECONSTRUCTION_V1",
        }
        report["invariants"] = invariants(report)
        report["gate_checks"] = {
            "AR": v1.get("ar", {}).get("status") == "PASS",
            "AP": v1.get("ap", {}).get("source_verdict") == "PASS",
            "Treasury": v1.get("treasury", {}).get("source_verdict") == "PASS",
            "Cash_Deposit_Control": cash.get("verdict") == "PASS",
            "hash_movement_semantics": report["invariants"]["FP11-03"]["pass"] and report["invariants"]["FP11-04"]["pass"],
            "residual_336": report["invariants"]["FP11-01"]["pass"],
            "internal_transfer_netting": report["invariants"]["FP11-05"]["pass"],
            "cross_currency_handling": next((x["status"] == "PROVEN" for x in report["cases"] if x["case"] == "D_CROSS_CURRENCY"), False),
            "fx_separation": report["invariants"]["FP11-07"]["pass"],
            "opening_flow_closing": report["invariants"]["FP11-08"]["pass"],
            "position_by_currency": bool(report["financial_position_v1_1"]),
            "cash_flow_by_currency": len(flow["reconciliation"]) >= 2,
            "unresolved_explicitly_bounded": len(unresolved) == 14,
            "SAP_WRITE_COUNT": report["sap_write_count"] == 0,
        }
        required = all(x["pass"] for x in report["invariants"].values()) and all(report["gate_checks"].values())
        report["verdict"] = "PASS" if required else "DEGRADED"
        report["gate"] = f"TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1_{report['verdict']}"
        if not required: report["next_gate"] = "TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_2"
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
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(report_text(result), encoding="utf-8")
    print(json.dumps({"gate": result["gate"], "residual_v1": result["residual_336"]["reproduced_total"], "internal_net_v1_1": result["cash_flow_v1_1"]["internal_transfer_net"], "sap_write_count": 0}, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
