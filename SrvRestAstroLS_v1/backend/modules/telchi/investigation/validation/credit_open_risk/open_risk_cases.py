"""PHASE 1-10 — Open risk × aging over the 268 explained credit cases.

Consumes validation/credit_exception_economic/evidence/grouped_cases.json
(frozen at TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS) and
enriches each atomic case with due-date state as of a fixed cutoff.

CUTOFF (baseline) = 2026-09-01 (inclusive). Validated in this gate:
  * INV6 = 1 installment per invoice for all 162 open invoices (no
    multi-installment in this installation) -> single due date semantics.
  * The only settlement on/after cutoff is DocEntry 11500423 (Bs 748.30) on
    2026-09-01, already counted as paid in the frozen baseline, so
    OPEN(09-01) = Bs 252,973.00 EXACTLY equals the frozen gate amount.

State per case (payment/debt state):
  FULLY_PAID            open<=tol
  CREDITED              settled by credit note, open<=tol
  OPEN_NOT_DUE          open>tol and due_date >= cutoff
  OPEN_FULLY_OVERDUE    open>tol and due_date <  cutoff
  OPEN_PARTIALLY_OVERDUE (reserved; never occurs with single installment)

For each open case:
  overdue_amount = open amount whose due date is before cutoff
  not_due_amount = open amount still within term
  days_overdue   = (cutoff - due_date).days  (>0 only when overdue)

Aging buckets over overdue: 1-15 / 16-30 / 31-60 / 61-90 / 91-180 / 181+.
NOT_YET_DUE bucket over not-due.

Emitted:
  evidence/open_risk_cases.json      (268 enriched rows)
  evidence/open_risk_summary.json    (global + per-group splits)
  evidence/aging.json                (buckets global + per group)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_open_risk" / "evidence"
ROOT = HERE.parent

CUTOFF = date(2026, 9, 1)  # frozen baseline as-of

TOLERANCE = 0.05

GROUP_ORDER = [
    "USER_AUTHORIZATION_FULL",
    "CUSTOMER_EXCEPTION",
    "DOCUMENT_FLOW_PREAUTHORIZED",
    "NON_CREDIT_RETAIL_CASH",
    "TECHNICAL_RECONCILIATION",
]

AGING_BUCKETS = [
    ("NOT_YET_DUE", None, None),
    ("1-15", 1, 15),
    ("16-30", 16, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("91-180", 91, 180),
    ("181+", 181, 10**9),
]

RISK_CATEGORY = {
    "NO_CURRENT_RISK": lambda r: r["open_amount"] <= TOLERANCE,
    "OPEN_NOT_DUE": lambda r: r["open_amount"] > TOLERANCE and r["days_overdue"] <= 0,
    "OVERDUE_LOW_AGE": lambda r: 1 <= r["days_overdue"] <= 30,
    "OVERDUE_MEDIUM_AGE": lambda r: 31 <= r["days_overdue"] <= 90,
    "OVERDUE_HIGH_AGE": lambda r: r["days_overdue"] > 90,
}


def money(v) -> float:
    return round(float(v or 0.0), 2)


def to_date(s) -> date:
    return date.fromisoformat(str(s)[:10])


def load() -> list[dict]:
    rows = json.loads((EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "grouped_cases.json")
                      .read_text(encoding="utf-8"))
    assert len(rows) == 268
    return rows


def classify_open(r: dict) -> str:
    if r["open_amount"] <= TOLERANCE:
        return "CREDITED" if r["credited_amount"] > TOLERANCE else "FULLY_PAID"
    if to_date(r["due_date"]) < CUTOFF:
        return "OPEN_FULLY_OVERDUE"
    return "OPEN_NOT_DUE"


def risk_category(r: dict) -> str:
    for cat, pred in RISK_CATEGORY.items():
        if pred(r):
            return cat
    return "OVERDUE_HIGH_AGE"


def enrich(r: dict) -> dict:
    due = to_date(r["docduedate"])
    sale = to_date(r["docdate"])
    row = dict(r)
    row["due_date"] = str(due)
    row["cutoff_date"] = str(CUTOFF)
    row["days_to_due"] = (due - CUTOFF).days  # >0 not yet due
    row["days_overdue"] = (CUTOFF - due).days  # >0 overdue
    open_amt = r["open_amount"]
    if open_amt <= TOLERANCE:
        overdue_amt = 0.0
    elif due < CUTOFF:
        overdue_amt = open_amt
    else:
        overdue_amt = 0.0
    row["not_due_amount"] = money(open_amt - overdue_amt)
    row["overdue_amount"] = money(overdue_amt)
    row["open_state"] = classify_open(row)
    row["installment_count"] = 1  # validated INV6 1:1 for all open invoices
    row["payment_terms_days"] = (due - sale).days
    row["risk_category"] = risk_category(row)
    row["evidence"].append("due-date as-of 2026-09-01; INV6 single installment (validated)")
    return row


def main() -> int:
    rows = [enrich(r) for r in load()]

    # ---- global invariants ----
    total_open = money(sum(r["open_amount"] for r in rows))
    total_not_due = money(sum(r["not_due_amount"] for r in rows))
    total_overdue = money(sum(r["overdue_amount"] for r in rows))
    assert abs(total_open - (total_not_due + total_overdue)) <= 0.05
    assert total_open == 252973.00, total_open

    state_dist = Counter(r["open_state"] for r in rows)
    risk_dist = Counter(r["risk_category"] for r in rows)

    # ---- per group ----
    by_group = {}
    for g in GROUP_ORDER:
        gr = [r for r in rows if r["primary_business_group"] == g]
        open_rows = [r for r in gr if r["open_amount"] > TOLERANCE]
        by_group[g] = {
            "cases": len(gr),
            "open_cases": len(open_rows),
            "open_amount": money(sum(r["open_amount"] for r in open_rows)),
            "not_due_amount": money(sum(r["not_due_amount"] for r in open_rows)),
            "overdue_amount": money(sum(r["overdue_amount"] for r in open_rows)),
            "not_due_cases": sum(1 for r in open_rows if r["days_overdue"] <= 0),
            "overdue_cases": sum(1 for r in open_rows if r["days_overdue"] > 0),
            "customers": len({r["cardcode"] for r in open_rows}),
            "overdue_customers": len({r["cardcode"] for r in open_rows if r["days_overdue"] > 0}),
        }

    # ---- aging ----
    aging = {}
    for scope, group in [(("TOTAL",), None)] + [(("GROUP", g), g) for g in GROUP_ORDER]:
        key = scope[0] if group is None else f"GROUP:{group}"
        gr = rows if group is None else [r for r in rows if r["primary_business_group"] == group]
        buckets = []
        for label, lo, hi in AGING_BUCKETS:
            if label == "NOT_YET_DUE":
                sel = [r for r in gr if r["days_overdue"] <= 0 and r["open_amount"] > TOLERANCE]
            else:
                sel = [r for r in gr if lo <= r["days_overdue"] <= hi]
            buckets.append({
                "bucket": label,
                "case_count": len(sel),
                "customer_count": len({r["cardcode"] for r in sel}),
                "open_amount": money(sum(r["open_amount"] for r in sel)),
                "overdue_amount": money(sum(r["overdue_amount"] for r in sel)),
            })
        aging[key] = buckets

    # ---- open amount reconciliation ----
    reconciliation = {
        "baseline_open_frozen": 252973.00,
        "recomputed_open": total_open,
        "delta": round(total_open - 252973.00, 2),
        "not_due": total_not_due,
        "overdue": total_overdue,
        "not_due_plus_overdue": money(total_not_due + total_overdue),
        "invariant": abs(total_not_due + total_overdue - total_open) <= 0.05,
        "cutoff": str(CUTOFF),
        "semantics": "INV6 single installment (162/162 open invoices); DocDueDate effective due date",
        "settlement_on_cutoff": {"docentry": 11500423, "amount": 748.30,
                                 "note": "settled 2026-09-01; already counted as paid in frozen baseline"},
    }

    summary = {
        "cases": len(rows),
        "distinct_doc_entry": len({r["doc_entry"] for r in rows}),
        "cutoff": str(CUTOFF),
        "total_gross": money(sum(r["gross_sales_amount"] for r in rows)),
        "total_open": total_open,
        "total_not_due": total_not_due,
        "total_overdue": total_overdue,
        "open_share_of_gross": round(100.0 * total_open / sum(r["gross_sales_amount"] for r in rows), 2),
        "overdue_share_of_open": round(100.0 * total_overdue / total_open, 2),
        "not_due_share_of_open": round(100.0 * total_not_due / total_open, 2),
        "state_distribution": dict(state_dist),
        "risk_category_distribution": dict(risk_dist),
        "by_group": by_group,
        "reconciliation": reconciliation,
        "seconds": None,
    }

    (EVIDENCE / "open_risk_cases.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "open_risk_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "aging.json").write_text(
        json.dumps(aging, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps({
        "open": total_open, "not_due": total_not_due, "overdue": total_overdue,
        "overdue_share_of_open": summary["overdue_share_of_open"],
        "state": dict(state_dist),
        "by_group": {g: {k: v for k, v in d.items() if k != "customers"}
                     for g, d in by_group.items()},
        "aging_global": aging["TOTAL"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())