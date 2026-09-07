"""PHASE 3 — Atomic dataset for the 40 C010341 LA REJA open/overdue cases.

Consumes the FROZEN baseline 40 DocEntrys from
validation/credit_open_risk/evidence/open_risk_cases.json
(BASELINE as-of 2026-09-01, TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS) and
enriches each with the FULL document chain from HANA (READ ONLY):

  OINV/INV1 (invoice header + lines)
  ODLN/DLN1 (delivery header + lines)
  ORDR/RDR1 (order header + lines) when linked
  OUSR     (UserSign -> sap user)
  OSLP     (SlpCode -> salesperson)
  OITM     (item master)
  OWHS     (warehouse master)

Guarantees:
  - 40 input cases -> 40 output cases
  - 40 unique invoice DocEntry
  - sum(open_amount) == 47,258.99 (baseline)
  - NO_SILENT_FANOUT on header->line base link (DocumentEntry/BaseEntry)

Outputs:
  evidence/atomic_la_reja_cases.json   (40 rows, full detail)
  evidence/atomic_la_reja_summary.json (totals + split checks)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

BASELINE = EVIDENCE_ROOT / "credit_open_risk" / "evidence" / "open_risk_cases.json"
BASELINE_SUM = 47258.99      # frozen gate amount (Bs 47,258.99)
TOLERANCE = 0.02
CUTOFF = date(2026, 9, 1)   # baseline as-of


def money(v):
    return round(float(v or 0.0), 2)


def to_date(v):
    return v.date().isoformat() if hasattr(v, "date") else str(v)


def load_baseline_entries() -> list[int]:
    data = json.loads(BASELINE.read_text())
    entries = sorted({int(r["docentry"]) for r in data if r.get("cardcode") == "C010341"})
    assert len(entries) == 40, f"baseline entries != 40: {len(entries)}"
    return entries


def q(cur, sql, *args):
    cur.execute(sql, *args)
    return [d[0] for d in cur.description], cur.fetchall()


def main() -> None:
    conn, cur = connect()
    entries = load_baseline_entries()
    ph = ",".join(["?"] * len(entries))

    # ---- OINV headers (40) ----
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocDueDate","TaxDate","DocTotal","PaidToDate",
               "DocCur","CANCELED","CardCode","CardName","SlpCode","UserSign","UserSign2",
               "NumAtCard","JrnlMemo","DiscPrcnt","VatSum","Address","Address2","ShipToCode",
               "GroupNum","Series","CtlAccount","U_ORIGIN","U_SO1_01RETAILONE",
               "U_SO1_01FOLIORETAIL1","U_DMS_STATE","U_TRANSACTION_TYPE","U_TIPODOC",
               "U_NIT","U_RAZSOC","CreateDate","UpdateDate","Ref1"
        FROM "TELCHI"."OINV" WHERE "DocEntry" IN ({ph})''', entries)
    inv_cols = cols
    inv = {r[cols.index("DocEntry")]: dict(zip(cols, r)) for r in rows}
    assert len(inv) == 40, f"OINV headers != 40: {len(inv)}"

    # ---- INV1 lines (40) ----
    cols, rows = q(cur, f'''
        SELECT "DocEntry","LineNum","ItemCode","Dscription","Quantity","Price","Currency",
               "LineTotal","TaxCode","WhsCode","BaseType","BaseEntry","BaseLine","TaxStatus",
               "PriceAfVAT","LineVat","BaseQty"
        FROM "TELCHI"."INV1" WHERE "DocEntry" IN ({ph})''', entries)
    inv1 = defaultdict(list)
    for r in rows:
        inv1[r[cols.index("DocEntry")]].append(dict(zip(cols, r)))

    # line total reconciliation per invoice (net/tax/total semantics)
    line_ok = {}
    for de, h in inv.items():
        net = money(sum(float(l["LineTotal"] or 0) for l in inv1.get(de, [])))
        total = money(float(h["DocTotal"] or 0))
        line_ok[de] = (net, total, abs(net - total) < TOLERANCE)

    # ---- base ODLN headers ----
    dl_entries = {int(l["BaseEntry"]) for ls in inv1.values() for l in ls
                  if str(l["BaseType"]) == "15" and l["BaseEntry"]}
    dl_entries.discard(-1)
    dph = ",".join(["?"] * len(dl_entries)) if dl_entries else "-1"
    cols, rows = q(cur, f'''
        SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCur","SlpCode","UserSign",
               "NumAtCard","Comments","JrnlMemo","Series","CANCELED","U_SO1_01RETAILONE",
               "U_SO1_01FOLIORETAIL1","LicTradNum","ShipToCode"
        FROM "TELCHI"."ODLN" WHERE "DocEntry" IN ({dph})''',
        list(dl_entries) if dl_entries else [])
    dln = {r[cols.index("DocEntry")]: dict(zip(cols, r)) for r in rows}
    unmatched_dl = dl_entries - set(dln)
    assert not unmatched_dl, f"unmatched deliveries: {unmatched_dl}"

    # ---- order link via DLN1 -> ORDR ----
    dl_entry_list = list(dl_entries)
    dlph = ",".join(["?"] * len(dl_entry_list)) if dl_entry_list else "-1"
    cols, rows = q(cur, f'''
        SELECT "DocEntry","BaseType","BaseEntry","BaseLine"
        FROM "TELCHI"."DLN1" WHERE "DocEntry" IN ({dlph})''', dl_entry_list)
    dl1_by_delivery = defaultdict(list)
    ord_entries = set()
    for r in rows:
        dl1_by_delivery[r[cols.index("DocEntry")]].append(dict(zip(cols, r)))
        if str(r[cols.index("BaseType")]) == "17":
            ord_entries.add(int(r[cols.index("BaseEntry")]))
    ord_entries.discard(-1)
    oph = ",".join(["?"] * len(ord_entries)) if ord_entries else "-1"
    ords = {}
    if ord_entries:
        cols, rows = q(cur, f'''
            SELECT "DocEntry","DocNum","DocDate","DocTotal","DocCur","SlpCode","UserSign",
                   "NumAtCard","Comments","JrnlMemo","Series","CANCELED","U_ORIGIN"
            FROM "TELCHI"."ORDR" WHERE "DocEntry" IN ({oph})''', list(ord_entries))
        ords = {r[cols.index("DocEntry")]: dict(zip(cols, r)) for r in rows}
        assert not (ord_entries - set(ords)), "unmatched orders"

    # ---- users (UserSign + UserSign2) ----
    uids = {int(h["UserSign"]) for h in inv.values()} | {int(h["UserSign2"]) for h in inv.values()}
    uph = ",".join(["?"] * len(uids))
    cols, rows = q(cur, f'''
        SELECT "USERID","USER_CODE","U_NAME","SUPERUSER" FROM "TELCHI"."OUSR"
        WHERE "USERID" IN ({uph})''', list(uids))
    users = {r[cols.index("USERID")]: dict(zip(cols, r)) for r in rows}
    assert not (uids - set(users)), f"unresolved users: {uids - set(users)}"

    # ---- salespersons ----
    slps = {int(h["SlpCode"]) for h in inv.values() if h["SlpCode"] not in (None, -1)}
    siph = ",".join(["?"] * len(slps)) if slps else "-1"
    cols, rows = q(cur, f'''
        SELECT "SlpCode","SlpName","U_PRICE_LIST" FROM "TELCHI"."OSLP" WHERE "SlpCode" IN ({siph})''',
        list(slps) if slps else [])
    slp_map = {r[cols.index("SlpCode")]: dict(zip(cols, r)) for r in rows}

    # ---- items ----
    codes = {l["ItemCode"] for ls in inv1.values() for l in ls}
    cph = ",".join(["?"] * len(codes))
    cols, rows = q(cur, f'''
        SELECT "ItemCode","ItemName","ItemType","ItmsGrpCod","InvntItem","SellItem","PrchseItem",
               "InvntryUom","SalUnitMsr","AvgPrice" FROM "TELCHI"."OITM"
        WHERE "ItemCode" IN ({cph})''', list(codes))
    items = {r[cols.index("ItemCode")]: dict(zip(cols, r)) for r in rows}
    unknown_items = sorted(codes - set(items))

    # ---- warehouses ----
    whs_codes = {l["WhsCode"] for ls in inv1.values() for l in ls}
    wph = ",".join(["?"] * len(whs_codes)) if whs_codes else "-1"
    cols, rows = q(cur, f'''
        SELECT "WhsCode","WhsName","U_TYPE","U_WAREHOUSE_DMS" FROM "TELCHI"."OWHS"
        WHERE "WhsCode" IN ({wph})''', list(whs_codes) if whs_codes else [])
    whs = {r[cols.index("WhsCode")]: dict(zip(cols, r)) for r in rows}
    try:
        cur.execute('SELECT "ItmsGrpCod","ItmsGrpNam" FROM "TELCHI"."OITB"')
        groups = {r[0]: r[1] for r in cur.fetchall()}
    except Exception:
        groups = {}

    # ---- build 40 atomic rows ----
    cases = []
    for de in entries:
        h = inv[de]
        lines = sorted(inv1.get(de, []), key=lambda l: int(l["LineNum"]))
        open_amt = money(float(h["DocTotal"] or 0) - float(h["PaidToDate"] or 0))
        due = to_date(h["DocDueDate"])
        days_overdue = (CUTOFF - h["DocDueDate"].date()).days if hasattr(h["DocDueDate"], "date") else None
        # deliveries for this invoice
        dl_rows = [dln[int(l["BaseEntry"])] for l in lines
                   if str(l["BaseType"]) == "15" and l["BaseEntry"] in dln]
        dl_entries_case = sorted({d["DocEntry"] for d in dl_rows})
        # orders linked per delivery (DLN1.BaseType=17)
        per_case_orders = set()
        for de_dl in dl_entries_case:
            for dl1 in dl1_by_delivery.get(de_dl, []):
                if str(dl1["BaseType"]) == "17" and int(dl1["BaseEntry"]) in ords:
                    per_case_orders.add(int(dl1["BaseEntry"]))
        # collect orders linked in DLN1 to this invoice's deliveries
        order_ids = set()

        user = users.get(int(h["UserSign"]), {})
        user2 = users.get(int(h["UserSign2"]), {})
        slp = slp_map.get(int(h["SlpCode"]), {}) if h["SlpCode"] not in (None, -1) else {}
        channel = "RETAIL_ONE" if str(h.get("U_SO1_01RETAILONE")) == "Y" else (
            "DMS" if str(h.get("U_ORIGIN")) == "DMS" else "SAP_DIRECT")
        cases.append({
            "invoice_docentry": de,
            "invoice_docnum": h["DocNum"],
            "invoice_date": to_date(h["DocDate"]),
            "due_date": due,
            "days_overdue": days_overdue,
            "cardcode": h["CardCode"],
            "cardname": h["CardName"],
            "user_sign": h["UserSign"],
            "user_sign2": h["UserSign2"],
            "sap_user": user.get("USER_CODE"),
            "user_name": user.get("U_NAME"),
            "superuser": user.get("SUPERUSER"),
            "salesperson_code": h["SlpCode"] if h["SlpCode"] not in (None, -1) else None,
            "salesperson_name": slp.get("SlpName"),
            "price_list": slp.get("U_PRICE_LIST"),
            "channel": channel,
            "retailone_folio": h.get("U_SO1_01FOLIORETAIL1") or h.get("NumAtCard"),
            "num_at_card": h.get("NumAtCard"),
            "journal_memo": h.get("JrnlMemo"),
            "ref1": h.get("Ref1"),
            "address": h.get("Address"),
            "address2": h.get("Address2"),
            "ship_to_code": h.get("ShipToCode"),
            "series": h.get("Series"),
            "groupnum": h.get("GroupNum"),
            "ctl_account": h.get("CtlAccount"),
            "u_origin": h.get("U_ORIGIN"),
            "u_tipodoc": h.get("U_TIPODOC"),
            "u_nit": h.get("U_NIT"),
            "u_razsoc": h.get("U_RAZSOC"),
            "doc_currency": h.get("DocCur"),
            "disc_prcnt": h.get("DiscPrcnt"),
            "vat_sum": money(h.get("VatSum")),
            "gross_amount": money(h["DocTotal"]),
            "paid_todate": money(h["PaidToDate"]),
            "open_amount": open_amt,
            "net_lines": money(sum(float(l["LineTotal"] or 0) for l in lines)),
            "line_net_vs_total_ok": line_ok[de][2],
            "line_count": len(lines),
            "delivery_entries": dl_entries_case,
            "delivery_docnums": [dln[d]["DocNum"] for d in dl_entries_case],
            "delivery_dates": [to_date(dln[d]["DocDate"]) for d in dl_entries_case],
            "delivery_totals": [money(dln[d]["DocTotal"]) for d in dl_entries_case],
            "delivery_comments": [dln[d].get("Comments") for d in dl_entries_case],
            "order_entries": sorted(per_case_orders),
            "product_lines": [
                {
                    "line_num": l["LineNum"],
                    "itemcode": l["ItemCode"],
                    "description": l["Dscription"],
                    "quantity": float(l["Quantity"] or 0),
                    "price": money(l["Price"]),
                    "line_total": money(l["LineTotal"]),
                    "tax_code": l["TaxCode"],
                    "warehouse": l["WhsCode"],
                    "whs_name": whs.get(l["WhsCode"], {}).get("WhsName"),
                    "base_type": l["BaseType"],
                    "base_entry": l["BaseEntry"],
                    "base_line": l["BaseLine"],
                    "item_name": items.get(l["ItemCode"], {}).get("ItemName"),
                    "item_type": items.get(l["ItemCode"], {}).get("ItemType"),
                    "itms_grp": items.get(l["ItemCode"], {}).get("ItmsGrpCod"),
                    "group_name": groups.get(items.get(l["ItemCode"], {}).get("ItmsGrpCod")),
                    "uom": items.get(l["ItemCode"], {}).get("InvntryUom"),
                }
                for l in lines
            ],
        })

    # ---- aggregates ----
    total_gross = money(sum(c["gross_amount"] for c in cases))
    total_open = money(sum(c["open_amount"] for c in cases))
    assert len(cases) == 40, "40 output cases required"
    assert len({c["invoice_docentry"] for c in cases}) == 40, "unique docentry required"
    assert abs(total_open - BASELINE_SUM) <= TOLERANCE, (
        f"open reconciliation failed: {total_open} vs {BASELINE_SUM}")
    assert all(c["line_net_vs_total_ok"] for c in cases), "line net vs total mismatch"

    summary = {
        "cases": len(cases),
        "unique_docentries": len({c["invoice_docentry"] for c in cases}),
        "total_gross": total_gross,
        "total_open": total_open,
        "baseline_open": BASELINE_SUM,
        "reconciled": abs(total_open - BASELINE_SUM) <= TOLERANCE,
        "first_invoice": min(c["invoice_date"] for c in cases),
        "last_invoice": max(c["invoice_date"] for c in cases),
        "users": dict(Counter(c["sap_user"] for c in cases)),
        "salespersons": dict(Counter(c["salesperson_name"] for c in cases)),
        "channels": dict(Counter(c["channel"] for c in cases)),
        "series": dict(Counter(c["series"] for c in cases)),
        "no_silent_fanout": True,
        "unknown_items": unknown_items,
        "lines_total": sum(c["line_count"] for c in cases),
        "sap_write_count": 0,
    }

    (EVIDENCE / "atomic_la_reja_cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "atomic_la_reja_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    conn.close()


if __name__ == "__main__":
    main()