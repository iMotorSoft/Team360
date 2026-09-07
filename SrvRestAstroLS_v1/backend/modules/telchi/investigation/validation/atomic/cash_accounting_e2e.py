#!/usr/bin/env python3
"""H4 CASH ACCOUNTING TRACEABILITY — E2E runner (READ ONLY HANA).

Gate: TELCHI_ATOMIC_CASH_ACCOUNTING_TRACEABILITY_H4_V1
Chain: SALE -> ORCT --TransId--> OJDT -> JDT1[Account=CashAcct] -> OACT.
Window: 2023-02 (baseline gate window). Batch extract, local evaluation.

Primary evidence is transactional (payment -> journal -> line -> account);
aggregation is secondary control only.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

import pandas

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.atomic import connection as hconn
from modules.telchi.investigation.atomic.accounting import (
    build_cash_accounting_trace, evaluate_cash_accounting,
    branch_from_account_name,
)

WINDOW = ("2023-02-01", "2023-03-01")
OUT = ROOT / "validation" / "atomic" / "cash_accounting_h4_report.json"


def fetch(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d[0] for d in (cur.description or ())]
    return pandas.DataFrame(cur.fetchall(), columns=cols)


def main() -> int:
    try:
        conn, cur = hconn.connect()
    except Exception as e:
        print("STOP_MANUAL_PODMAN_START_REQUIRED:", str(e)[:120])
        return 3

    try:
        # ---- payments of the window with their expected cash account
        pay = fetch(cur, f'''
            SELECT "DocEntry","DocNum","TransId","Canceled","CashSum",
                   "CheckSum","TrsfrSum","CreditSum","NoDocSum","BoeSum",
                   "DocCurr","CashAcct"
            FROM TELCHI."ORCT"
            WHERE "DocDate" >= ? AND "DocDate" < ?''', WINDOW)

        # ---- journals + ALL lines for those payments (1:N preserved)
        jl = fetch(cur, '''
            SELECT J."TransId", J."Line_ID", J."Account", J."Debit", J."Credit",
                   J."ContraAct", J."BPLId", J."LineMemo"
            FROM TELCHI."JDT1" AS J
            WHERE J."TransId" IN (
                SELECT "TransId" FROM TELCHI."ORCT"
                WHERE "DocDate" >= ? AND "DocDate" < ?)''', WINDOW)
        lines_by_trans = defaultdict(list)
        for _, r in jl.iterrows():
            lines_by_trans[r["TransId"]].append(r.to_dict())

        # ---- account master subset actually used
        am = fetch(cur, '''
            SELECT "AcctCode","AcctName","CashBox","Postable"
            FROM TELCHI."OACT"
            WHERE "AcctCode" IN (SELECT DISTINCT "CashAcct" FROM TELCHI."ORCT"
                                 WHERE "DocDate" >= ? AND "DocDate" < ?)''', WINDOW)
        master = {r["AcctCode"]: r.to_dict() for _, r in am.iterrows()}
    finally:
        cur.close()
        conn.close()

    traces = []
    for _, p in pay.iterrows():
        tr = build_cash_accounting_trace(p.to_dict(),
                                         lines_by_trans.get(p["TransId"], []),
                                         master)
        traces.append(tr)

    status_dist = Counter(t["status"] for t in traces)
    cash_traces = [t for t in traces
                   if t["status"] not in ("NOT_APPLICABLE_TO_PHYSICAL_CASH",
                                          "CASH_CANCELED")]

    # ---- coverage metrics (§23): document-level, transactional primary proof
    exact = sum(1 for t in cash_traces if t["amount_delta"] == 0)
    tolerated = sum(1 for t in cash_traces if t["amount_delta"] is not None
                    and 0 < abs(t["amount_delta"]) <= 0.01)
    amount_mismatch = sum(1 for t in cash_traces if t["status"] == "CASH_AMOUNT_MISMATCH")
    acct_mismatch = sum(1 for t in cash_traces if t["status"] == "CASH_ACCOUNT_MISMATCH")
    journal_missing = sum(1 for t in traces if t["status"] == "CASH_JOURNAL_MISSING")

    # ---- cash accounts ranking (§24) from CONFIRMED traces only
    acct_rank = defaultdict(lambda: {"n": 0, "amount": 0.0})
    branch_rank = defaultdict(lambda: {"n": 0, "amount": 0.0, "class": None})
    confirmed_amount = 0.0
    for t in cash_traces:
        if t["status"] != "CASH_ACCOUNTING_CONFIRMED":
            continue
        confirmed_amount += float(t["instruments"]["cash"])
        key = t["cash_account_expected"]
        a = acct_rank[key]
        a["n"] += 1
        a["amount"] += float(t["instruments"]["cash"])
        a["name"] = t.get("acct_name")
        a["cashbox_flag"] = t.get("cashbox_flag")
        b, cls = branch_from_account_name(t.get("acct_name"))
        if b:
            br = branch_rank[b]
            br["n"] += 1
            br["amount"] += float(t["instruments"]["cash"])
            br["class"] = cls

    # ---- real positive examples (§30): A cash-only, B mixed, C partial
    def pick(pred):
        for t in traces:
            if pred(t):
                return t
        return None

    examples = {
        "A_cash_only": pick(lambda t: t["status"] == "CASH_ACCOUNTING_CONFIRMED"
                            and t["payment_method"] == "CASH"
                            and float(t["instruments"]["cash"]) > 1000),
        "B_mixed": pick(lambda t: "MIXED_PAYMENT_DECOMPOSED" in t["explanation"]),
        "C_partial": pick(lambda t: t["status"] == "CASH_ACCOUNTING_CONFIRMED"
                          and 0 < float(t["instruments"]["cash"]) < 10),
    }

    report = {
        "gate": "TELCHI_ATOMIC_CASH_ACCOUNTING_TRACEABILITY_H4_V1",
        "window": list(WINDOW),
        "hana_read_only": True,
        "payments_total": len(traces),
        "payments_canceled": status_dist.get("CASH_CANCELED", 0),
        "not_applicable_non_cash": status_dist.get("NOT_APPLICABLE_TO_PHYSICAL_CASH", 0),
        "cash_payments": len(cash_traces),
        "status_distribution": dict(status_dist),
        "coverage": {
            "journal_matched": len(cash_traces) - journal_missing - acct_mismatch,
            "journal_missing": journal_missing,
            "account_resolved": len(cash_traces) - acct_mismatch,
            "account_mismatch": acct_mismatch,
            "amount_exact": exact,
            "amount_tolerated": tolerated,
            "amount_mismatch": amount_mismatch,
            "unresolved": status_dist.get("CASH_ACCOUNT_UNRESOLVED", 0),
        },
        "amounts": {
            "cash_expected": round(sum(float(t["instruments"]["cash"]) for t in cash_traces), 2),
            "cash_accounting_confirmed": round(confirmed_amount, 2),
            "difference_unconfirmed": round(
                sum(float(t["instruments"]["cash"]) for t in cash_traces
                    if t["status"] != "CASH_ACCOUNTING_CONFIRMED"), 2),
        },
        "cash_account_ranking": dict(sorted(
            acct_rank.items(), key=lambda kv: kv[1]["amount"], reverse=True)),
        "branch_heuristic_ranking": dict(branch_rank),
        "examples_real": examples,
    }
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"H4 payments: {len(traces)} | cash: {len(cash_traces)}")
    print("status:", dict(status_dist))
    print("coverage:", report["coverage"])
    print("amounts:", report["amounts"])
    print("branch heuristic:", {k: v["n"] for k, v in branch_rank.items()})
    print("report:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())