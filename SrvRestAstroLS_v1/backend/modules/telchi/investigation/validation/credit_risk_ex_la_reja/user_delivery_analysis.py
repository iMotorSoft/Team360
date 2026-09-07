"""PHASE 7/8/14/38 — Consolidated USER FULL + DELIVERY analysis for EX_LA_REJA.

Consumes the evidence produced by collection_kpi.py (user_full_detail_ex.json,
delivery_flow_ex.json) and emits a consolidated report object with:
  * USER FULL summary (cases, customers, overdue, users)
  * DELIVERY flow summary (cases, overdue, top overdue cases)
  * per-user overdue ranking (FULL)
  * per-delivery overdue detail
Reuses EXACT frozen mappings; never mixes SAP USER with OSLP SALESPERSON.
Outputs: user_delivery_summary.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    full = json.loads((EVIDENCE / "user_full_detail_ex.json").read_text())
    delivery = json.loads((EVIDENCE / "delivery_flow_ex.json").read_text())

    full_overdue = money(sum(r["overdue_amount"] for r in full))
    delivery_open = money(sum(r["open"] for r in delivery))
    delivery_overdue = money(sum(r["overdue"] for r in delivery))

    by_user = defaultdict(lambda: {"cases": 0, "customers": set(), "overdue": 0.0})
    for r in full:
        u = r["sap_user"]
        by_user[u]["cases"] += 1
        by_user[u]["customers"].add(r["customer"])
        by_user[u]["overdue"] += r["overdue_amount"]
    user_rows = [{"sap_user": u, "cases": v["cases"], "customers": len(v["customers"]),
                  "overdue": money(v["overdue"])} for u, v in by_user.items()]
    user_rows.sort(key=lambda r: -r["overdue"])

    by_cust_delivery = defaultdict(lambda: {"cases": 0, "overdue": 0.0})
    for r in delivery:
        c = by_cust_delivery[r["customer"]]
        c["cases"] += 1
        c["overdue"] += r["overdue"]
    dl_cust = [{"customer": k, "cases": v["cases"], "overdue": money(v["overdue"])}
               for k, v in by_cust_delivery.items()]
    dl_cust.sort(key=lambda r: -r["overdue"])

    out = {
        "user_full": {
            "overdue_cases": len(full),
            "overdue_amount": full_overdue,
            "by_user": user_rows,
        },
        "delivery_flow": {
            "open_cases": len(delivery),
            "open_amount": delivery_open,
            "overdue_amount": delivery_overdue,
            "overdue_customers": len([c for c in dl_cust if c["overdue"] > 0.005]),
            "by_customer": dl_cust[:15],
        },
        "invariant": "SAP USER != OSLP SALESPERSON (separados en dos rankings)",
        "sap_write_count": 0,
    }
    (EVIDENCE / "user_delivery_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()