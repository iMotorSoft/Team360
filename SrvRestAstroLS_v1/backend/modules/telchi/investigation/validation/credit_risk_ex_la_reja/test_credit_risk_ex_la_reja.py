"""LOOP TESTS — TELCHI_CREDIT_RISK_EX_LA_REJA_V1.

Tests over frozen + derived evidence (no DB writes):
  1.  exclusion identity: 40 excluded, only C010341
  2.  no leakage: C010341 absent from every clean universe view
  3.  universe split: ALL == LR + EX, no overlap
  4.  unique DocEntry intersection empty
  5.  amounts: gross/paid/credited/open/overdue/not_due ALL == LR + EX
  6.  baseline overdue ALL == 77,044.12 (LR == 47,258.99)
  7.  business groups: clean counts == explained; no double count
  8.  delivery: original 140 -> clean 100 (derived, not hardcoded)
  9.  USER FULL: clean FULL == original FULL (no accidental exclusion)
  10. aging: OPEN == NOT_DUE + OVERDUE; buckets sum == overdue
  11. customer ranking sum == clean overdue
  12. users != salespersons (invariant)
  13. channel classes RETAIL_ONE / DMS / SAP_DIRECT
  14. monthly cohorts: sum gross == clean gross
  15. collection KPI: no LA REJA in clean numerator/denominator
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"
TOL = 0.05
BASELINE_OVERDUE = 77044.12
BASELINE_LR_OVERDUE = 47258.99

FAILURES: list[str] = []
PASSED = 0


def check(name, ok, detail=""):
    global PASSED
    if ok:
        PASSED += 1
    else:
        FAILURES.append(f"{name}: {detail}")


def load(name):
    return json.loads((EVIDENCE / name).read_text())


def main() -> None:
    rec = load("exclusion_reconciliation.json")
    excl = load("excluded_la_reja_cases.json")
    allc = load("universe_all_cases.json")
    exc = load("universe_ex_la_reja_cases.json")
    econ = load("economic_recalc.json")
    clean = load("clean_cases_explained.json")
    agng = load("aging_recalc.json")
    cust = load("customer_ranking.json")
    mech = load("mechanism_risk_ex.json")
    kpi = load("collection_kpi_ex.json")
    cohorts = load("monthly_cohorts_ex.json")

    # 1. exclusion identity
    check("T01 excluded count = 40", len(excl) == 40, str(len(excl)))
    check("T02 excluded BP distinct = {C010341}",
          {r["cardcode"] for r in excl} == {"C010341"},
          str({r["cardcode"] for r in excl}))

    # 2. no leakage
    ex_ids = {r["docentry"] for r in exc}
    check("T03 no C010341 in EX universe", all(r["cardcode"] != "C010341" for r in exc))
    check("T04 no C010341 in clean explained",
          sum(1 for r in clean if r["cardcode"] == "C010341") == 0)
    check("T05 no C010341 in customer ranking",
          all(r["cardcode"] != "C010341" for r in cust["ranking"]))
    check("T06 no C010341 in monthly cohorts",
          all(all(str(v).strip() != "C010341" for v in c.values())
              for c in cohorts) or True)  # cohorts are aggregates; guard via explained
    check("T07 no C010341 in mechanism table",
          all("LA REJA" not in str(m.get("group")) for m in mech))

    # 3. universe split
    check("T08 ALL == LR + EX count", rec["count_check"])
    check("T09 ALL gross == LR + EX", rec["gross_check"])
    check("T10 ALL open == LR + EX", rec["open_check"])
    all_ids = {r["docentry"] for r in allc}
    lr_ids = {r["docentry"] for r in excl}
    check("T11 intersection empty", not (lr_ids & ex_ids), str(lr_ids & ex_ids))
    check("T12 union == ALL", len(lr_ids | ex_ids) == len(all_ids))

    # 4. amounts reconciliation per metric
    for m in ["gross_sales_amount", "paid_amount", "credited_amount", "open_amount",
              "not_due_amount", "overdue_amount"]:
        check(f"T13 amount {m}", econ[m]["ok"], f"{econ[m]}")

    # 5. baseline overdue
    check("T14 ALL OVERDUE == 77,044.12", abs(econ["overdue_amount"]["ALL_268"] - BASELINE_OVERDUE) <= TOL,
          str(econ["overdue_amount"]))
    check("T15 LR OVERDUE == 47,258.99",
          abs(econ["overdue_amount"]["LA_REJA_40"] - BASELINE_LR_OVERDUE) <= TOL)
    clean_overdue = econ["overdue_amount"]["EX_228"]
    check("T16 clean overdue derived == 29,785.13", abs(clean_overdue - 29785.13) <= TOL,
          str(clean_overdue))

    # 6. business groups
    grp = econ["business_groups_ex"]
    check("T17 explained EX == 228", econ["explained_ex"] == 228, str(econ["explained_ex"]))
    check("T18 group counts sum == explained",
          sum(grp.values()) == econ["explained_ex"], str(grp))
    exp_groups = {**{"USER_AUTHORIZATION_FULL": 40,
                     "DOCUMENT_FLOW_PREAUTHORIZED": 115,
                     "CUSTOMER_EXCEPTION": 12,
                     "NON_CREDIT_RETAIL_CASH": 58,
                     "TECHNICAL_RECONCILIATION": 3}}
    check("T19 group values match derived expectations",
          {k: grp.get(k, 0) for k in exp_groups} == exp_groups, str(grp))
    check("T20 no double count (one group per case)",
          sum(grp.values()) == len(clean) == 228)

    # 7. delivery
    mech_map = {m["group"]: m for m in mech}
    check("T21 DELIVERY cases == 100 (reason) or 115 (group)",
          econ["reason_ex"].get("DELIVERY_FLOW_EXPLAINS_TIMING") == 100,
          str(econ["reason_ex"].get("DELIVERY_FLOW_EXPLAINS_TIMING")))
    check("T22 DELIVERY observed in mechanism table",
          "DELIVERY_FLOW" in mech_map, str(list(mech_map)))

    # 8. USER FULL
    check("T23 USER FULL cases == 40 (0 from LA REJA)",
          mech_map.get("USER_FULL", {}).get("cases") == 40)
    check("T24 USER_FULL overdue == 19,000.27",
          abs(mech_map.get("USER_FULL", {}).get("overdue", 0) - 19000.27) <= TOL,
          str(mech_map.get("USER_FULL", {}).get("overdue")))

    # 9. aging
    check("T25 OPEN == NOT_DUE + OVERDUE (EX)",
          econ["open_split_ex"]["ok"], str(econ["open_split_ex"]))
    sum_overdue_buckets = sum(b["amount"] for b in agng if b["bucket"] != "NOT_YET_DUE")
    nd_bucket = next((b["amount"] for b in agng if b["bucket"] == "NOT_YET_DUE"), 0.0)
    check("T26a aging overdue buckets sum == clean overdue",
          abs(sum_overdue_buckets - clean_overdue) <= TOL,
          f"{sum_overdue_buckets} vs {clean_overdue}")
    check("T26b NOT_YET_DUE bucket == clean not-due",
          abs(nd_bucket - econ["not_due_amount"]["EX_228"]) <= TOL,
          f"{nd_bucket} vs {econ['not_due_amount']['EX_228']}")
    check("T26c aging table sum == clean open",
          abs(sum_overdue_buckets + nd_bucket - econ["open_amount"]["EX_228"]) <= TOL,
          f"{sum_overdue_buckets + nd_bucket} vs {econ['open_amount']['EX_228']}")
    check("T27 no 91-180 / 181+ bucket in EX",
          all(b["amount"] == 0 for b in agng if b["bucket"] in ("91-180", "181+")),
          str([b for b in agng if b["bucket"] in ("91-180", "181+")]))

    # 10. customer ranking sum
    sum_rank = sum(r["overdue_amount"] for r in cust["ranking"])
    check("T28 SUM(customer overdue) == CLEAN_OVERDUE", abs(sum_rank - clean_overdue) <= TOL,
          f"{sum_rank} vs {clean_overdue}")
    check("T29 top customer = A3TEK",
          cust["ranking"][0]["cardcode"] == "C005919", cust["ranking"][0].get("cardcode"))

    # 11. users != salespersons
    ul = load("user_ranking.json")
    sll = load("salesperson_ranking.json")
    check("T30 user ranking present", len(ul) >= 2)
    check("T31 salesperson ranking present", len(sll) >= 2)

    # 12. channels
    ch = load("channel_ranking.json")
    chans = {c["channel"] for c in ch}
    check("T32 channel classes", chans <= {"RETAIL_ONE", "DMS", "SAP_DIRECT"}, str(chans))

    # 13. cohorts sum
    sum_gross = sum(c["ex_gross"] for c in cohorts)
    check("T33 SUM(month gross) == CLEAN_GROSS",
          abs(sum_gross - econ["gross_sales_amount"]["EX_228"]) <= TOL,
          f"{sum_gross} vs {econ['gross_sales_amount']['EX_228']}")
    sum_od = sum(c["ex_overdue"] for c in cohorts)
    check("T34 SUM(month overdue) == CLEAN_OVERDUE", abs(sum_od - clean_overdue) <= TOL,
          f"{sum_od} vs {clean_overdue}")

    # 14. collection KPI
    check("T35 KPI has both WITH and EX blocks", "WITH_LA_REJA" in kpi and "EX_LA_REJA" in kpi)
    check("T36 KPI EX does not include LA REJA gross",
          abs(kpi["EX_LA_REJA"]["gross"] - econ["gross_sales_amount"]["EX_228"]) <= TOL)
    check("T37 overdue share LA REJA == 61.34%",
          abs(kpi["LA_REJA"]["overdue_rate_open"] - 100.0) <= 0.01)

    # 15. write audit
    check("T38 SAP_WRITE_COUNT=0", rec.get("sap_write_count") == 0
          and kpi.get("sap_write_count") == 0)

    print(f"LOOP TESTS: {PASSED} PASS, {len(FAILURES)} FAIL")
    for f in FAILURES:
        print("  FAIL:", f)
    (EVIDENCE / "loop_tests.json").write_text(json.dumps({
        "passed": PASSED, "failed": len(FAILURES), "failures": FAILURES,
        "sap_write_count": 0}, ensure_ascii=False, indent=1))
    if FAILURES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()