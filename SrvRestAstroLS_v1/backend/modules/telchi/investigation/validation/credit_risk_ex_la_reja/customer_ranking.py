"""PHASE 6/13/15/16/34/35/37 — Customer/user/salesperson/channel/cohort rankings
for UNIVERSE_EX_LA_REJA (READ ONLY, derived from frozen evidence).

  * Top 20 customers by overdue_amount EX (with business group, channel,
    sap_user, salesperson, oldest due, max days overdue)
  * new TOP_OVERDUE_CUSTOMER_EX_LA_REJA candidate
  * concentration Top 1/5/10 % over OVERDUE_EX
  * SAP user ranking over overdue EX
  * salesperson ranking over overdue EX (never mixed with user)
  * channel ranking
  * monthly cohorts EX (comparison WITH / WITHOUT LA REJA)
  * repeated exposure (2+/3+/5+ while open)

Outputs:
  customer_ranking.json
  new_top_customer.json
  user_ranking.json
  salesperson_ranking.json
  channel_ranking.json
  monthly_cohorts_ex.json
  repeat_exposure_ex.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_risk_ex_la_reja" / "evidence"
CUTOFF = date(2026, 9, 1)


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    clean = json.loads((EVIDENCE / "clean_cases_explained.json").read_text())
    # salesperson mapping (frozen name map)
    names = json.loads((Path(__file__).parent.parent / "credit_exception_economic" /
                        "evidence" / "name_maps.json").read_text())
    slp_names = names.get("salespersons", {}) if isinstance(names, dict) else {}
    # ensure string keys
    slp_names = {str(k): v for k, v in slp_names.items()}

    # ---- customer overdue ranking ----
    by_cust = defaultdict(lambda: {
        "cases": 0, "open_cases": 0, "overdue_cases": 0,
        "gross": 0.0, "open": 0.0, "overdue": 0.0,
        "not_due": 0.0, "channels": set(), "groups": set(),
        "users": set(), "slps": set(),
        "oldest_due": None, "max_days": 0,
        "cardname": None,
    })
    for r in clean:
        c = by_cust[r["cardcode"]]
        c["cardname"] = r.get("cardname")
        c["cases"] += 1
        gross = float(r.get("gross_sales_amount") or 0)
        op = float(r.get("open_amount") or 0)
        od = float(r.get("overdue_amount") or 0)
        nd = float(r.get("not_due_amount") or 0)
        c["gross"] += gross
        c["open"] += op
        c["overdue"] += od
        c["not_due"] += nd
        if op > 0.005:
            c["open_cases"] += 1
        if od > 0.005:
            c["overdue_cases"] += 1
        if r.get("channel"):
            c["channels"].add(r["channel"])
        if r.get("primary_business_group"):
            c["groups"].add(r["primary_business_group"])
        if r.get("sap_user"):
            c["users"].add(r["sap_user"])
        if r.get("slpcode"):
            c["slps"].add(r["slpcode"])
        due = r.get("due_date") or r.get("docduedate")
        days = r.get("days_overdue")
        if days:
            c["max_days"] = max(c["max_days"], days)
        if due and (c["oldest_due"] is None or str(due) < c["oldest_due"]):
            c["oldest_due"] = str(due)[:10]

    total_overdue_ex = money(sum(float(r.get("overdue_amount") or 0) for r in clean))
    total_open_ex = money(sum(float(r.get("open_amount") or 0) for r in clean))

    ranking = []
    for code, c in by_cust.items():
        ranking.append({
            "cardcode": code,
            "cardname": c["cardname"],
            "case_count": c["cases"],
            "open_cases": c["open_cases"],
            "overdue_cases": c["overdue_cases"],
            "gross_amount": money(c["gross"]),
            "open_amount": money(c["open"]),
            "overdue_amount": money(c["overdue"]),
            "not_due_amount": money(c["not_due"]),
            "oldest_due_date": c["oldest_due"],
            "max_days_overdue": c["max_days"],
            "business_group": sorted(c["groups"]),
            "channel": sorted(c["channels"]),
            "sap_user": sorted(c["users"]),
            "salesperson": sorted({slp_names.get(str(s), str(s)) for s in c["slps"]}),
        })
    ranking.sort(key=lambda r: -r["overdue_amount"])

    # concentration tiers
    def shares(k):
        top = sum(r["overdue_amount"] for r in ranking[:k])
        return money(top), round(100.0 * top / total_overdue_ex, 2) if total_overdue_ex else 0.0

    tier1_cases = sum(1 for r in ranking if r["overdue_amount"] > 0)
    concentration = {
        "total_overdue_ex": total_overdue_ex,
        "overdue_customers": tier1_cases,
        "top1": {"customer": ranking[0]["cardcode"] if ranking else None,
                 "amount": money(ranking[0]["overdue_amount"]) if ranking else 0,
                 "pct": shares(1)[1]},
        "top5": {"amount": shares(5)[0], "pct": shares(5)[1]},
        "top10": {"amount": shares(10)[0], "pct": shares(10)[1]},
    }

    # new top customer deeper profile
    new_top = None
    if ranking:
        t = ranking[0]
        new_top = {
            "cardcode": t["cardcode"],
            "cardname": t["cardname"],
            "overdue_amount": t["overdue_amount"],
            "open_amount": t["open_amount"],
            "cases": t["case_count"],
            "overdue_cases": t["overdue_cases"],
            "max_days_overdue": t["max_days_overdue"],
            "oldest_due_date": t["oldest_due_date"],
            "salespersons": t["salesperson"],
            "sap_users": t["sap_user"],
            "channel": t["channel"],
            "business_group": t["business_group"],
        }

    # ---- user ranking (overdue EX) ----
    by_user = defaultdict(lambda: {"cases": 0, "customers": set(), "open": 0.0, "overdue": 0.0,
                                   "not_due": 0.0, "gross": 0.0})
    for r in clean:
        u = r.get("sap_user") or "?"
        by_user[u]["cases"] += 1
        by_user[u]["customers"].add(r["cardcode"])
        by_user[u]["open"] += float(r.get("open_amount") or 0)
        by_user[u]["overdue"] += float(r.get("overdue_amount") or 0)
        by_user[u]["not_due"] += float(r.get("not_due_amount") or 0)
        by_user[u]["gross"] += float(r.get("gross_sales_amount") or 0)
    user_rows = [{
        "sap_user": u, "cases": v["cases"], "customers": len(v["customers"]),
        "gross": money(v["gross"]), "open": money(v["open"]),
        "overdue": money(v["overdue"]), "not_due": money(v["not_due"]),
    } for u, v in by_user.items()]
    user_rows.sort(key=lambda r: -r["overdue"])

    # ---- salesperson ranking (overdue EX) ----
    by_slp = defaultdict(lambda: {"cases": 0, "customers": set(), "open": 0.0, "overdue": 0.0,
                                  "gross": 0.0})
    for r in clean:
        s = r.get("slpcode")
        if s is None:
            continue
        by_slp[s]["cases"] += 1
        by_slp[s]["customers"].add(r["cardcode"])
        by_slp[s]["open"] += float(r.get("open_amount") or 0)
        by_slp[s]["overdue"] += float(r.get("overdue_amount") or 0)
        by_slp[s]["gross"] += float(r.get("gross_sales_amount") or 0)
    slp_rows = [{
        "slpcode": s,
        "salesperson": slp_names.get(str(s), str(s)),
        "cases": v["cases"], "customers": len(v["customers"]),
        "gross": money(v["gross"]), "open": money(v["open"]),
        "overdue": money(v["overdue"]),
    } for s, v in by_slp.items()]
    slp_rows.sort(key=lambda r: -r["overdue"])

    # ---- channel ranking ----
    by_chan = defaultdict(lambda: {"cases": 0, "open": 0.0, "overdue": 0.0, "gross": 0.0})
    for r in clean:
        ch = r.get("channel")
        by_chan[ch]["cases"] += 1
        by_chan[ch]["open"] += float(r.get("open_amount") or 0)
        by_chan[ch]["overdue"] += float(r.get("overdue_amount") or 0)
        by_chan[ch]["gross"] += float(r.get("gross_sales_amount") or 0)
    chan_rows = [{"channel": k, **{kk: money(vv) if kk != "cases" else vv
                                   for kk, vv in v.items()}}
                 for k, v in by_chan.items()]
    chan_rows.sort(key=lambda r: -r["overdue"])

    # ---- monthly cohorts EX vs WITH LR ----
    ex_month = defaultdict(lambda: {"cases": 0, "gross": 0.0, "open": 0.0,
                                    "not_due": 0.0, "overdue": 0.0})
    for r in clean:
        m = str(r.get("docdate"))[:7]
        ex_month[m]["cases"] += 1
        ex_month[m]["gross"] += float(r.get("gross_sales_amount") or 0)
        ex_month[m]["open"] += float(r.get("open_amount") or 0)
        ex_month[m]["not_due"] += float(r.get("not_due_amount") or 0)
        ex_month[m]["overdue"] += float(r.get("overdue_amount") or 0)
    # with LR baseline: use open_risk monthly cohorts
    prev = json.loads((Path(__file__).parent.parent / "credit_open_risk" /
                       "evidence" / "monthly_cohorts.json").read_text())
    cohorts = []
    for p in prev:
        m = p["month"]
        e = ex_month.get(m, {})
        cohorts.append({
            "month": m,
            "with_lr_cases": p["cases"],
            "ex_cases": e.get("cases", 0),
            "with_lr_gross": money(p["sale_amount"]),
            "ex_gross": money(e.get("gross", 0.0)),
            "with_lr_open": money(p["open_amount"]),
            "ex_open": money(e.get("open", 0.0)),
            "with_lr_overdue": money(p["overdue_amount"]),
            "ex_overdue": money(e.get("overdue", 0.0)),
            "ex_not_due": money(e.get("not_due", 0.0)),
            "ex_pct_overdue_of_month_open": round(100.0 * e.get("overdue", 0) / e.get("open", 0), 2)
            if e.get("open", 0) else 0.0,
        })
    cohorts.sort(key=lambda r: r["month"])

    # ---- repeat exposure EX ----
    seen_seq = defaultdict(list)
    for r in sorted(clean, key=lambda x: str(x.get("docdate"))):
        # sequence of sales while open (using open_at_sale proxy)
        seen_seq[r["cardcode"]].append(r)
    repeat_info = []
    for code, rows in seen_seq.items():
        if len(rows) < 2:
            continue
        multi_open = sum(1 for r in rows if float(r.get("open_at_sale") or 0) > 0.005
                         or bool(r.get("overdue_at_sale")))
        repeat_info.append({
            "cardcode": code,
            "cardname": rows[0].get("cardname"),
            "sales_while_open_or_overdue": multi_open,
            "total_cases": len(rows),
            "gross": money(sum(float(r.get("gross_sales_amount") or 0) for r in rows)),
            "open": money(sum(float(r.get("open_amount") or 0) for r in rows)),
            "overdue": money(sum(float(r.get("overdue_amount") or 0) for r in rows)),
        })
    repeat_info.sort(key=lambda r: -r["overdue"])

    (EVIDENCE / "customer_ranking.json").write_text(
        json.dumps({"ranking": ranking, "concentration": concentration,
                    "total_overdue_ex": total_overdue_ex, "total_open_ex": total_open_ex},
                   ensure_ascii=False, indent=1))
    (EVIDENCE / "new_top_customer.json").write_text(
        json.dumps(new_top, ensure_ascii=False, indent=1))
    (EVIDENCE / "user_ranking.json").write_text(json.dumps(user_rows, ensure_ascii=False, indent=1))
    (EVIDENCE / "salesperson_ranking.json").write_text(json.dumps(slp_rows, ensure_ascii=False, indent=1))
    (EVIDENCE / "channel_ranking.json").write_text(json.dumps(chan_rows, ensure_ascii=False, indent=1))
    (EVIDENCE / "monthly_cohorts_ex.json").write_text(json.dumps(cohorts, ensure_ascii=False, indent=1))
    (EVIDENCE / "repeat_exposure_ex.json").write_text(json.dumps(repeat_info, ensure_ascii=False, indent=1))

    print(json.dumps({
        "total_overdue_ex": total_overdue_ex,
        "overdue_customers": tier1_cases,
        "concentration": concentration,
        "new_top_customer": new_top,
        "top_users": user_rows[:6],
        "top_slps": slp_rows[:6],
        "channels": chan_rows,
        "cohorts": cohorts,
        "repeat_top": repeat_info[:8],
    }, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()