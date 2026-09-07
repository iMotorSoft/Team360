"""PHASE 19/20 — Order/Delivery/Invoice timing for the revalidated cases.

Base-document mapping validated for this installation (ObjType values):
  13=OINV, 14=ORIN, 15=ODLN, 16=RDN1, 17=ORDR, 23=OQUT
INV1.BaseType = ObjType of the base document. Chains resolved:
  OINV -> (BaseType 15) -> ODLN -> (DLN1.BaseType 17) -> ORDR
  OINV -> (BaseType 17) -> ORDR
  OINV -> (BaseType 23) -> OQUT

Also reconstructs whether at ORDER date the customer already had an overdue
unpaid invoice (same machinery as revalidate.py) to classify
ORDER_AUTHORIZED_BEFORE_OVERDUE with evidence.

Emits evidence/doc_chain.json and evidence/doc_chain_summary.json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "credit_exception" / "evidence"
TOLERANCE = 0.01


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def to_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def load_applied(cur, entries):
    app: dict[int, float] = defaultdict(float)
    if not entries:
        return app
    oitr = rows(cur, f'''SELECT "ReconNum","ReconDate" FROM "TELCHI"."OITR"
        WHERE "Canceled"='N' AND "ReconNum" IN (
          SELECT DISTINCT "ReconNum" FROM "TELCHI"."ITR1"
          WHERE "SrcObjTyp" IN ('13','14') AND "SrcObjAbs" IN ({",".join(["?"] * len(entries))})
        )''', entries)
    recon_ok = {r["reconnum"]: to_date(r["recondate"]) for r in oitr}
    lines = rows(cur, f'''SELECT "ReconNum","SrcObjAbs","ReconSum" FROM "TELCHI"."ITR1"
        WHERE "SrcObjTyp"='13' AND "SrcObjAbs" IN ({",".join(["?"] * len(entries))})''', entries)
    for t in lines:
        if t["reconnum"] in recon_ok:
            app[t["srcobjabs"]] += float(t["reconsum"] or 0)
    return app


def main() -> int:
    conn, cur = connect()
    try:
        cases = json.loads((EVIDENCE / "revalidated_cases.json").read_text(encoding="utf-8"))
        entries = [c["docentry"] for c in cases]
        cardcodes = sorted({c["cardcode"] for c in cases})
        ph = ",".join(["?"] * len(cardcodes))

        inv1 = rows(cur, f'''SELECT "DocEntry","BaseType","BaseEntry","BaseRef" FROM "TELCHI"."INV1"
            WHERE "DocEntry" IN ({",".join(["?"] * len(entries))}) AND "BaseType" IS NOT NULL''', entries)
        base_entries = sorted({r["baseentry"] for r in inv1 if r["baseentry"]})
        base_types = {int(r["basetype"]) for r in inv1 if r["basetype"] is not None}
        phb = ",".join(["?"] * len(base_entries)) if base_entries else "NULL"

        ordr: dict = {}
        odln: dict = {}
        oqut: dict = {}
        if 17 in base_types:
            ordr = {r["docentry"]: r for r in rows(cur, f'''SELECT "DocEntry","DocNum","CardCode","DocDate",
                "DocDueDate","DocTotal","CANCELED","UserSign","SlpCode" FROM "TELCHI"."ORDR"
                WHERE "DocEntry" IN ({phb})''', base_entries)}
        if 23 in base_types:
            oqut = {r["docentry"]: r for r in rows(cur, f'''SELECT "DocEntry","DocNum","CardCode","DocDate",
                "DocDueDate","DocTotal","CANCELED","UserSign","SlpCode" FROM "TELCHI"."OQUT"
                WHERE "DocEntry" IN ({phb})''', base_entries)}
        if 15 in base_types:
            odln = {r["docentry"]: r for r in rows(cur, f'''SELECT "DocEntry","DocNum","CardCode","DocDate",
                "DocDueDate","DocTotal","CANCELED","UserSign","SlpCode" FROM "TELCHI"."ODLN"
                WHERE "DocEntry" IN ({phb})''', base_entries)}
            if odln:
                dl1 = rows(cur, f'''SELECT "DocEntry","BaseEntry" FROM "TELCHI"."DLN1"
                    WHERE "DocEntry" IN ({",".join(["?"] * len(odln))}) AND "BaseType"='17' ''', list(odln))
                for r in dl1:
                    odln[r["docentry"]]["_order_base"] = r["baseentry"]

        # all active orders of the universe (for overdue-at-order-date)
        ordr_all = rows(cur, f'''SELECT "DocEntry","DocNum","CardCode","DocDate","DocDueDate",
            "DocTotal","CANCELED","UserSign" FROM "TELCHI"."ORDR"
            WHERE "CardCode" IN ({ph}) AND "CANCELED"='N' ''', cardcodes)
        ordr_by_cc: dict[str, list] = defaultdict(list)
        for r in ordr_all:
            ordr_by_cc[r["cardcode"]].append(r)
        inv_all = rows(cur, f'''SELECT "DocEntry","CardCode","DocDate","DocDueDate","DocTotal" FROM "TELCHI"."OINV"
            WHERE "CardCode" IN ({ph}) AND "CANCELED"='N' ''', cardcodes)
        inv_applied = load_applied(cur, [r["docentry"] for r in inv_all])
        inv_by_cc: dict[str, list] = defaultdict(list)
        for r in inv_all:
            inv_by_cc[r["cardcode"]].append(r)

        def overdue_volume(cc, at_date):
            total = 0.0
            for i in inv_by_cc.get(cc, []):
                dd = to_date(i["docdate"])
                if dd and dd >= at_date:
                    continue
                due = to_date(i["docduedate"])
                if due and due < at_date:
                    op = float(i["doctotal"]) - inv_applied.get(i["docentry"], 0.0)
                    if op > TOLERANCE:
                        total += op
            return total

        out = []
        for c in cases:
            de = c["docentry"]
            cc = c["cardcode"]
            bases = [r for r in inv1 if r["docentry"] == de]
            order_info = None
            delivery_info = None
            quotation_info = None
            for r in bases:
                if r["basetype"] == 17 or (isinstance(r["basetype"], str) and r["basetype"] == "17"):
                    _bt = 17
                elif r["basetype"] == 15 or (isinstance(r["basetype"], str) and r["basetype"] == "15"):
                    _bt = 15
                elif r["basetype"] == 23 or (isinstance(r["basetype"], str) and r["basetype"] == "23"):
                    _bt = 23
                else:
                    _bt = None
                if _bt == 17 and r["baseentry"] in ordr:
                    order_info = ordr[r["baseentry"]]
                elif _bt == 15 and r["baseentry"] in odln:
                    delivery_info = odln[r["baseentry"]]
                elif _bt == 23 and r["baseentry"] in oqut:
                    quotation_info = oqut[r["baseentry"]]
            if order_info is None and delivery_info is not None:
                ob = delivery_info.get("_order_base")
                if ob and ob in ordr:
                    order_info = ordr[ob]
            rec = {
                "docentry": de,
                "has_inv1_base_link": len(bases) > 0,
                "base_types": sorted({int(b) if isinstance(r["basetype"], str) or isinstance(r["basetype"], int) else r["basetype"] for b in (r["basetype"] for r in bases)}),
                "order_entry": order_info["docentry"] if order_info else None,
                "order_num": order_info["docnum"] if order_info else None,
                "order_date": str(order_info["docdate"])[:10] if order_info else None,
                "order_duedate": str(order_info["docduedate"])[:10] if order_info else None,
                "order_total": round(float(order_info["doctotal"]), 2) if order_info else None,
                "order_canceled": order_info["canceled"] if order_info else None,
                "order_user": order_info["usersign"] if order_info else None,
                "delivery_entry": delivery_info["docentry"] if delivery_info else None,
                "delivery_date": str(delivery_info["docdate"])[:10] if delivery_info else None,
                "delivery_total": round(float(delivery_info["doctotal"]), 2) if delivery_info else None,
                "quotation_entry": quotation_info["docentry"] if quotation_info else None,
                "quotation_date": str(quotation_info["docdate"])[:10] if quotation_info else None,
                "quotation_total": round(float(quotation_info["doctotal"]), 2) if quotation_info else None,
            }
            if order_info:
                od = to_date(order_info["docdate"])
                sd = date.fromisoformat(c["docdate"])
                rec["order_before_sale_days"] = (sd - od).days if od else None
                ov_at_order = overdue_volume(cc, od)
                rec["overdue_amount_at_order"] = round(ov_at_order, 2)
                rec["any_overdue_at_order"] = ov_at_order > TOLERANCE
            else:
                rec["overdue_amount_at_order"] = None
                rec["any_overdue_at_order"] = None
            out.append(rec)

        base_type_dist = defaultdict(int)
        for r in out:
            for b in r["base_types"]:
                base_type_dist[b] += 1
        summary = {
            "cases": len(out),
            "with_any_base_link": sum(1 for r in out if r["has_inv1_base_link"]),
            "with_order": sum(1 for r in out if r["order_entry"]),
            "with_delivery": sum(1 for r in out if r["delivery_entry"]),
            "with_quotation": sum(1 for r in out if r["quotation_entry"]),
            "order_not_overdue_at_order": sum(1 for r in out if r.get("any_overdue_at_order") is False),
            "order_overdue_already_at_order": sum(1 for r in out if r.get("any_overdue_at_order") is True),
            "base_type_distribution": dict(base_type_dist),
        }
        (EVIDENCE / "doc_chain.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        (EVIDENCE / "doc_chain_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        print(json.dumps(summary, indent=1))
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())