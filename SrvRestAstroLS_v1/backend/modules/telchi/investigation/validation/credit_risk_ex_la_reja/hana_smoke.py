"""Real HANA smoke — TELCHI_CREDIT_RISK_EX_LA_REJA_V1.

Validates against live HANA (READ ONLY):
  * 5 LA REJA excluded cases (present in cleaned universe? -> must be ABSENT
    from EX; present in excluded)
  * 5 clean overdue cases (largest)
  * 5 clean USER FULL cases
  * 5 clean delivery cases
  * top 3 clean customers
Checks header amounts (DocTotal/PaidToDate) and open vs evidence.

Evidence counters printed; failures counted; exit nonzero on failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    clean = json.loads((EVIDENCE / "clean_cases_explained.json").read_text())
    excluded = json.loads((EVIDENCE / "excluded_la_reja_cases.json").read_text())
    conn, cur = connect()
    checks = 0
    failures = []

    def verify(name, ok, detail=""):
        nonlocal checks
        checks += 1
        print(f"  [{'OK' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            failures.append(f"{name}: {detail}")

    # 1. exclusion presence: 5 largest LA REJA ARE in excluded, NOT in clean
    lr_clean_ids = {r["docentry"] for r in clean if r["cardcode"] == "C010341"}
    verify("lr_absent_from_clean", len(lr_clean_ids) == 0, f"found {len(lr_clean_ids)}")
    lr_excl_ids = {r["docentry"] for r in excluded}
    top5_lr = sorted(excluded, key=lambda r: -float(r["open_amount"] or 0))[:5]
    for r in top5_lr:
        cur.execute('SELECT "DocTotal","PaidToDate","CardCode","CANCELED" FROM "TELCHI"."OINV" WHERE "DocEntry"=?',
                    (r["docentry"],))
        h = cur.fetchone()
        verify(f"excluded HANA {r['docentry']}",
               h is not None and h[2] == "C010341" and abs(float(h[0]) - float(r["open_amount"] or 0)) <= 0.02,
               f"db={h} expected={r['open_amount']}")

    # 2. clean overdue: 5 largest
    top_overdue = sorted(clean, key=lambda r: -float(r.get("overdue_amount") or 0))[:5]
    for r in top_overdue:
        od = float(r.get("overdue_amount") or 0)
        if od <= 0:
            continue
        cur.execute('SELECT "DocTotal","PaidToDate","CardCode","DocDueDate" FROM "TELCHI"."OINV" WHERE "DocEntry"=?',
                    (r["docentry"],))
        h = cur.fetchone()
        open_db = float(h[0]) - float(h[1]) if h else None
        verify(f"clean overdue {r['cardcode']} {r['docentry']}",
               h is not None and r["cardcode"] != "C010341" and open_db is not None
               and abs(open_db - od) <= 0.05,
               f"db_open={open_db} expected_od={od}")

    # 3. clean USER FULL overdue (9)
    full = [r for r in clean if r.get("primary_business_group") == "USER_AUTHORIZATION_FULL"
            and (r.get("overdue_amount") or 0) > 0.005]
    for r in full[:5]:
        cur.execute('SELECT "DocEntry" FROM "TELCHI"."OINV" WHERE "DocEntry"=?', (r["docentry"],))
        verify(f"USER FULL {r['cardcode']} {r['docentry']}", cur.fetchone() is not None)

    # 4. clean delivery overdue
    dly = [r for r in clean if r.get("classification") == "DELIVERY_FLOW_EXPLAINS_TIMING"
           and (r.get("overdue_amount") or 0) > 0.005]
    for r in dly[:5]:
        cur.execute('SELECT "DocEntry" FROM "TELCHI"."OINV" WHERE "DocEntry"=?', (r["docentry"],))
        verify(f"delivery {r['cardcode']} {r['docentry']}", cur.fetchone() is not None)

    # 5. top 3 customers live totals (window universe only: sum of clean cases)
    cust_rank = json.loads((EVIDENCE / "customer_ranking.json").read_text())["ranking"]
    clean_ids = {(r["cardcode"], r["docentry"]) for r in clean}
    for t in cust_rank[:3]:
        code = t["cardcode"]
        cur.execute('''SELECT "CardCode","CardName","Balance" FROM "TELCHI"."OCRD" WHERE "CardCode"=?''', (code,))
        m = cur.fetchone()
        verify(f"top customer {code} master", m is not None and m[0] == code, f"{m}")
        # sum of window-universe open for this customer from clean evidence
        exp_open = money(sum(float(r.get("open_amount") or 0) for r in clean
                             if r["cardcode"] == code))
        # compare against live DB: window-universe DocEntries only
        de_ids = tuple(r["docentry"] for r in clean if r["cardcode"] == code)
        if de_ids:
            ph = ",".join(["?"] * len(de_ids))
            cur.execute(f'''SELECT COUNT(*), ROUND(SUM("DocTotal"-"PaidToDate"),2) FROM "TELCHI"."OINV"
                WHERE "DocEntry" IN ({ph})''', de_ids)
            nca, oa = cur.fetchone()
            verify(f"top {code} window open == evidence open",
                   abs(float(oa or 0) - exp_open) <= 0.05,
                   f"db={oa} evidence={exp_open}")

    print(f"\nHANA SMOKE: {checks} checks, {len(failures)} failures")
    if failures:
        for f in failures:
            print("  FAIL:", f)
        sys.exit(1)
    conn.close()


if __name__ == "__main__":
    main()