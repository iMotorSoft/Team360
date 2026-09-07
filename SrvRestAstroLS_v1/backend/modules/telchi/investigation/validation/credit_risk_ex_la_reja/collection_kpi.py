"""PHASE 9/12/14/17/43/44 — Collection KPIs + mechanism splits for EX_LA_REJA.

Collection KPIs recomputed WITHOUT LA REJA:
  RAW_COLLECTION_RATE = paid / gross
  MATURED_COLLECTION_RATE = paid / (gross - newest-cohort gross)
  OPEN_RATE = open / gross
  OVERDUE_RATE = overdue / open  (and overdue/gross)

Matured definition reused from the open-risk gate: mature cohorts = excludes
the most recent month (2026-08) from gross baseline.

Mechanism table (PHASE 33):
  USER_FULL / DOCUMENT_FLOW / CUSTOMER_EXCEPTION / RETAIL_CASH / TECHNICAL
  -> cases, gross, open, overdue, % of clean overdue

For USER FULL also emits the aging detail (PHASE 38).

Outputs:
  collection_kpi_ex.json
  mechanism_risk_ex.json
  user_full_detail_ex.json
  delivery_flow_ex.json
  before_after_comparison.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"
V = Path(__file__).parent.parent

AGING_BUCKETS = ["NOT_YET_DUE", "1-15", "16-30", "31-60", "61-90", "91-180", "181+"]


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    clean = json.loads((EVIDENCE / "clean_cases_explained.json").read_text())
    prev_kpi = json.loads((EVIDENCE_ROOT / "credit_open_risk" / "evidence" / "concentration.json").read_text())
    prev_rate = prev_kpi.get("collection_rate", {})
    cohorts_prev = json.loads((EVIDENCE_ROOT / "credit_open_risk" / "evidence" / "monthly_cohorts.json").read_text())

    def sums(rows, key):
        return money(sum(float(r.get(key) or 0) for r in rows))

    gross = sums(clean, "gross_sales_amount")
    paid = sums(clean, "paid_amount")
    credited = sums(clean, "credited_amount")
    open_amt = sums(clean, "open_amount")
    not_due = sums(clean, "not_due_amount")
    overdue = sums(clean, "overdue_amount")

    # matured collection: exclude most recent month cohort (2026-08) from gross
    mature_gross = 0.0
    mature_paid = 0.0
    latest_month = max(str(r.get("docdate"))[:7] for r in clean)
    for r in clean:
        m = str(r.get("docdate"))[:7]
        if m != latest_month:
            mature_gross += float(r.get("gross_sales_amount") or 0)
            mature_paid += float(r.get("paid_amount") or 0)
    latest_gross = gross - money(mature_gross)

    lr_gross = 47258.99
    lr_paid = 0.0
    lr_open = 47258.99
    lr_overdue = 47258.99
    all_gross = gross + lr_gross
    all_paid = paid + lr_paid
    all_open = open_amt + lr_open
    all_overdue = overdue + lr_overdue
    all_mature_gross = money(mature_gross) + lr_gross

    kpi = {
        "WITH_LA_REJA": {
            "gross": money(all_gross),
            "paid": money(all_paid),
            "open": money(all_open),
            "overdue": money(all_overdue),
            "raw_collection_rate": round(100 * all_paid / all_gross, 2) if all_gross else 0,
            "matured_collection_rate": round(100 * all_paid / all_mature_gross, 2) if all_mature_gross else 0,
            "open_rate": round(100 * all_open / all_gross, 2) if all_gross else 0,
            "overdue_rate_open": round(100 * all_overdue / all_open, 2) if all_open else 0,
            "overdue_rate_gross": round(100 * all_overdue / all_gross, 2) if all_gross else 0,
        },
        "EX_LA_REJA": {
            "gross": gross,
            "paid": paid,
            "credited": credited,
            "open": open_amt,
            "not_due": not_due,
            "overdue": overdue,
            "raw_collection_rate": round(100 * paid / gross, 2) if gross else 0,
            "matured_collection_rate": round(100 * mature_paid / mature_gross, 2) if mature_gross else 0,
            "mature_gross": money(mature_gross),
            "mature_paid": money(mature_paid),
            "latest_month": latest_month,
            "open_rate": round(100 * open_amt / gross, 2) if gross else 0,
            "overdue_rate_open": round(100 * overdue / open_amt, 2) if open_amt else 0,
            "overdue_rate_gross": round(100 * overdue / gross, 2) if gross else 0,
        },
        "LA_REJA": {
            "gross": lr_gross, "paid": lr_paid, "open": lr_open, "overdue": lr_overdue,
            "raw_collection_rate": 0.0, "open_rate": 100.0, "overdue_rate_open": 100.0,
        },
        "sap_write_count": 0,
    }

    # ---- mechanism split (PHASE 33) ----
    GROUP_LABEL = {
        "USER_AUTHORIZATION_FULL": "USER_FULL",
        "DOCUMENT_FLOW_PREAUTHORIZED": "DELIVERY_FLOW",
        "CUSTOMER_EXCEPTION": "CUSTOMER_EXCEPTION",
        "NON_CREDIT_RETAIL_CASH": "RETAIL_CASH",
        "TECHNICAL_RECONCILIATION": "TECHNICAL",
    }
    by_grp = defaultdict(list)
    for r in clean:
        g = r.get("primary_business_group") or "UNKNOWN"
        by_grp[g].append(r)

    mechanism = []
    for g, rows in by_grp.items():
        gs = sums(rows, "gross_sales_amount")
        op = sums(rows, "open_amount")
        nd = sums(rows, "not_due_amount")
        od = sums(rows, "overdue_amount")
        mechanism.append({
            "group": GROUP_LABEL.get(g, g),
            "cases": len(rows),
            "customers": len({r["cardcode"] for r in rows}),
            "gross": gs, "open": op, "not_due": nd, "overdue": od,
            "pct_of_clean_overdue": round(100 * od / overdue, 2) if overdue else 0,
        })
    mechanism.append({
        "group": "TOTAL",
        "cases": len(clean),
        "customers": len({r["cardcode"] for r in clean}),
        "gross": gross, "open": open_amt, "not_due": not_due, "overdue": overdue,
        "pct_of_clean_overdue": 100.0,
    })
    # sanity: OPEN == NOT_DUE + OVERDUE per group
    for m in mechanism:
        m["open_split_ok"] = abs(m["open"] - (m["not_due"] + m["overdue"])) <= 0.05
    mechanism.sort(key=lambda m: -m["overdue"])

    # ---- USER FULL aging detail (PHASE 38) ----
    user_full = [r for r in clean if r.get("primary_business_group") == "USER_AUTHORIZATION_FULL"]
    user_full_detail = sorted(
        [{
            "sap_user": r.get("sap_user"),
            "customer": r["cardcode"],
            "cardname": r.get("cardname"),
            "docentry": r["docentry"],
            "docnum": r.get("docnum"),
            "due_date": str(r.get("due_date"))[:10],
            "days_overdue": r.get("days_overdue"),
            "overdue_amount": money(r.get("overdue_amount")),
            "open_amount": money(r.get("open_amount")),
            "channel": r.get("channel"),
        } for r in user_full if (r.get("overdue_amount") or 0) > 0.005],
        key=lambda r: -r["overdue_amount"])

    # ---- DELIVERY FLOW detail (PHASE 8/26/27/28) ----
    delivery = [r for r in clean if r.get("classification") == "DELIVERY_FLOW_EXPLAINS_TIMING"]
    delivery_rows = sorted(
        [{
            "docentry": r["docentry"], "customer": r["cardcode"], "cardname": r.get("cardname"),
            "docdate": str(r.get("docdate"))[:10],
            "gross": money(r.get("gross_sales_amount")),
            "open": money(r.get("open_amount")),
            "overdue": money(r.get("overdue_amount")),
            "not_due": money(r.get("not_due_amount")),
            "days_overdue": r.get("days_overdue"),
            "sap_user": r.get("sap_user"), "channel": r.get("channel"),
        } for r in delivery if (r.get("open_amount") or 0) > 0.005],
        key=lambda r: -r["overdue"])

    # ---- before/after executive table (PHASE 18) ----
    before_after = {
        "metrics": [
            {"metric": "Casos (ventas)", "with_lr": 287, "ex_lr": 247, "delta": -40},
            {"metric": "Monto bruto (268 explicadas)", "with_lr": 318051.61, "ex_lr": gross,
             "delta": round(gross - 318051.61, 2)},
            {"metric": "Abierto", "with_lr": 252973.00, "ex_lr": open_amt,
             "delta": round(open_amt - 252973.00, 2)},
            {"metric": "Vencido", "with_lr": 77044.12, "ex_lr": overdue,
             "delta": round(overdue - 77044.12, 2)},
            {"metric": "No vencido", "with_lr": 175928.88, "ex_lr": not_due,
             "delta": round(not_due - 175928.88, 2)},
            {"metric": "Clientes con vencido", "with_lr": 20, "ex_lr":
             len({r["cardcode"] for r in clean if (r.get("overdue_amount") or 0) > 0.005}),
             "delta": 0},
        ],
        "top1_concentration": "61.3% (LA REJA) -> 39.59% (A3TEK)",
        "overdue_share_la_reja": round(100 * 47258.99 / 77044.12, 2),
    }

    # ---- collections with/without (comparison) ----
    (EVIDENCE / "collection_kpi_ex.json").write_text(json.dumps(kpi, ensure_ascii=False, indent=1))
    (EVIDENCE / "mechanism_risk_ex.json").write_text(json.dumps(mechanism, ensure_ascii=False, indent=1))
    (EVIDENCE / "user_full_detail_ex.json").write_text(json.dumps(user_full_detail, ensure_ascii=False, indent=1))
    (EVIDENCE / "delivery_flow_ex.json").write_text(json.dumps(delivery_rows, ensure_ascii=False, indent=1))
    (EVIDENCE / "before_after_comparison.json").write_text(json.dumps(before_after, ensure_ascii=False, indent=1))

    print(json.dumps({"kpi": kpi, "mechanism": mechanism, "before_after": before_after,
                      "user_full_overdue_cases": len(user_full_detail),
                      "delivery_open_cases": len(delivery_rows)},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()