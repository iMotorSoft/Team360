"""PHASE 4/14/39 — Product analysis for C010341 LA REJA (READ ONLY).

For every INV1 line of the 40 frozen cases (and the full 85-invoice history
for comparison):
  - resolves ItemCode -> OITM (item master), OITB (item group)
  - classifies with the VALIDATED stock_domain.classify_item (never by
    description alone): uses ItemType + ItmsGrpCod + production/BOM
    membership + group-name keyword fallback.
  - aggregates by product and by category:
      MATERIA_PRIMA / INSUMO / ENVASE / ETIQUETA / SEMIELABORADO /
      PRODUCTO_TERMINADO / REPUESTO / SERVICIO / OTRO / UNKNOWN

Outputs:
  evidence/products_by_amount.json   (top products by amount)
  evidence/products_by_qty.json      (top products by quantity)
  evidence/products_category.json    (category table)
  evidence/product_lines_full.json   (audit rows: DocEntry+lines)
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

import sys
from stock_domain import (  # type: ignore
    classify_item, ItemFacts,
    ITEM_RAW_MATERIAL, ITEM_INPUT, ITEM_PACKAGING, ITEM_FINISHED_GOOD,
    ITEM_SEMI_FINISHED, ITEM_TRADED_GOOD, ITEM_SERVICE, ITEM_OTHER,
    ITEM_UNRESOLVED,
)

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    cases = json.loads((EVIDENCE / "atomic_la_reja_cases.json").read_text())
    conn, cur = connect()

    # production membership: items produced (OWOR output) or BOM component (ITT1)
    codes = {l["itemcode"] for c in cases for l in c["product_lines"]}
    cph = ",".join(["?"] * len(codes))
    cur.execute(f'''SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "ItemCode" IN ({cph})''', list(codes))
    produced = {r[0] for r in cur.fetchall()}
    cur.execute(f'''SELECT "Father" FROM "TELCHI"."ITT1" WHERE "Code" IN ({cph})''', list(codes))
    bom_components = {r[0] for r in cur.fetchall()}
    # OITB group names
    cur.execute('SELECT "ItmsGrpCod","ItmsGrpNam" FROM "TELCHI"."OITB"')
    groups = {r[0]: r[1] for r in cur.fetchall()}
    # OITM facts
    cur.execute(f'''SELECT "ItemCode","ItemName","ItemType","ItmsGrpCod","InvntItem","SellItem","PrchseItem","InvntryUom"
        FROM "TELCHI"."OITM" WHERE "ItemCode" IN ({cph})''', list(codes))
    facts = {r[0]: r for r in cur.fetchall()}
    conn.close()

    item_class = {}
    item_group_name = {}
    for code in codes:
        f = facts.get(code)
        if f is None:
            item_class[code] = ITEM_UNRESOLVED
            item_group_name[code] = None
            continue
        itm = ItemFacts(
            itemcode=code,
            itemname=f[1] or "",
            item_type=f[2],
            itms_grp=f[3],
            invnt_item=f[4],
            sell_item=f[5],
            prchse_item=f[6],
            invnt_uom=f[7],
            is_produced=code in produced,
            is_bom_component=code in bom_components,
        )
        item_class[code] = classify_item(itm)
        item_group_name[code] = groups.get(f[3])

    CAT_LABEL = {
        ITEM_RAW_MATERIAL: "MATERIA_PRIMA",
        ITEM_INPUT: "INSUMO",
        ITEM_PACKAGING: "ENVASE",
        ITEM_FINISHED_GOOD: "PRODUCTO_TERMINADO",
        ITEM_SEMI_FINISHED: "SEMIELABORADO",
        ITEM_TRADED_GOOD: "PRODUCTO_TERMINADO",
        ITEM_SERVICE: "SERVICIO",
        ITEM_OTHER: "OTRO",
        ITEM_UNRESOLVED: "UNKNOWN",
    }
    for c in cases:
        for l in c["product_lines"]:
            cl = item_class.get(l["itemcode"], ITEM_UNRESOLVED)
            l["classification"] = CAT_LABEL.get(cl, cl)
            l["group_name"] = item_group_name.get(l["itemcode"])

    # aggregates over the 40 cases
    by_prod_amount = defaultdict(lambda: {"qty": 0.0, "amount": 0.0, "docs": set(), "warehouses": set()})
    by_prod_qty = defaultdict(lambda: {"qty": 0.0, "amount": 0.0, "docs": set()})
    by_cat = defaultdict(lambda: {"lines": 0, "qty": 0.0, "amount": 0.0})
    for c in cases:
        for l in c["product_lines"]:
            qty = float(l["quantity"] or 0)
            amt = float(l["line_total"] or 0)
            by_prod_amount[l["itemcode"]]["qty"] += qty
            by_prod_amount[l["itemcode"]]["amount"] += amt
            by_prod_amount[l["itemcode"]]["docs"].add(c["invoice_docentry"])
            by_prod_amount[l["itemcode"]]["warehouses"].add(l["warehouse"])
            by_prod_qty[l["itemcode"]]["qty"] += qty
            by_prod_qty[l["itemcode"]]["amount"] += amt
            by_prod_qty[l["itemcode"]]["docs"].add(c["invoice_docentry"])
            by_cat[l["classification"]]["lines"] += 1
            by_cat[l["classification"]]["qty"] += qty
            by_cat[l["classification"]]["amount"] += amt

    def product_row(code, agg):
        f = facts.get(code)
        return {
            "itemcode": code,
            "description": (f[1] if f else None),
            "classification": item_class.get(code),
            "group": item_group_name.get(code),
            "quantity": round(agg["qty"], 3),
            "amount": money(agg["amount"]),
            "documents": sorted(agg.get("docs", ()))[:200],
            "doc_count": len(agg.get("docs", ())),
            "warehouses": sorted(agg.get("warehouses", ())) if "warehouses" in agg else None,
        }

    top_amount = sorted(by_prod_amount.items(), key=lambda kv: -kv[1]["amount"])[:20]
    top_qty = sorted(by_prod_qty.items(), key=lambda kv: -kv[1]["qty"])[:20]
    recurrent = sorted(by_prod_amount.items(), key=lambda kv: -len(kv[1]["docs"]))[:20]

    total_amount = money(sum(v["amount"] for v in by_cat.values()))
    cat_table = []
    for cls, agg in sorted(by_cat.items(), key=lambda kv: -kv[1]["amount"]):
        cat_table.append({
            "category": cls,
            "lines": agg["lines"],
            "quantity": round(agg["qty"], 3),
            "amount": money(agg["amount"]),
            "pct_amount": round(100.0 * agg["amount"] / total_amount, 2) if total_amount else 0.0,
        })

    out = {
        "total_lines": sum(v["lines"] for v in by_cat.values()),
        "total_amount": total_amount,
        "distinct_items": len(by_prod_amount),
        "category_table": cat_table,
        "top_20_by_amount": [product_row(c, a) for c, a in top_amount],
        "top_20_by_qty": [product_row(c, a) for c, a in top_qty],
        "top_20_recurrent": [product_row(c, a) for c, a in recurrent],
        "unclassified_items": sorted(code for code in codes if item_class.get(code) == ITEM_UNRESOLVED),
        "sap_write_count": 0,
    }
    (EVIDENCE / "products_by_amount.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "products_by_qty.json").write_text(json.dumps(out["top_20_by_qty"], ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "products_category.json").write_text(json.dumps(cat_table, ensure_ascii=False, indent=1, default=str))
    (EVIDENCE / "product_lines_full.json").write_text(
        json.dumps([{k: l for k, l in c.items() if k == "invoice_docentry"} or {**{"invoice_docentry": c["invoice_docentry"]}, **l}
                    for c in cases for l in c["product_lines"]], ensure_ascii=False, indent=1, default=str))
    print(json.dumps({
        "total_amount": total_amount,
        "distinct_items": len(by_prod_amount),
        "category_table": cat_table,
    }, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()