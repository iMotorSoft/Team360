"""PHASE 28/29/30/31 — Repeat exposure and current-vs-mechanism risk.

Consumes evidence/open_risk_cases.json.

- Per customer: sale sequence over time; how many exception-sales happened
  while the customer still had open exposure from a prior exception-sale.
  Highlight customers with 2+/3+/5+ exception sales (REPEATED_CREDIT_EXPOSURE).
- Repeated FULL authorization: customers with 2+/3+/5+ FULL sales.
- Repeated delivery flow: customers with repeated delivery->invoice while open.
- Credit exposure context at sale for USER FULL + DELIVERY (overdue at sale,
  exposure before sale, credit limit).

Emitted:
  evidence/repeat_exposure.json
  evidence/executive_cases.json  (priority risk cases for the report)
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


def load() -> list[dict]:
    return json.loads((EVIDENCE / "open_risk_cases.json").read_text(encoding="utf-8"))


def main() -> int:
    rows = load()

    # ---- per-customer sequence (all 268)
    by_cust = defaultdict(list)
    for r in sorted(rows, key=lambda x: (x["cardcode"], x["docdate"], x["doc_entry"])):
        by_cust[r["cardcode"]].append(r)

    seq = []
    for cc, lst in by_cust.items():
        n = len(lst)
        # open exposure BEFORE each sale: sum of open_amount of previous sales in the sequence
        # (as-of the prior sale; approximation: use current open as the exposure persistent),
        # exact approach: track per-case open that remains open; we use open_amount>0 as
        # "still open today" — conservative proxy for "was open at time of next sale".
        open_prior = 0.0
        repeated_while_open = 0
        for i, r in enumerate(lst):
            seq.append({
                "cardcode": cc, "docentry": r["doc_entry"], "docnum": r["docnum"],
                "sale_date": r["docdate"][:10], "due_date": r["due_date"][:10],
                "amount": r["gross_sales_amount"], "open_now": r["open_amount"],
                "overdue_now": r["overdue_amount"],
                "business_group": r["primary_business_group"],
                "user": r["sap_user"], "salesperson": r["slpcode"], "channel": r["channel"],
                "open_exposure_before_sale": money(open_prior),
            })
            if open_prior > 0.05:
                repeated_while_open += 1
            open_prior += r["open_amount"]

    # customers with 2+/3+/5+ exception sales
    cust_counts = Counter(r["cardcode"] for r in rows)
    repeat_customers = sorted(
        ({"cardcode": cc, "exception_sales": n,
          "total_amount": money(sum(x["amount"] for x in seq if x["cardcode"] == cc)),
          "open_amount": money(sum(x["open_now"] for x in seq if x["cardcode"] == cc)),
          "overdue_amount": money(sum(x["overdue_now"] for x in seq if x["cardcode"] == cc)),
          "sales_while_open": sum(1 for x in seq if x["cardcode"] == cc and x["open_exposure_before_sale"] > 0.05),
          "first_case": min(x["sale_date"] for x in seq if x["cardcode"] == cc),
          "last_case": max(x["sale_date"] for x in seq if x["cardcode"] == cc),
          "groups": sorted({x["business_group"] for x in seq if x["cardcode"] == cc})}
         for cc, n in cust_counts.items() if n >= 2), key=lambda x: -x["exception_sales"])

    # repeated FULL (customer received 2+/3+/5+ FULL sales)
    full_by_cust = defaultdict(list)
    for r in rows:
        if r["primary_business_group"] == "USER_AUTHORIZATION_FULL":
            full_by_cust[r["cardcode"]].append(r)
    repeated_full = sorted(
        ({"cardcode": cc, "full_sales": len(lst),
          "users": sorted({x["sap_user"] for x in lst}),
          "amount": money(sum(x["gross_sales_amount"] for x in lst)),
          "open": money(sum(x["open_amount"] for x in lst)),
          "overdue": money(sum(x["overdue_amount"] for x in lst)),
          "period": [min(x["docdate"][:10] for x in lst), max(x["docdate"][:10] for x in lst)]}
         for cc, lst in full_by_cust.items() if len(lst) >= 2),
        key=lambda x: -x["full_sales"])

    # repeated delivery flow
    del_by_cust = defaultdict(list)
    for r in rows:
        if r["secondary_reason"] == "DELIVERY_PREVIOUS":
            del_by_cust[r["cardcode"]].append(r)
    repeated_delivery = sorted(
        ({"cardcode": cc, "delivery_sales": len(lst),
          "open": money(sum(x["open_amount"] for x in lst)),
          "overdue": money(sum(x["overdue_amount"] for x in lst)),
          "overdue_days_max": max(x["days_overdue"] for x in lst),
          "period": [min(x["docdate"][:10] for x in lst), max(x["docdate"][:10] for x in lst)]}
         for cc, lst in del_by_cust.items() if len(lst) >= 2),
        key=lambda x: -x["delivery_sales"])

    # ---- credit exposure context at sale (FULL + DELIVERY)
    exposure_ctx = {}
    for g in ("USER_AUTHORIZATION_FULL", "DOCUMENT_FLOW_PREAUTHORIZED"):
        gr = [r for r in rows if r["primary_business_group"] == g]
        per = [{
            "docentry": r["doc_entry"], "customer": r["cardcode"], "sale_date": r["docdate"][:10],
            "sale_amount": r["gross_sales_amount"], "open_now": r["open_amount"],
            "overdue_now": r["overdue_amount"],
            "overdue_amount_at_sale": money(r["overdue_amount_at_sale"]),
            "exposure_before_sale": money(r["exposure_before"]),
            "credit_limit": money(r["creditline"]),
            "over_limit_before": bool(r["over_limit_before"]),
            "user": r["sap_user"],
        } for r in gr]
        exposure_ctx[g] = {
            "cases": len(per),
            "with_overdue_at_sale": sum(1 for x in per if x["overdue_amount_at_sale"] > 0),
            "total_overdue_at_sale": money(sum(x["overdue_amount_at_sale"] for x in per)),
            "total_sale_amount": money(sum(x["sale_amount"] for x in per)),
            "total_open_now": money(sum(x["open_now"] for x in per)),
            "total_overdue_now": money(sum(x["overdue_now"] for x in per)),
            "detail_sorted_by_overdue_now": sorted(per, key=lambda x: -x["overdue_now"])[:15],
        }

    # ---- executive cases (max 15)
    candidates = []
    for r in rows:
        if r["overdue_amount"] <= 0.05:
            continue
        candidates.append({
            "cardcode": r["cardcode"], "cardname": r["cardname"],
            "docentry": r["doc_entry"], "docnum": r["docnum"],
            "sale_date": r["docdate"][:10], "due_date": r["due_date"][:10],
            "amount": r["gross_sales_amount"], "open_amount": r["open_amount"],
            "overdue_amount": r["overdue_amount"], "days_overdue": r["days_overdue"],
            "business_group": r["primary_business_group"],
            "secondary_reason": r["secondary_reason"],
            "user": r["sap_user"], "salesperson": r["slpcode"], "channel": r["channel"],
            "score_overdue": r["open_amount"] * r["days_overdue"],
        })
    candidates.sort(key=lambda x: -x["overdue_amount"])
    seen_docs = set()
    exec_cases = []
    for c in candidates:
        if c["docentry"] in seen_docs:
            continue
        seen_docs.add(c["docentry"])
        exec_cases.append(c)
        if len(exec_cases) == 15:
            break

    out = {
        "customer_sale_sequence": seq,
        "repeat_customers_2plus": repeat_customers,
        "repeat_customers_3plus": [c for c in repeat_customers if c["exception_sales"] >= 3],
        "repeat_customers_5plus": [c for c in repeat_customers if c["exception_sales"] >= 5],
        "repeated_full_authorization": repeated_full,
        "repeated_delivery_flow": repeated_delivery,
        "credit_exposure_context": exposure_ctx,
        "executive_cases": exec_cases,
        "anti_fanout": {
            "case_rows": len(rows), "sequence_rows": len(seq),
            "distinct_docentry": len({x["docentry"] for x in seq}),
            "no_silent_fanout": len(seq) == len(rows) == len({x["docentry"] for x in seq}),
        },
    }
    (EVIDENCE / "repeat_exposure.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "executive_cases.json").write_text(json.dumps(exec_cases, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps({
        "repeat_2plus_count": len(repeat_customers),
        "repeat_3plus_count": len([c for c in repeat_customers if c["exception_sales"] >= 3]),
        "repeat_5plus_count": len([c for c in repeat_customers if c["exception_sales"] >= 5]),
        "top_repeat": [{k: c[k] for k in ("cardcode", "exception_sales", "total_amount",
                                          "open_amount", "overdue_amount", "sales_while_open")}
                       for c in repeat_customers[:5]],
        "repeated_full": repeated_full[:5],
        "repeated_delivery": repeated_delivery[:5],
        "exposure_context": {g: {k: v for k, v in d.items() if k != "detail_sorted_by_overdue_now"}
                             for g, d in exposure_ctx.items()},
        "exec_cases_count": len(exec_cases),
        "top_exec": [{k: c[k] for k in ("cardname", "docentry", "docnum", "sale_date", "due_date",
                                        "amount", "open_amount", "overdue_amount", "days_overdue",
                                        "business_group", "user", "channel")} for c in exec_cases[:8]],
        "anti_fanout": out["anti_fanout"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())