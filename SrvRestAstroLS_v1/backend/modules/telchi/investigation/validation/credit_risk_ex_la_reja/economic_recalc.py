"""PHASE 3/4/10 — Economic + aging recalc for UNIVERSE_EX_LA_REJA.

Builds the clean analytical universe from the FROZEN enriched rows
(open_risk_cases.json = 268 explained with aging) minus C010341 (40),
plus the 19 UNRESOLVED (audited: C010341 count = 0 there).

Reconciles:
  gross / paid / credited / open / not_due / overdue
  ALL == LA_REJA + EX_LA_REJA   (per metric)
  OPEN_EX == NOT_DUE_EX + OVERDUE_EX
  aging buckets re-built for EX.

Outputs:
  economic_recalc.json
  aging_recalc.json
  clean_cases_explained.json      (228 rows, enriched)
  clean_cases_unresolved.json     (19 rows)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"
V = Path(__file__).parent.parent

AGING_BUCKETS = [
    ("NOT_YET_DUE", None, None),
    ("1-15", 1, 15),
    ("16-30", 16, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("91-180", 91, 180),
    ("181+", 181, 10**9),
]

CUTOFF = date(2026, 9, 1)


def money(v):
    return round(float(v or 0.0), 2)


def bucket_of(days) -> str:
    if days is None or days <= 0:
        return "NOT_YET_DUE"
    for name, lo, hi in AGING_BUCKETS:
        if name == "NOT_YET_DUE":
            continue
        if lo <= days <= hi:
            return name
    return "181+"


def main() -> None:
    enriched = json.loads((EVIDENCE_ROOT / "credit_open_risk" / "evidence" / "open_risk_cases.json").read_text())
    grouped = json.loads((EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "grouped_cases.json").read_text())
    univ_all = json.loads((EVIDENCE / "universe_all_cases.json").read_text())

    # default enriched fields for 268 explained; group fields for 228 clean
    grp_by_key = {(r["cardcode"], r["docentry"]): r for r in grouped}
    by_key = {(r["cardcode"], r["doc_entry"]): r for r in enriched}
    assert len(enriched) == 268 and len(grouped) == 268

    # --- split 287 into explained (with aging) and unresolved ---
    resolved_keys = set(by_key)
    unresolved = [r for r in univ_all
                  if (r["cardcode"], r["docentry"]) not in resolved_keys]
    assert len(unresolved) == 19, len(unresolved)
    assert sum(1 for r in unresolved if r["cardcode"] == "C010341") == 0, "C010341 in unresolved!"
    assert sum(1 for r in univ_all if (r["cardcode"], r["docentry"]) in resolved_keys) == 268

    clean_explained = []
    for r in enriched:
        if r["cardcode"] == "C010341":
            continue
        g = grp_by_key.get((r["cardcode"], r["docentry"]), {})
        clean_explained.append({
            **r,
            "gross_sales_amount": money(g.get("gross_sales_amount", r.get("gross_sales_amount"))),
            "paid_amount": money(g.get("paid_amount", r.get("paid_amount"))),
            "credited_amount": money(g.get("credited_amount", r.get("credited_amount"))),
            "open_amount": money(r.get("open_amount") or 0),
            "not_due_amount": money(r.get("not_due_amount") or 0),
            "overdue_amount": money(r.get("overdue_amount") or 0),
            "sap_user": r.get("sap_user"),
            "slpcode": r.get("slpcode"),
            "channel": r.get("channel"),
            "days_overdue": r.get("days_overdue"),
            "docdate": str(r.get("docdate"))[:10],
            "docduedate": str(r.get("due_date"))[:10],
        })
    assert len(clean_explained) == 228

    # --- aggregates ---
    def sum_metric(rows, key):
        return money(sum(float(r.get(key) or 0) for r in rows))

    # explained ALL (268) from enriched
    exp_all = enriched
    exp_lr = [r for r in enriched if r["cardcode"] == "C010341"]
    exp_ex = clean_explained

    metrics = ["gross_sales_amount", "paid_amount", "credited_amount", "open_amount",
               "not_due_amount", "overdue_amount"]
    rec = {}
    for m in metrics:
        rec[m] = {
            "ALL_268": money(sum(float(r.get(m) or 0) for r in exp_all)),
            "LA_REJA_40": money(sum(float(r.get(m) or 0) for r in exp_lr)),
            "EX_228": money(sum(float(r.get(m) or 0) for r in exp_ex)),
            "ok": abs(money(sum(float(r.get(m) or 0) for r in exp_all)) -
                    (money(sum(float(r.get(m) or 0) for r in exp_lr)) +
                     money(sum(float(r.get(m) or 0) for r in exp_ex)))) <= 0.05,
        }
        assert rec[m]["ok"], m

    # open == not_due + overdue (EX and ALL)
    open_ex = rec["open_amount"]["EX_228"]
    nd_ex = rec["not_due_amount"]["EX_228"]
    od_ex = rec["overdue_amount"]["EX_228"]
    assert abs(open_ex - (nd_ex + od_ex)) <= 0.05, (open_ex, nd_ex, od_ex)
    rec["open_split_ex"] = {"open": open_ex, "not_due": nd_ex, "overdue": od_ex,
                            "ok": abs(open_ex - (nd_ex + od_ex)) <= 0.05}

    # --- aging buckets EX (explained only) ---
    buckets = defaultdict(lambda: {"cases": 0, "customers": set(), "amount": 0.0})
    for r in clean_explained:
        od = float(r.get("overdue_amount") or 0)
        nd = float(r.get("not_due_amount") or 0)
        days = r.get("days_overdue")
        if od > 0.005:
            b = bucket_of(days)
            buckets[b]["cases"] += 1
            buckets[b]["customers"].add(r["cardcode"])
            buckets[b]["amount"] += od
        elif nd > 0.005:
            buckets["NOT_YET_DUE"]["cases"] += 1
            buckets["NOT_YET_DUE"]["customers"].add(r["cardcode"])
            buckets["NOT_YET_DUE"]["amount"] += nd
        else:
            buckets["NOT_YET_DUE"]["cases"] += 1  # fully paid/credited, zero open
            buckets["NOT_YET_DUE"]["amount"] += 0.0
    aging = []
    for name, lo, hi in AGING_BUCKETS:
        b = buckets[name]
        aging.append({
            "bucket": name,
            "cases": b["cases"],
            "customers": len(b["customers"]),
            "amount": money(b["amount"]),
        })
    sum_buckets = money(sum(b["amount"] for b in aging))
    rec["aging_ex"] = aging
    rec["aging_ex_sum"] = sum_buckets
    rec["aging_ex_component_ok"] = abs(sum_buckets - (nd_ex + od_ex)) <= 0.05 or \
        abs(sum_buckets - open_ex) <= 0.06

    # --- business groups EX ---
    grp = Counter(r["primary_business_group"] for r in clean_explained)
    grp_reason = Counter(r["classification"] for r in clean_explained)
    rec["business_groups_ex"] = dict(grp)
    rec["reason_ex"] = dict(grp_reason)
    rec["explained_ex"] = len(clean_explained)
    rec["unresolved_ex"] = len(unresolved)
    rec["unresolved_amount_open"] = money(sum(float(r.get("open_amount") or 0) for r in unresolved))
    rec["unresolved_customers"] = len({r["cardcode"] for r in unresolved})

    # --- unresolved detail (audit) ---
    unresolved_rows = [{
        "cardcode": r["cardcode"],
        "cardname": r.get("cardname"),
        "docentry": r["docentry"],
        "docnum": r.get("docnum"),
        "docdate": r.get("docdate"),
        "amount": money(r.get("amount")),
        "open_amount": money(r.get("open_amount")),
        "channel": None,
    } for r in unresolved]

    (EVIDENCE / "economic_recalc.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "aging_recalc.json").write_text(json.dumps(aging, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "clean_cases_explained.json").write_text(
        json.dumps(clean_explained, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "clean_cases_unresolved.json").write_text(
        json.dumps(unresolved_rows, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(rec, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()