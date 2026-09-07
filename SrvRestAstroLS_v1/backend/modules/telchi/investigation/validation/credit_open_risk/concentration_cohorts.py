"""PHASE 5/6/7/20-27 — Concentration and monthly cohorts of the open risk.

Consumes evidence/open_risk_cases.json.

- Top 10 customers by overdue amount (+ business group, oldest due, max days).
- Concentration economics (top 1%/5%/10% of overdue).
- User concentration for USER FULL (overdue).
- Salesperson concentration (open/overdue) separated from SAP users.
- Monthly origination cohorts: sale_amount / open / overdue / not_due / % overdue.
- Cohort maturity + corrected collection rate over matured receivables.

Emitted:
  evidence/concentration.json
  evidence/monthly_cohorts.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_open_risk" / "evidence"
CUTOFF = date(2026, 9, 1)


def money(v) -> float:
    return round(float(v or 0.0), 2)


def pct(v, d) -> float:
    return round(100.0 * v / d, 2) if d else 0.0


def load() -> list[dict]:
    return json.loads((EVIDENCE / "open_risk_cases.json").read_text(encoding="utf-8"))


def main() -> int:
    rows = load()
    names = json.loads((EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "name_maps.json")
                       .read_text(encoding="utf-8"))
    open_rows = [r for r in rows if r["open_amount"] > 0.05]

    # ---------------- customers by overdue
    by_cust = defaultdict(lambda: {"groups": set(), "cases": 0, "open": 0.0,
                                   "overdue": 0.0, "not_due": 0.0,
                                   "due_dates": [], "days_overdue": [],
                                   "users": set(), "channels": set()})
    for r in open_rows:
        c = by_cust[r["cardcode"]]
        c["groups"].add(r["primary_business_group"])
        c["cases"] += 1
        c["open"] += r["open_amount"]
        c["overdue"] += r["overdue_amount"]
        c["not_due"] += r["not_due_amount"]
        c["users"].add(r["sap_user"])
        c["channels"].add(r["channel"])
        if r["days_overdue"] > 0:
            c["days_overdue"].append(r["days_overdue"])
            c["due_dates"].append(r["due_date"][:10])
    customers = sorted(
        ({"cardcode": k, "cardname": next(r["cardname"] for r in open_rows if r["cardcode"] == k),
          "business_groups": sorted(v["groups"]), "case_count": v["cases"],
          "open_amount": money(v["open"]), "not_due_amount": money(v["not_due"]),
          "overdue_amount": money(v["overdue"]),
          "oldest_due_date": min(v["due_dates"]) if v["due_dates"] else None,
          "max_days_overdue": max(v["days_overdue"]) if v["days_overdue"] else None,
          "users": sorted(v["users"]), "channels": sorted(v["channels"])}
         for k, v in by_cust.items()), key=lambda x: -x["overdue_amount"])

    total_overdue = sum(r["overdue_amount"] for r in rows)
    overdue_customers = [c for c in customers if c["overdue_amount"] > 0]
    n_ov = len(overdue_customers)
    cum = 0
    concentration_tiers = {}
    for label, frac in [("top_1_pct", 0.01), ("top_5_pct", 0.05), ("top_10_pct", 0.10)]:
        k = max(1, round(frac * n_ov))
        top = overdue_customers[:k]
        amt = sum(c["overdue_amount"] for c in top)
        concentration_tiers[label] = {
            "customers": k, "share_of_overdue_customers": round(100.0 * k / n_ov, 2),
            "overdue_amount": money(amt), "share_of_total_overdue": pct(amt, total_overdue)}

    # ---------------- user concentration (USER FULL)
    full_rows = [r for r in open_rows if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"]
    full_total_overdue = sum(r["overdue_amount"] for r in full_rows)
    by_user = defaultdict(lambda: {"customers": set(), "cases": 0, "open": 0.0, "overdue": 0.0})
    for r in full_rows:
        u = by_user[r["sap_user"]]
        u["customers"].add(r["cardcode"])
        u["cases"] += 1
        u["open"] += r["open_amount"]
        u["overdue"] += r["overdue_amount"]
    user_conc = sorted(
        ({"user": k, "customers": len(v["customers"]), "cases": v["cases"],
          "open": money(v["open"]), "overdue": money(v["overdue"]),
          "pct_of_full_overdue": pct(v["overdue"], full_total_overdue)}
         for k, v in by_user.items()), key=lambda x: -x["overdue"])

    # ---------------- salespersons (OSLP), open+overdue
    by_slp = defaultdict(lambda: {"customers": set(), "cases": 0, "open": 0.0, "overdue": 0.0,
                                  "channels": set()})
    for r in open_rows:
        s = by_slp[r["slpcode"]]
        s["customers"].add(r["cardcode"])
        s["cases"] += 1
        s["open"] += r["open_amount"]
        s["overdue"] += r["overdue_amount"]
        s["channels"].add(r["channel"])
    slp_conc = sorted(
        ({"slpcode": k, "slpname": names["salespersons"].get(str(k)) or f"slp {k}",
          "customers": len(v["customers"]), "cases": v["cases"],
          "open": money(v["open"]), "overdue": money(v["overdue"]),
          "channels": sorted(v["channels"])}
         for k, v in by_slp.items() if v["overdue"] > 0), key=lambda x: -x["overdue"])

    # ---------------- monthly cohorts
    by_month = defaultdict(lambda: {"sale_amount": 0.0, "cases": 0, "open": 0.0,
                                    "not_due": 0.0, "overdue": 0.0, "customers": set()})
    for r in rows:
        m = r["docdate"][:7]
        b = by_month[m]
        b["sale_amount"] += r["gross_sales_amount"]
        b["cases"] += 1
        b["open"] += r["open_amount"]
        b["not_due"] += r["not_due_amount"]
        b["overdue"] += r["overdue_amount"]
        b["customers"].add(r["cardcode"])
    cohorts = [{
        "month": m, "cases": b["cases"], "sale_amount": money(b["sale_amount"]),
        "open_amount": money(b["open"]), "not_due_amount": money(b["not_due"]),
        "overdue_amount": money(b["overdue"]),
        "pct_of_month_open_overdue": pct(b["overdue"], b["open"]) if b["open"] else 0.0,
        "matured_cases": sum(1 for r in rows if r["docdate"][:7] == m and
                             date.fromisoformat(r["due_date"][:10]) < CUTOFF),
    } for m, b in sorted(by_month.items())]

    # ---------------- corrected collection rate over matured receivables
    # matured = gross of sales whose due date < cutoff (they had the chance to be collected)
    total_matured_gross = sum(r["gross_sales_amount"] for r in rows
                              if date.fromisoformat(r["due_date"][:10]) < CUTOFF)
    matured_paid = sum(r["paid_amount"] for r in rows
                       if date.fromisoformat(r["due_date"][:10]) < CUTOFF)
    matured_open = sum(r["open_amount"] for r in rows
                       if date.fromisoformat(r["due_date"][:10]) < CUTOFF)
    collection = {
        "overall_paid_over_gross": pct(sum(r["paid_amount"] for r in rows),
                                       sum(r["gross_sales_amount"] for r in rows)),
        "matured_gross": money(total_matured_gross),
        "matured_paid": money(matured_paid),
        "matured_open": money(matured_open),
        "collection_rate_matured": pct(matured_paid, total_matured_gross),
        "matured_overdue_share_of_open": pct(sum(r["overdue_amount"] for r in rows if
                                                 date.fromisoformat(r["due_date"][:10]) < CUTOFF),
                                             matured_open),
    }

    out = {
        "top_customers_by_overdue": customers[:10],
        "top_customers_by_open": sorted(customers, key=lambda x: -x["open_amount"])[:10],
        "concentration_tiers": concentration_tiers,
        "overdue_customers_count": n_ov,
        "total_overdue": money(total_overdue),
        "user_concentration_full": user_conc,
        "full_overdue_total": money(full_total_overdue),
        "salesperson_concentration": slp_conc,
        "monthly_cohorts": cohorts,
        "collection_rate": collection,
        "global_monthly_summary": None,
    }
    (EVIDENCE / "concentration.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "monthly_cohorts.json").write_text(json.dumps(cohorts, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps({
        "top_customers_by_overdue": [{k: c[k] for k in ("cardcode", "cardname", "case_count",
                                                        "overdue_amount", "max_days_overdue",
                                                        "business_groups")} for c in customers[:8]],
        "concentration_tiers": concentration_tiers,
        "user_concentration_full": user_conc,
        "salesperson_conc_top": [{k: s[k] for k in ("slpname", "cases", "open", "overdue", "customers")}
                                 for s in slp_conc[:6]],
        "monthly_cohorts": cohorts,
        "collection_rate": collection,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())