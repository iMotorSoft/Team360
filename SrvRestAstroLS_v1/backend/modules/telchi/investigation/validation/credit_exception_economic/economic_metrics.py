"""Economic metrics for the 268 explained cases grouped by business mechanism.

Consumes validation/credit_exception_economic/evidence/grouped_cases.json
(emitted by group_cases.py) plus the frozen evidence of the prior gate.

Emitted evidence:
  economic_metrics.json          - group summary table (section 6)
  monthly_series.json            - business_group x month series (section 8)
  collection.json                - collection stats + days-to-payment (19-20)
  aging.json                     - aging buckets of open balances (21)
  user_full_detail.json          - USER FULL per-user table (9-10, 33)
  customer_exception_detail.json - CUSTOMER EXCEPTION per-customer table (12-14)
  channels.json                  - channel x group (25)
  concentration.json             - top customers/users/salespersons (22-24)
  repeated_behavior.json         - repeated exception customers + FULL users (32-33)
  credit_exposure.json           - exposure at sale for FULL + EXCEPTION (30)
  executive_summary.json         - executive blocks (34-37, 55)
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception_economic" / "evidence"

GROUP_ORDER = [
    "USER_AUTHORIZATION_FULL",
    "CUSTOMER_EXCEPTION",
    "DOCUMENT_FLOW_PREAUTHORIZED",
    "NON_CREDIT_RETAIL_CASH",
    "TECHNICAL_RECONCILIATION",
]

AGING_BUCKETS = [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90),
                 ("91-180", 91, 180), ("180+", 181, 10**9)]

CUT_DATE = date(2026, 9, 2)  # analysis cut (same as payments_outcome.py)

TECHNICAL = {"soluone", "dms", "b1i", "manager", "workflow"}


def money(v) -> float:
    return round(float(v or 0.0), 2)


def load() -> tuple[list[dict], dict]:
    rows = json.loads((EVIDENCE / "grouped_cases.json").read_text(encoding="utf-8"))
    names = json.loads((EVIDENCE / "name_maps.json").read_text(encoding="utf-8"))
    return rows, names


def pct(v, d):
    return round(100.0 * v / d, 2) if d else 0.0


def median(vals):
    return statistics.median(vals) if vals else None


def quantile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


# ---------------------------------------------------------------- metrics


def group_metrics(rows):
    out = {}
    for g in GROUP_ORDER:
        gr = [r for r in rows if r["primary_business_group"] == g]
        cust = {r["cardcode"] for r in gr}
        users = {r["sap_user"] for r in gr}
        human_users = {u for u in users if u.lower() not in TECHNICAL and not any(r["technical_user"] for r in gr if r["sap_user"] == u)}
        slps = {r["slpcode"] for r in gr}
        gross = sum(r["gross_sales_amount"] for r in gr)
        paid = sum(r["paid_amount"] for r in gr)
        credited = sum(r["credited_amount"] for r in gr)
        open_amt = sum(r["open_amount"] for r in gr)
        amounts = [r["gross_sales_amount"] for r in gr]
        dates = sorted(r["docdate"] for r in gr)
        months = {d[:7] for d in dates}
        out[g] = {
            "case_count": len(gr),
            "customer_count": len(cust),
            "user_count": len(users),
            "human_user_count": len(human_users),
            "technical_user_count": len(users - human_users),
            "salesperson_count": len(slps),
            "gross_sales_amount": money(gross),
            "paid_amount": money(paid),
            "credited_amount": money(credited),
            "open_amount": money(open_amt),
            "average_sale_amount": money(statistics.mean(amounts)),
            "median_sale_amount": money(statistics.median(amounts)),
            "max_sale_amount": money(max(amounts)),
            "first_sale_date": dates[0] if dates else None,
            "last_sale_date": dates[-1] if dates else None,
            "active_days": (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1 if dates else 0,
            "active_months": len(months),
            "share_of_total_cases": pct(len(gr), len(rows)),
            "share_of_total_amount": pct(gross, sum(r["gross_sales_amount"] for r in rows)),
            "share_of_total_open": pct(open_amt, sum(r["open_amount"] for r in rows)),
        }
    return out


def monthly_series(rows):
    series = {}
    for g in GROUP_ORDER:
        by_month = defaultdict(lambda: {"case_count": 0, "sales_amount": 0.0,
                                        "paid_amount": 0.0, "open_amount": 0.0,
                                        "customers": set()})
        for r in rows:
            if r["primary_business_group"] != g:
                continue
            m = r["docdate"][:7]
            b = by_month[m]
            b["case_count"] += 1
            b["sales_amount"] += r["gross_sales_amount"]
            b["paid_amount"] += r["paid_amount"]
            b["open_amount"] += r["open_amount"]
            b["customers"].add(r["cardcode"])
        series[g] = [{
            "business_group": g,
            "month": m,
            "case_count": b["case_count"],
            "sales_amount": money(b["sales_amount"]),
            "paid_amount": money(b["paid_amount"]),
            "open_amount": money(b["open_amount"]),
            "customer_count": len(b["customers"]),
        } for m, b in sorted(by_month.items())]
    # global timeline
    by_month = defaultdict(lambda: {"case_count": 0, "sales_amount": 0.0,
                                    "paid_amount": 0.0, "open_amount": 0.0,
                                    "customers": set()})
    for r in rows:
        m = r["docdate"][:7]
        bm = by_month[m]
        bm["case_count"] += 1
        bm["sales_amount"] += r["gross_sales_amount"]
        bm["paid_amount"] += r["paid_amount"]
        bm["open_amount"] += r["open_amount"]
        bm["customers"].add(r["cardcode"])
    series["TOTAL"] = [{
        "month": m, "case_count": b["case_count"], "sales_amount": money(b["sales_amount"]),
        "paid_amount": money(b["paid_amount"]), "open_amount": money(b["open_amount"]),
        "customer_count": len(b["customers"]),
    } for m, b in sorted(by_month.items())]
    return series


def collection_stats(rows):
    out = {}
    for g in GROUP_ORDER + ["TOTAL"]:
        gr = rows if g == "TOTAL" else [r for r in rows if r["primary_business_group"] == g]
        status = Counter(r["current_status"] for r in gr)
        paid_amt = sum(r["paid_amount"] for r in gr)
        credited_amt = sum(r["credited_amount"] for r in gr)
        open_amt = sum(r["open_amount"] for r in gr)
        gross = sum(r["gross_sales_amount"] for r in gr)
        paid_cases = [r for r in gr if r["current_status"] == "FULLY_PAID"]
        d2p = [r["days_to_first_any"] for r in paid_cases if r["days_to_first_any"] is not None]
        out[g] = {
            "fully_paid_count": status.get("FULLY_PAID", 0),
            "partially_paid_count": status.get("PARTIALLY_PAID", 0),
            "open_count": status.get("OPEN", 0),
            "paid_amount": money(paid_amt),
            "credited_amount": money(credited_amt),
            "open_amount": money(open_amt),
            "collection_rate_count": pct(status.get("FULLY_PAID", 0), len(gr)),
            "collection_rate_amount": pct(paid_amt, gross),
            "settled_rate_amount": pct(paid_amt + credited_amt, gross),
            "days_to_first_payment_paid_only": {
                "n": len(d2p),
                "median": median(d2p),
                "p75": quantile(d2p, 0.75),
                "p90": quantile(d2p, 0.90),
                "max": max(d2p) if d2p else None,
                "zero_days_same_day": sum(1 for x in d2p if x == 0),
            },
        }
    return out


def aging(rows):
    out = {}
    for g in GROUP_ORDER + ["TOTAL"]:
        gr = rows if g == "TOTAL" else [r for r in rows if r["primary_business_group"] == g]
        buckets = {}
        for label, lo, hi in AGING_BUCKETS:
            sel = [r for r in gr if r["current_status"] != "FULLY_PAID"
                   and lo <= (r["days_open_since_sale"] or 0) <= hi]
            buckets[label] = {
                "open_amount": money(sum(r["open_amount"] for r in sel)),
                "case_count": len(sel),
                "customer_count": len({r["cardcode"] for r in sel}),
            }
        out[g] = buckets
    return out


def user_full_detail(rows, names):
    gr = [r for r in rows if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"]
    excel = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "excel_authorization_model.json")
                       .read_text(encoding="utf-8"))
    user_idx = {u["login"].lower(): u for u in excel["users"]}
    by_user = defaultdict(lambda: {"case_count": 0, "customers": set(), "amount": 0.0,
                                   "paid": 0.0, "open": 0.0, "first": None, "last": None,
                                   "credited": 0.0, "channels": set()})
    for r in gr:
        u = by_user[r["sap_user"]]
        u["case_count"] += 1
        u["customers"].add(r["cardcode"])
        u["amount"] += r["gross_sales_amount"]
        u["paid"] += r["paid_amount"]
        u["credited"] += r["credited_amount"]
        u["open"] += r["open_amount"]
        u["channels"].add(r["channel"])
        u["first"] = min(u["first"] or r["docdate"], r["docdate"])
        u["last"] = max(u["last"] or r["docdate"], r["docdate"])
    detail = []
    for login, u in by_user.items():
        x = user_idx.get(login.lower())
        detail.append({
            "user_code": login,
            "user_name": (x.get("nombre") if x else None),
            "groups": (x.get("groups") if x else []) or [],
            "group_label": (x.get("grupo_nombre") if x else None),
            "authorization_level": "FULL",
            "authorization_source": "Excel current (HISTORICAL_AUTHORIZATION=UNAVAILABLE)",
            "license": x.get("licencia") if x else None,
            "superuser": any(r["superuser"] == "Y" for r in gr if r["sap_user"] == login),
            "blocked": (x.get("bloqueado") if x else None),
            "technical_user": login.lower() in TECHNICAL,
            "case_count": u["case_count"],
            "customer_count": len(u["customers"]),
            "gross_sales_amount": money(u["amount"]),
            "paid_amount": money(u["paid"]),
            "credited_amount": money(u["credited"]),
            "open_amount": money(u["open"]),
            "first_sale_date": u["first"],
            "last_sale_date": u["last"],
            "channels": sorted(u["channels"]),
        })
    detail.sort(key=lambda r: -r["gross_sales_amount"])
    return detail


def customer_exception_detail(rows, names):
    gr = [r for r in rows if r["primary_business_group"] == "CUSTOMER_EXCEPTION"]
    by_cust = defaultdict(lambda: {"case_count": 0, "amount": 0.0, "paid": 0.0,
                                   "open": 0.0, "first": None, "last": None,
                                   "channels": set(), "operators": set(), "flag": "Y"})
    for r in gr:
        cc = by_cust[r["cardcode"]]
        cc["case_count"] += 1
        cc["amount"] += r["gross_sales_amount"]
        cc["paid"] += r["paid_amount"]
        cc["open"] += r["open_amount"]
        cc["channels"].add(r["channel"])
        op = r.get("retail", {}).get("usuario_pos")
        if op:
            cc["operators"].add(str(op))
        cc["first"] = min(cc["first"] or r["docdate"], r["docdate"])
        cc["last"] = max(cc["last"] or r["docdate"], r["docdate"])
    detail = []
    for cc, v in by_cust.items():
        ops = []
        for op in sorted(v["operators"]):
            m = names["pos_operators"].get(op)
            ops.append({"pos_id": op, "name": f"{m['first']} {m['last']}".strip() if m else None,
                        "branch": m.get("branch") if m else None})
        detail.append({
            "cardcode": cc,
            "cardname": next(r["cardname"] for r in gr if r["cardcode"] == cc),
            "flag": "U_SO1_01VENCREVENC='Y'",
            "flag_history": "CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE",
            "case_count": v["case_count"],
            "gross_sales_amount": money(v["amount"]),
            "paid_amount": money(v["paid"]),
            "open_amount": money(v["open"]),
            "first_sale_date": v["first"],
            "last_sale_date": v["last"],
            "channel": sorted(v["channels"]),
            "operators": ops,
            "sap_executor": sorted({r["sap_user"] for r in gr if r["cardcode"] == cc}),
        })
    detail.sort(key=lambda r: -r["gross_sales_amount"])
    return detail


def channels(rows):
    out = {}
    for g in GROUP_ORDER + ["TOTAL"]:
        gr = rows if g == "TOTAL" else [r for r in rows if r["primary_business_group"] == g]
        per_chan = {}
        for ch in ("RETAIL_ONE", "DMS", "SAP_DIRECT"):
            sel = [r for r in gr if r["channel"] == ch]
            per_chan[ch] = {
                "case_count": len(sel),
                "sales_amount": money(sum(r["gross_sales_amount"] for r in sel)),
                "open_amount": money(sum(r["open_amount"] for r in sel)),
            }
        out[g] = per_chan
    return out


def concentration(rows, names):
    out = {}
    for g in GROUP_ORDER:
        gr = [r for r in rows if r["primary_business_group"] == g]
        # top customers by sales / open / count
        by_cust = defaultdict(lambda: {"sales": 0.0, "open": 0.0, "cases": 0})
        for r in gr:
            cc = by_cust[r["cardcode"]]
            cc["sales"] += r["gross_sales_amount"]
            cc["open"] += r["open_amount"]
            cc["cases"] += 1
        customers = [{"cardcode": k, "cardname": next(r["cardname"] for r in gr if r["cardcode"] == k),
                      **v} for k, v in by_cust.items()]
        customers.sort(key=lambda x: -x["sales"])
        # top users
        by_user = defaultdict(lambda: {"sales": 0.0, "open": 0.0, "cases": 0, "customers": set()})
        for r in gr:
            u = by_user[r["sap_user"]]
            u["sales"] += r["gross_sales_amount"]
            u["open"] += r["open_amount"]
            u["cases"] += 1
            u["customers"].add(r["cardcode"])
        users = [{"user": k, "customer_count": len(v["customers"]),
                  "sales": money(v["sales"]), "open": money(v["open"]), "cases": v["cases"]}
                 for k, v in by_user.items()]
        users.sort(key=lambda x: -x["sales"])
        # salespersons
        by_slp = defaultdict(lambda: {"sales": 0.0, "open": 0.0, "cases": 0})
        for r in gr:
            s = by_slp[r["slpcode"]]
            s["sales"] += r["gross_sales_amount"]
            s["open"] += r["open_amount"]
            s["cases"] += 1
        slp = [{"slpcode": k, "slpname": names["salespersons"].get(str(k)),
                "sales": money(v["sales"]), "open": money(v["open"]), "cases": v["cases"]}
               for k, v in by_slp.items()]
        slp.sort(key=lambda x: -x["sales"])
        out[g] = {
            "top_customers_by_sales": [{**x, "sales": money(x["sales"]), "open": money(x["open"])} for x in customers[:10]],
            "top_customers_by_open": [{**x, "sales": money(x["sales"]), "open": money(x["open"])}
                                      for x in sorted(customers, key=lambda x: -x["open"])[:10]],
            "top_customers_by_cases": [{**x, "sales": money(x["sales"]), "open": money(x["open"])}
                                       for x in sorted(customers, key=lambda x: -x["cases"])[:10]],
            "top_users": users[:10],
            "top_salespersons": slp[:10],
        }
    return out


def repeated_behavior(rows):
    # exception-sale recurrence per customer (all groups)
    by_cust = defaultdict(lambda: {"cases": 0, "amount": 0.0, "open": 0.0,
                                   "first": None, "last": None, "groups": set()})
    for r in rows:
        cc = by_cust[r["cardcode"]]
        cc["cases"] += 1
        cc["amount"] += r["gross_sales_amount"]
        cc["open"] += r["open_amount"]
        cc["groups"].add(r["primary_business_group"])
        cc["first"] = min(cc["first"] or r["docdate"], r["docdate"])
        cc["last"] = max(cc["last"] or r["docdate"], r["docdate"])
    recurring = sorted(
        ({**v, "cardcode": k, "cardname": next(r["cardname"] for r in rows if r["cardcode"] == k),
          "groups": sorted(v["groups"]),
          "amount": money(v["amount"]), "open": money(v["open"])}
         for k, v in by_cust.items() if v["cases"] >= 2),
        key=lambda x: -x["cases"])
    # FULL user recurrence
    full_rows = [r for r in rows if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"]
    by_user = defaultdict(lambda: {"cases": 0, "customers": set(), "amount": 0.0,
                                   "open": 0.0, "first": None, "last": None})
    for r in full_rows:
        u = by_user[r["sap_user"]]
        u["cases"] += 1
        u["customers"].add(r["cardcode"])
        u["amount"] += r["gross_sales_amount"]
        u["open"] += r["open_amount"]
        u["first"] = min(u["first"] or r["docdate"], r["docdate"])
        u["last"] = max(u["last"] or r["docdate"], r["docdate"])
    full_recurring = sorted(
        ({**v, "user": k, "customer_count": len(v["customers"]),
          "amount": money(v["amount"]), "open": money(v["open"])}
         for k, v in by_user.items() if v["cases"] >= 2),
        key=lambda x: -x["cases"])
    return {
        "recurring_exception_customers": recurring,
        "recurring_full_users": full_recurring,
        "one_off_customers": sum(1 for v in by_cust.values() if v["cases"] == 1),
        "one_off_full_users": sum(1 for v in by_user.values() if v["cases"] == 1),
    }


def credit_exposure(rows):
    groups = ["USER_AUTHORIZATION_FULL", "CUSTOMER_EXCEPTION"]
    out = {}
    for g in groups:
        gr = [r for r in rows if r["primary_business_group"] == g]
        per = []
        for r in gr:
            per.append({
                "docentry": r["doc_entry"],
                "cardcode": r["cardcode"],
                "docdate": r["docdate"],
                "doctotal": r["gross_sales_amount"],
                "overdue_amount_at_sale": money(r["overdue_amount_at_sale"]),
                "overdue_count_at_sale": r["overdue_count_at_sale"],
                "exposure_before": money(r["exposure_before"]),
                "credit_line": money(r["creditline"]),
                "over_limit_before": bool(r["over_limit_before"]),
                "excess_over_limit": money(max((r["exposure_before"] or 0) - (r["creditline"] or 0), 0)),
                "open_now": r["open_amount"],
            })
        per.sort(key=lambda x: -x["overdue_amount_at_sale"])
        out[g] = {
            "cases": len(per),
            "total_overdue_amount_at_sale": money(sum(x["overdue_amount_at_sale"] for x in per)),
            "total_exposure_before": money(sum(x["exposure_before"] for x in per)),
            "over_limit_before_count": sum(1 for x in per if x["over_limit_before"]),
            "total_open_now": money(sum(x["open_now"] for x in per)),
            "detail_sorted_by_overdue": per,
        }
    return out


# ---------------------------------------------------------------- aggregate rows


def group_rows(rows, metrics, collection, aging_map):
    table = []
    total_open = metrics["USER_AUTHORIZATION_FULL"]["open_amount"] + \
        metrics["CUSTOMER_EXCEPTION"]["open_amount"] + metrics["DOCUMENT_FLOW_PREAUTHORIZED"]["open_amount"] + \
        metrics["NON_CREDIT_RETAIL_CASH"]["open_amount"] + metrics["TECHNICAL_RECONCILIATION"]["open_amount"]
    for g in GROUP_ORDER:
        m = metrics[g]
        cl = collection[g]
        table.append({
            "group": g,
            "label": next(r["business_group_label"] for r in rows if r["primary_business_group"] == g),
            "case_count": m["case_count"],
            "customer_count": m["customer_count"],
            "user_count": m["user_count"],
            "salesperson_count": m["salesperson_count"],
            "gross_sales_amount": m["gross_sales_amount"],
            "paid_amount": m["paid_amount"],
            "credited_amount": m["credited_amount"],
            "open_amount": m["open_amount"],
            "collection_rate_count": cl["collection_rate_count"],
            "collection_rate_amount": cl["collection_rate_amount"],
            "average_sale_amount": m["average_sale_amount"],
            "first_sale_date": m["first_sale_date"],
            "last_sale_date": m["last_sale_date"],
            "active_months": m["active_months"],
            "share_of_total_amount": m["share_of_total_amount"],
            "share_of_total_open": m["share_of_total_open"],
        })
    return table


def main() -> int:
    rows, names = load()
    metrics = group_metrics(rows)
    monthly = monthly_series(rows)
    collection = collection_stats(rows)
    aging_map = aging(rows)
    user_full = user_full_detail(rows, names)
    cust_exc = customer_exception_detail(rows, names)
    chan = channels(rows)
    concent = concentration(rows, names)
    repeated = repeated_behavior(rows)
    exposure = credit_exposure(rows)
    table = group_rows(rows, metrics, collection, aging_map)

    gross = money(sum(r["gross_sales_amount"] for r in rows))
    paid = money(sum(r["paid_amount"] for r in rows))
    credited = money(sum(r["credited_amount"] for r in rows))
    open_amt = money(sum(r["open_amount"] for r in rows))
    full_users = user_full

    executive = {
        "total_explained_cases": len(rows),
        "total_gross_sales_amount": gross,
        "total_paid_amount": paid,
        "total_credited_amount": credited,
        "total_open_amount": open_amt,
        "total_settled_amount": money(paid + credited),
        "currency": "BS (Bolivianos) — DocCur='BS' for all 268 (HANA verified)",
        "period": [min(r["docdate"] for r in rows), max(r["docdate"] for r in rows)],
        "first_sale_date": min(r["docdate"] for r in rows),
        "last_sale_date": max(r["docdate"] for r in rows),
        "channels_overall": chan["TOTAL"],
        "top_open_group": max(GROUP_ORDER, key=lambda g: metrics[g]["open_amount"]),
        "user_full_text": {
            "cases": metrics["USER_AUTHORIZATION_FULL"]["case_count"],
            "amount": metrics["USER_AUTHORIZATION_FULL"]["gross_sales_amount"],
            "open": metrics["USER_AUTHORIZATION_FULL"]["open_amount"],
            "users": metrics["USER_AUTHORIZATION_FULL"]["user_count"],
            "human_users": metrics["USER_AUTHORIZATION_FULL"]["human_user_count"],
            "customers": metrics["USER_AUTHORIZATION_FULL"]["customer_count"],
            "period": [metrics["USER_AUTHORIZATION_FULL"]["first_sale_date"],
                       metrics["USER_AUTHORIZATION_FULL"]["last_sale_date"]],
            "top_users": [{"user_code": u["user_code"], "user_name": u["user_name"],
                           "cases": u["case_count"], "amount": u["gross_sales_amount"],
                           "open": u["open_amount"]} for u in full_users[:3]],
        },
        "customer_exception_text": {
            "cases": metrics["CUSTOMER_EXCEPTION"]["case_count"],
            "amount": metrics["CUSTOMER_EXCEPTION"]["gross_sales_amount"],
            "open": metrics["CUSTOMER_EXCEPTION"]["open_amount"],
            "customers": metrics["CUSTOMER_EXCEPTION"]["customer_count"],
            "detail": [{"cardcode": d["cardcode"], "cardname": d["cardname"],
                        "cases": d["case_count"], "amount": d["gross_sales_amount"],
                        "open": d["open_amount"]} for d in cust_exc],
        },
    }

    bundle = {
        "group_table": table,
        "group_metrics": metrics,
        "monthly_series": monthly,
        "collection": collection,
        "aging": aging_map,
        "user_full_detail": user_full,
        "customer_exception_detail": cust_exc,
        "channels": chan,
        "concentration": concent,
        "repeated_behavior": repeated,
        "credit_exposure": exposure,
        "executive_summary": executive,
    }
    for fn, key in [
        ("economic_metrics.json", "group_metrics"),
        ("group_table.json", "group_table"),
        ("monthly_series.json", "monthly_series"),
        ("collection.json", "collection"),
        ("aging.json", "aging"),
        ("user_full_detail.json", "user_full_detail"),
        ("customer_exception_detail.json", "customer_exception_detail"),
        ("channels.json", "channels"),
        ("concentration.json", "concentration"),
        ("repeated_behavior.json", "repeated_behavior"),
        ("credit_exposure.json", "credit_exposure"),
        ("executive_summary.json", "executive_summary"),
    ]:
        (EVIDENCE / fn).write_text(json.dumps(bundle[key], ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps({
        "groups": [{"group": t["group"], "label": t["label"], "cases": t["case_count"],
                    "customers": t["customer_count"], "users": t["user_count"],
                    "amount": t["gross_sales_amount"], "paid": t["paid_amount"],
                    "open": t["open_amount"], "first": t["first_sale_date"],
                    "last": t["last_sale_date"]} for t in table],
        "total": {"gross": gross, "paid": paid, "credited": credited, "open": open_amt},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())