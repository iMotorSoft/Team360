"""PHASE 1/2 — Exact exclusion of C010341 LA REJA from the credit universe.

Consumes ONLY frozen baselines (no re-derivation from scratch):
  * credit_control/evidence/phase78_sale_credit_state.json (prior 287)
  * credit_exception/evidence/classified_cases.json          (2,318 all; the 287
    subset is the analytical universe, 268 explained + 19 UNRESOLVED)
  * credit_exception_economic/evidence/grouped_cases.json    (268 explained, grouped)
  * credit_open_risk/evidence/open_risk_cases.json           (268 enriched, aging)
  * la_reja_identity/evidence/atomic_la_reja_cases.json      (40 LA REJA DocEntry)

Rule of exclusion (EXACT, reproducible):
    EXCLUDED_REASON = RELATED_PARTY_INTERNAL_ACCOUNT_C010341
    filter: CardCode == 'C010341'  (never by name/grupo/NIT/heuristic)

Outputs:
  excluded_la_reja_cases.json   (40 rows with reason_code + business_group)
  universe_all_cases.json       (287 rows: the analytical baseline)
  universe_ex_la_reja_cases.json(247 rows: 287 - 40)
  exclusion_reconciliation.json (counts + amounts: ALL == LR + EX)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

ROOT = HERE.parent.parent
VALIDATION = ROOT / "validation"
IN_CREDIT = EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json"
IN_CLASS = EVIDENCE_ROOT / "credit_exception" / "evidence" / "classified_cases.json"
IN_GROUP = EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "grouped_cases.json"
IN_AGING = EVIDENCE_ROOT / "credit_open_risk" / "evidence" / "open_risk_cases.json"
IN_LAREJA = EVIDENCE_ROOT / "la_reja_identity" / "evidence" / "atomic_la_reja_cases.json"

BP = "C010341"
EXCLUDED_REASON = "RELATED_PARTY_INTERNAL_ACCOUNT_C010341"


def money(v) -> float:
    return round(float(v or 0.0), 2)


def main() -> None:
    assert IN_CREDIT.exists(), IN_CREDIT
    assert IN_CLASS.exists() and IN_GROUP.exists() and IN_AGING.exists()
    assert IN_LAREJA.exists()

    prior = json.loads(IN_CREDIT.read_text())["all_overdue_sales"]   # 287
    classified = json.loads(IN_CLASS.read_text())                    # 2318
    grouped = json.loads(IN_GROUP.read_text())                       # 268 explained
    aging = json.loads(IN_AGING.read_text())                         # 268 enriched
    lareja_atomic = json.loads(IN_LAREJA.read_text())                # 40 LA REJA atomic

    # --- class maps ---
    cls_by_key = {(x["cardcode"], x["doc_entry"]): x for x in classified}
    grp_by_key = {(x["cardcode"], x["docentry"]): x for x in grouped}
    age_by_key = {(x["cardcode"], x["doc_entry"]): x for x in aging}

    # --- universe ALL = prior 287 (analytical baseline) ---
    all_cases = []
    for s in prior:
        key = (s["cardcode"], s["docentry"])
        cls = cls_by_key.get(key, {})
        row = {
            "cardcode": s["cardcode"],
            "cardname": s.get("cardname") or cls.get("cardname"),
            "docentry": s["docentry"],
            "docnum": s.get("docnum") or cls.get("docnum"),
            "docdate": str(s.get("docdate"))[:10],
            "docduedate": str(s.get("docduedate"))[:10],
            "amount": money(s.get("doctotal")),
            "open_amount": money(s.get("open_now")),
            "reason_code": cls.get("classification"),
            "confidence": cls.get("confidence"),
            "full_by": cls.get("sap_user"),
        }
        # enrich from grouped (business group + paid/credited) and aging (overdue)
        g = grp_by_key.get(key)
        if g:
            row.update({
                "primary_business_group": g.get("primary_business_group"),
                "gross_sales_amount": money(g.get("gross_sales_amount")),
                "paid_amount": money(g.get("paid_amount")),
                "credited_amount": money(g.get("credited_amount")),
                "open_group": money(g.get("open_amount")),
                "sap_user": g.get("sap_user"),
                "slpcode": g.get("slpcode"),
                "channel": g.get("channel"),
            })
        a = age_by_key.get(key)
        if a:
            row.update({
                "overdue_amount": money(a.get("overdue_amount_at_sale") or a.get("open_amount") if False else a.get("overdue_amount")),
                "days_overdue": a.get("days_overdue"),
                "not_due_amount": a.get("not_due_amount"),
            })
        all_cases.append(row)

    # --- LA REJA excluded set (40) via analytic keys, plus reason ---
    lr_keys = {(x["cardcode"], x["docentry"]) for x in all_cases if x["cardcode"] == BP}
    assert len(lr_keys) == 40, f"LA REJA in 287 != 40: {len(lr_keys)}"

    # also verify against the frozen 40 atomic DocEntrys
    atomic_keys = {x["invoice_docentry"] for x in lareja_atomic}
    lr_docentries = {d for (_, d) in lr_keys}
    assert lr_docentries == atomic_keys, (
        f"LA REJA docenty mismatch: analytic only {lr_docentries - atomic_keys}, "
        f"atomic only {atomic_keys - lr_docentries}")

    excluded = []
    for row in all_cases:
        if row["cardcode"] == BP:
            excluded.append({
                **row,
                "excluded_reason": EXCLUDED_REASON,
            })

    # --- EX universe = ALL - LA REJA ---
    ex = [row for row in all_cases if row["cardcode"] != BP]
    assert len(ex) == len(all_cases) - 40

    # --- reconciliation ---
    def agg(rows):
        def g(r):
            return r.get("gross_sales_amount") or r.get("amount") or 0.0
        return {
            "cases": len(rows),
            "gross": money(sum(float(g(r)) for r in rows)),
            "open": money(sum(float(r.get("open_group") or r.get("open_amount") or 0.0) for r in rows)),
            "overdue": money(sum(float(r.get("overdue_amount") or 0.0) for r in rows)),
            "reason": dict(Counter(r["reason_code"] for r in rows if r["reason_code"])),
            "group": dict(Counter(r["primary_business_group"] for r in rows
                                  if r.get("primary_business_group"))),
            "customers": len({r["cardcode"] for r in rows}),
        }

    all_agg = agg(all_cases)
    lr_agg = agg(excluded)
    ex_agg = agg(ex)

    # use open_amount from prior for those without grouped enrichment (19 UNRESOLVED)
    def open_sum(rows):
        return money(sum(
            r["open_group"] if r.get("open_group") is not None else r["open_amount"]
            for r in rows))

    reconciliation = {
        "all": {**all_agg, "open": open_sum(all_cases)},
        "la_reja": {**lr_agg, "open": open_sum(excluded)},
        "ex_la_reja": {**ex_agg, "open": open_sum(ex)},
        "count_check": all_agg["cases"] == lr_agg["cases"] + ex_agg["cases"],
        "gross_check": abs(all_agg["gross"] - lr_agg["gross"] - ex_agg["gross"]) <= 0.05,
        "open_check": abs(open_sum(all_cases) - open_sum(excluded) - open_sum(ex)) <= 0.05,
        "reason_row_check": all(
            all_agg["reason"].get(k, 0) == lr_agg["reason"].get(k, 0) + ex_agg["reason"].get(k, 0)
            for k in set(all_agg["reason"]) | set(lr_agg["reason"]) | set(ex_agg["reason"])),
        "excluded_bp_distinct": sorted({r["cardcode"] for r in excluded}),
        "no_leakage_cl_in_ex": sum(1 for r in ex if r["cardcode"] == BP),
        "sap_write_count": 0,
    }

    # persist
    def clean(rows):
        return [{k: v for k, v in r.items() if v is not None} for r in rows]

    (EVIDENCE / "excluded_la_reja_cases.json").write_text(
        json.dumps(clean(excluded), ensure_ascii=False, indent=1))
    (EVIDENCE / "universe_all_cases.json").write_text(
        json.dumps(clean(all_cases), ensure_ascii=False, indent=1))
    (EVIDENCE / "universe_ex_la_reja_cases.json").write_text(
        json.dumps(clean(ex), ensure_ascii=False, indent=1))
    (EVIDENCE / "exclusion_reconciliation.json").write_text(
        json.dumps(reconciliation, ensure_ascii=False, indent=1))

    print(json.dumps(reconciliation, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()