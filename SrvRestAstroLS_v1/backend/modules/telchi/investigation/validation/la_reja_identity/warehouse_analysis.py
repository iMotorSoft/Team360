"""PHASE 5/16/42 — Warehouse analysis + stock effect for C010341 (READ ONLY).

  a) INV1 (invoice lines) WhsCode distribution for the 40 frozen cases.
  b) DLN1 (delivery lines) WhsCode distribution for the linked deliveries.
  c) warehouse role via VALIDATED taxonomy: OWHS U_TYPE (SAP/DMS) + name.
  d) OINM stock effect sample: delivery quantity vs OINM out quantity/sign/
     warehouse for 5 representative deliveries (no invoice=stock assumption).

Outputs:
  evidence/warehouses_invoices.json
  evidence/warehouses_deliveries.json
  evidence/stock_effect_sample.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    cases = json.loads((EVIDENCE / "atomic_la_reja_cases.json").read_text())
    conn, cur = connect()

    # warehouse master
    cur.execute('SELECT "WhsCode","WhsName","U_TYPE","U_WAREHOUSE_DMS" FROM "TELCHI"."OWHS"')
    whs = {r[0]: {"name": r[1], "u_type": r[2], "dms": r[3]} for r in cur.fetchall()}

    # a) invoice lines
    whs_inv = Counter()
    whs_inv_amount = defaultdict(float)
    for c in cases:
        for l in c["product_lines"]:
            whs_inv[l["warehouse"]] += 1
            whs_inv_amount[l["warehouse"]] += float(l["line_total"] or 0)

    # b) delivery lines
    dl_entries = {de for c in cases for de in c["delivery_entries"]}
    dph = ",".join(["?"] * len(dl_entries))
    cur.execute(f'''SELECT "DocEntry","ItemCode","Quantity","LineTotal","WhsCode","LineNum"
        FROM "TELCHI"."DLN1" WHERE "DocEntry" IN ({dph})''', list(dl_entries))
    dl_rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    whs_dln = Counter((r["DocEntry"], r["WhsCode"]) for r in dl_rows)
    whs_dlv = Counter(r["WhsCode"] for r in dl_rows)
    whs_dlv_amount = defaultdict(float)
    for r in dl_rows:
        whs_dlv_amount[r["WhsCode"]] += float(r["LineTotal"] or 0)

    inv_table = []
    for wh, n in whs_inv.most_common():
        inv_table.append({
            "warehouse": wh,
            "role": whs.get(wh, {}).get("u_type"),
            "name": whs.get(wh, {}).get("name"),
            "lines": n,
            "amount": money(whs_inv_amount[wh]),
        })
    dlv_table = []
    for wh, n in whs_dlv.most_common():
        dlv_table.append({
            "warehouse": wh,
            "role": whs.get(wh, {}).get("u_type"),
            "name": whs.get(wh, {}).get("name"),
            "lines": n,
            "amount": money(whs_dlv_amount[wh]),
        })

    # d) OINM stock effect sample: pick 5 representative deliveries
    #    OINM: TransType=15 (delivery), BASE_REF=DocNum, DocLineNum=LineNum
    sample = []
    for de in sorted(dl_entries)[:5]:
        cur.execute('''SELECT "DocNum","DocDate","Comments" FROM "TELCHI"."ODLN" WHERE "DocEntry"=?''', (de,))
        h = cur.fetchone()
        cur.execute('''SELECT "ItemCode","Quantity","LineTotal","WhsCode","LineNum","BaseRef"
            FROM "TELCHI"."DLN1" WHERE "DocEntry"=? ORDER BY "LineNum"''', (de,))
        lines = cur.fetchall()
        row = {
            "delivery_docentry": de,
            "delivery_docnum": h[0] if h else None,
            "delivery_date": h[1].date().isoformat() if h else None,
            "comments": (h[2] or "")[:120] if h else None,
            "lines": [],
        }
        for ln in lines:
            # ln[0]=ItemCode ln[1]=Quantity ln[2]=LineTotal ln[3]=WhsCode ln[4]=LineNum ln[5]=BaseRef
            cur.execute('''SELECT "BASE_REF","DocLineNum","ItemCode","InQty","OutQty","Warehouse","TransType","DocDate"
                FROM "TELCHI"."OINM" WHERE "TransType"=15 AND "ItemCode"=?
                AND "DocLineNum"=? AND "BASE_REF"=?
                ORDER BY "DocDate"''', (ln[0], ln[4], h[0] if h else None))
            moves = cur.fetchall()
            row["lines"].append({
                "line": ln[4],
                "item": ln[0],
                "qty": float(ln[1] or 0),
                "line_total": money(ln[2]),
                "whs_code": ln[3],
                "invm_moves": [
                    {"base_ref": m[0], "doc_line_num": m[1], "item": m[2],
                     "in_qty": float(m[3] or 0), "out_qty": float(m[4] or 0),
                     "whs": m[5], "trans_type": m[6], "date": m[7].date().isoformat()}
                    for m in moves
                ],
            })
        sample.append(row)

    out = {
        "invoice_warehouses": inv_table,
        "delivery_warehouses": dlv_table,
        "invoice_whs_total": sum(t["lines"] for t in inv_table),
        "delivery_whs_total": sum(t["lines"] for t in dlv_table),
        "stock_effect_sample": sample,
        "sap_write_count": 0,
    }
    (EVIDENCE / "warehouses_invoices.json").write_text(json.dumps(inv_table, ensure_ascii=False, indent=1))
    (EVIDENCE / "warehouses_deliveries.json").write_text(json.dumps(dlv_table, ensure_ascii=False, indent=1))
    (EVIDENCE / "stock_effect_sample.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"invoice_warehouses": inv_table, "delivery_warehouses": dlv_table},
                     ensure_ascii=False, indent=1, default=str))
    conn.close()


if __name__ == "__main__":
    main()