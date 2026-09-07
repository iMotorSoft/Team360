"""PHASE 3/4/16-19 — USER FULL and DELIVERY FLOW risk detail.

Consumes evidence/open_risk_cases.json.

USER FULL (40 cases, Bs 180,396.95 open): per-user table with not-due vs
overdue split, days-overdue metrics, per-customer view, block-date caveat
(mtolaba), technical account attribution (soluone).

DELIVERY FLOW (140 cases, Bs 71,282.55 open): not-due vs overdue, per-customer
concentration, order->delivery->invoice timing reconstruction (from the frozen
doc-chain evidence), C010341 LA REJA explicit analysis.

Emitted:
  evidence/user_full_detail.json
  evidence/delivery_detail.json
  evidence/delivery_timing.json
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_open_risk" / "evidence"

TECHNICAL = {"soluone", "dms", "b1i", "manager", "workflow"}


def money(v) -> float:
    return round(float(v or 0.0), 2)


def load() -> list[dict]:
    return json.loads((EVIDENCE / "open_risk_cases.json").read_text(encoding="utf-8"))


def pct(v, d) -> float:
    return round(100.0 * v / d, 2) if d else 0.0


def median(vals):
    return statistics.median(vals) if vals else None


# ---------------------------------------------------------------- USER FULL


def user_full_detail(rows, names, excel) -> dict:
    gr = [r for r in rows if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"]
    open_rows = [r for r in gr if r["open_amount"] > 0.05]
    user_idx = {u["login"].lower(): u for u in excel["users"]}

    by_user = defaultdict(lambda: {"cases": 0, "customers": set(), "open": 0.0,
                                   "not_due": 0.0, "overdue": 0.0,
                                   "overdue_cases": 0, "days_overdue": [],
                                   "first": None, "last": None, "approved_total": 0.0})
    for r in open_rows:
        u = by_user[r["sap_user"]]
        u["cases"] += 1
        u["customers"].add(r["cardcode"])
        u["open"] += r["open_amount"]
        u["not_due"] += r["not_due_amount"]
        u["overdue"] += r["overdue_amount"]
        u["approved_total"] += r["gross_sales_amount"]
        if r["days_overdue"] > 0:
            u["overdue_cases"] += 1
            u["days_overdue"].append(r["days_overdue"])
        u["first"] = min(u["first"] or r["docdate"][:10], r["docdate"][:10])
        u["last"] = max(u["last"] or r["docdate"][:10], r["docdate"][:10])

    detail = []
    for login, u in by_user.items():
        x = user_idx.get(login.lower())
        detail.append({
            "user_code": login,
            "user_name": (x.get("nombre") if x else None) or login,
            "authorization_level": "FULL",
            "authorization_source": "Excel vigente — HISTORICAL_AUTHORIZATION=UNAVAILABLE",
            "groups": [(g.get("nombre") if isinstance(g, dict) else g) for g in ((x.get("groups") if x else []) or [])],
            "blocked_excel": (x.get("bloqueado") if x else None),
            "technical_account": login.lower() in TECHNICAL,
            "open_cases": u["cases"],
            "customers": len(u["customers"]),
            "open_amount": money(u["open"]),
            "not_due_amount": money(u["not_due"]),
            "overdue_amount": money(u["overdue"]),
            "pct_overdue_of_open": pct(u["overdue"], u["open"]),
            "overdue_cases": u["overdue_cases"],
            "max_days_overdue": max(u["days_overdue"]) if u["days_overdue"] else None,
            "median_days_overdue": median(u["days_overdue"]),
            "approved_gross": money(u["approved_total"]),
            "sale_period": [u["first"], u["last"]],
        })
    detail.sort(key=lambda r: -r["overdue_amount"])

    # per customer within FULL
    by_cust = defaultdict(lambda: {"cases": 0, "users": set(), "open": 0.0,
                                   "not_due": 0.0, "overdue": 0.0,
                                   "days_overdue": [], "due_dates": []})
    for r in open_rows:
        c = by_cust[r["cardcode"]]
        c["cases"] += 1
        c["users"].add(r["sap_user"])
        c["open"] += r["open_amount"]
        c["not_due"] += r["not_due_amount"]
        c["overdue"] += r["overdue_amount"]
        if r["days_overdue"] > 0:
            c["days_overdue"].append(r["days_overdue"])
            c["due_dates"].append(r["due_date"][:10])
    cust_detail = sorted(
        ({"cardcode": k, "cardname": next(r["cardname"] for r in open_rows if r["cardcode"] == k),
          "users": sorted(v["users"]), "cases": v["cases"],
          "open": money(v["open"]), "not_due": money(v["not_due"]),
          "overdue": money(v["overdue"]), "max_days_overdue": max(v["days_overdue"]) if v["days_overdue"] else None,
          "oldest_due": min(v["due_dates"]) if v["due_dates"] else None}
         for k, v in by_cust.items()), key=lambda x: -x["overdue"])

    # mtolaba block caveat
    mtolaba = [r for r in open_rows if r["sap_user"] == "mtolaba"]
    block_note = None
    if mtolaba:
        block_note = {
            "user": "mtolaba",
            "blocked_excel": "Sí",
            "user_locked_hana": mtolaba[0].get("user_locked"),
            "sales": [{"docentry": r["doc_entry"], "docnum": r["docnum"],
                       "sale_date": r["docdate"][:10], "customer": r["cardcode"],
                       "amount": r["gross_sales_amount"], "due": r["due_date"][:10]} for r in mtolaba],
            "classification": "SALE_AFTER_BLOCK_UNCONFIRMED",
            "note": "Excel vigente marca bloqueado, pero OUSR user_locked='N'; sin historial de "
                    "fecha de bloqueo confiable (BLOCK_DATE_UNRESOLVED). No se acusa; se documenta.",
        }

    # soluone technical attribution
    soluone_cases = [r for r in open_rows if r["sap_user"] == "soluone"]
    soluone = {
        "user": "soluone",
        "technical_account": True,
        "cases": len(soluone_cases),
        "attribution": "POS Retail One via @SO1_01VENTA.U_SO1_USUARIO -> OHEM.empID where matched",
        "operators": [
            {"pos_id": r.get("retail", {}).get("usuario_pos"),
             "match": bool(r.get("retail", {}).get("matched")),
             "docentry": r["doc_entry"], "amount": r["gross_sales_amount"],
             "open": r["open_amount"], "overdue": r["overdue_amount"]}
            for r in soluone_cases],
    }

    return {"by_user": detail, "by_customer": cust_detail,
            "mtolaba_block_note": block_note, "soluone_technical": soluone,
            "totals": {"open": money(sum(r["open_amount"] for r in open_rows)),
                       "not_due": money(sum(r["not_due_amount"] for r in open_rows)),
                       "overdue": money(sum(r["overdue_amount"] for r in open_rows)),
                       "overdue_customers": len({r["cardcode"] for r in open_rows if r["days_overdue"] > 0}),
                       "overdue_users": len({r["sap_user"] for r in open_rows if r["days_overdue"] > 0})}}


# ---------------------------------------------------------------- DELIVERY


def delivery_detail(rows, names) -> dict:
    gr = [r for r in rows if r["secondary_reason"] == "DELIVERY_PREVIOUS"]
    open_rows = [r for r in gr if r["open_amount"] > 0.05]
    overdue_rows = [r for r in open_rows if r["days_overdue"] > 0]

    by_cust = defaultdict(lambda: {"cases": 0, "open": 0.0, "not_due": 0.0,
                                   "overdue": 0.0, "overdue_cases": 0,
                                   "users": set(), "days_overdue": [],
                                   "first": None, "last": None})
    for r in open_rows:
        c = by_cust[r["cardcode"]]
        c["cases"] += 1
        c["open"] += r["open_amount"]
        c["not_due"] += r["not_due_amount"]
        c["overdue"] += r["overdue_amount"]
        c["users"].add(r["sap_user"])
        if r["days_overdue"] > 0:
            c["overdue_cases"] += 1
            c["days_overdue"].append(r["days_overdue"])
        c["first"] = min(c["first"] or r["docdate"][:10], r["docdate"][:10])
        c["last"] = max(c["last"] or r["docdate"][:10], r["docdate"][:10])

    cust_detail = sorted(
        ({"cardcode": k, "cardname": next(r["cardname"] for r in open_rows if r["cardcode"] == k),
          "users": sorted(v["users"]), "cases": v["cases"],
          "open": money(v["open"]), "not_due": money(v["not_due"]),
          "overdue": money(v["overdue"]), "overdue_cases": v["overdue_cases"],
          "max_days_overdue": max(v["days_overdue"]) if v["days_overdue"] else None,
          "period": [v["first"], v["last"]]}
         for k, v in by_cust.items()), key=lambda x: -x["overdue"])

    la_reja = next((c for c in cust_detail if c["cardcode"] == "C010341"), None)
    la_reja_cases = [r for r in open_rows if r["cardcode"] == "C010341"]
    la_reja_detail = None
    if la_reja:
        la_reja_detail = {
            "cardcode": "C010341", "cardname": "LA REJA",
            **la_reja,
            "cases_detail": [{
                "docentry": r["doc_entry"], "docnum": r["docnum"],
                "sale_date": r["docdate"][:10], "due_date": r["due_date"][:10],
                "amount": r["gross_sales_amount"], "open": r["open_amount"],
                "overdue": r["overdue_amount"], "days_overdue": r["days_overdue"],
                "user": r["sap_user"], "channel": r["channel"],
                "delivery_date": (r.get("delivery_date") or "")[:10],
            } for r in sorted(la_reja_cases, key=lambda x: x["docdate"])],
        }

    return {
        "cases": len(gr),
        "open_cases": len(open_rows),
        "overdue_cases": len(overdue_rows),
        "open_amount": money(sum(r["open_amount"] for r in open_rows)),
        "not_due_amount": money(sum(r["not_due_amount"] for r in open_rows)),
        "overdue_amount": money(sum(r["overdue_amount"] for r in overdue_rows)),
        "overdue_customers": len({r["cardcode"] for r in overdue_rows}),
        "by_customer": cust_detail,
        "la_reja": la_reja_detail,
        "totals_share_of_global_overdue": pct(
            sum(r["overdue_amount"] for r in overdue_rows),
            sum(x["overdue_amount"] for x in rows)),
    }


def delivery_timing(rows) -> dict:
    """Reconstruct ORDER->DELIVERY->INVOICE timing where available (frozen doc-chain evidence)."""
    gr = [r for r in rows if r["secondary_reason"] == "DELIVERY_PREVIOUS"]
    timings = []
    with_chain = 0
    for r in gr:
        inv_date = r["docdate"][:10]
        del_date = (r.get("delivery_date") or "")[:10] or None
        ord_date = (r.get("order_date") or "")[:10] or None
        due = r["due_date"][:10]
        t = {"docentry": r["doc_entry"], "customer": r["cardcode"],
             "order_date": ord_date, "delivery_date": del_date,
             "invoice_date": inv_date, "due_date": due,
             "days_order_to_delivery": None, "days_delivery_to_invoice": None,
             "days_invoice_to_due": None, "days_due_to_cutoff": r["days_overdue"]}
        if ord_date and del_date:
            t["days_order_to_delivery"] = (date.fromisoformat(del_date) - date.fromisoformat(ord_date)).days
        if del_date:
            t["days_delivery_to_invoice"] = (date.fromisoformat(inv_date) - date.fromisoformat(del_date)).days
            with_chain += 1
        t["days_invoice_to_due"] = (date.fromisoformat(due) - date.fromisoformat(inv_date)).days
        timings.append(t)

    del_to_inv = [t["days_delivery_to_invoice"] for t in timings if t["days_delivery_to_invoice"] is not None]
    inv_to_due = [t["days_invoice_to_due"] for t in timings if t["days_invoice_to_due"] is not None]
    return {
        "cases": len(timings),
        "with_delivery_date": with_chain,
        "delivery_to_invoice_days": {"n": len(del_to_inv), "median": statistics.median(del_to_inv) if del_to_inv else None,
                                     "min": min(del_to_inv) if del_to_inv else None,
                                     "max": max(del_to_inv) if del_to_inv else None},
        "invoice_to_due_days": {"n": len(inv_to_due), "median": statistics.median(inv_to_due) if inv_to_due else None,
                                "min": min(inv_to_due) if inv_to_due else None,
                                "max": max(inv_to_due) if inv_to_due else None},
        "old_deliveries_late_invoiced": sum(1 for t in timings
                                            if t["days_delivery_to_invoice"] is not None and t["days_delivery_to_invoice"] > 60),
        "detail": timings,
    }


def main() -> int:
    rows = load()
    names = json.loads((EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "name_maps.json")
                       .read_text(encoding="utf-8"))
    excel = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "excel_authorization_model.json")
                       .read_text(encoding="utf-8"))

    uf = user_full_detail(rows, names, excel)
    dl = delivery_detail(rows, names)
    timing = delivery_timing(rows)

    (EVIDENCE / "user_full_detail.json").write_text(json.dumps(uf, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "delivery_detail.json").write_text(json.dumps(dl, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (EVIDENCE / "delivery_timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps({
        "user_full_totals": uf["totals"],
        "user_full_by_user": [{k: v for k, v in u.items() if k in (
            "user_code", "user_name", "open_cases", "customers", "open_amount",
            "not_due_amount", "overdue_amount", "pct_overdue_of_open", "max_days_overdue")}
            for u in uf["by_user"]],
        "delivery_totals": {k: dl[k] for k in ("open_amount", "not_due_amount", "overdue_amount",
                                               "overdue_cases", "overdue_customers")},
        "delivery_top_customers": [{k: c[k] for k in ("cardcode", "cardname", "cases", "open",
                                                      "not_due", "overdue", "max_days_overdue")}
                                   for c in dl["by_customer"][:6]],
        "la_reja": {k: dl["la_reja"][k] for k in ("cases", "open", "not_due", "overdue",
                                                  "max_days_overdue", "overdue_cases")} if dl["la_reja"] else None,
        "delivery_timing": {k: timing[k] for k in ("with_delivery_date", "delivery_to_invoice_days",
                                                   "invoice_to_due_days", "old_deliveries_late_invoiced")},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())