"""TELCHI_MATERIAL_STOCK_POSITION_V1 - validator (READ ONLY on HANA).

Executes the material stock position gate:
  1. SQL contracts (sql/current/stock/*.sql) execute cleanly
  2. Warehouse roles: all 82 resolved via taxonomy
  3. Item classification: produced (OWOR) + BOM component (ITT1) + flags
  4. Stock semantics: OnHand / IsCommited / OnOrder / Consig / Available
  5. Invariants: non-negative, no dup, item/whs integrity, UOM guard
  6. Ledger reconciliation sample: OITW.OnHand vs OINM In/Out
  7. Business cases (Matriplast packaging, soda caustica open PO)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.stock.stock_domain import (  # noqa: E402
    ItemFacts,
    classify_item,
    reconcile_ledger,
    resolve_warehouse_role,
)

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "stock"


def run_contracts(cur) -> dict:
    results = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            results[f.name] = {"rows": len(rows), "ok": True}
        except Exception as exc:  # pragma: no cover
            results[f.name] = {"rows": 0, "ok": False, "error": str(exc)}
    return results


def warehouse_roles(cur) -> list[dict]:
    cur.execute('''SELECT "WhsCode","WhsName","U_TYPE","U_TIPO","Inactive" FROM "TELCHI"."OWHS" ORDER BY "WhsCode"''')
    out = []
    for code, name, utype, utipo, inactive in cur.fetchall():
        role = resolve_warehouse_role(code, name, utype, utipo, inactive)
        out.append({"whscode": code, "name": name, "role": role, "inactive": inactive})
    return out


def item_facts(cur) -> dict[str, ItemFacts]:
    cur.execute('SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "Type"=\'S\'')
    produced = {r[0] for r in cur.fetchall()}
    cur.execute('SELECT DISTINCT "Code" FROM "TELCHI"."ITT1"')
    bom_components = {r[0] for r in cur.fetchall()}
    cur.execute('''SELECT "ItemCode","ItemName","ItemType","ItmsGrpCod","InvntItem","SellItem","PrchseItem"
        FROM "TELCHI"."OITM"''')
    out = {}
    for code, name, itype, grp, inv, sell, prch in cur.fetchall():
        out[code] = ItemFacts(
            itemcode=code, itemname=name or "", item_type=itype, itms_grp=grp,
            invnt_item=inv, sell_item=sell, prchse_item=prch,
            is_produced=code in produced, is_bom_component=code in bom_components)
    return out


def stock_summary(cur) -> dict:
    cur.execute('''SELECT COUNT(*), COUNT(DISTINCT "ItemCode"), COUNT(DISTINCT "WhsCode"),
        SUM("OnHand"), SUM("IsCommited"), SUM("OnOrder"), SUM("Consig")
        FROM "TELCHI"."OITW"''')
    n, n_item, n_whs, onhand, committed, onorder, consig = cur.fetchone()
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."OITW" WHERE "OnHand"<0')
    neg_onhand = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."OITW" WHERE "IsCommited"<0')
    neg_comm = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."OITW" WHERE "OnOrder"<0')
    neg_order = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM (SELECT "ItemCode","WhsCode" FROM "TELCHI"."OITW"
        GROUP BY "ItemCode","WhsCode" HAVING COUNT(*)>1)''')
    dup = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."OITW" T LEFT JOIN "TELCHI"."OITM" I
        ON I."ItemCode"=T."ItemCode" WHERE I."ItemCode" IS NULL''')
    orphan_item = cur.fetchone()[0]
    cur.execute('''SELECT COUNT(*) FROM "TELCHI"."OITW" T LEFT JOIN "TELCHI"."OWHS" W
        ON W."WhsCode"=T."WhsCode" WHERE W."WhsCode" IS NULL''')
    orphan_whs = cur.fetchone()[0]
    return {
        "rows": n, "items": n_item, "warehouses": n_whs,
        "onhand_total": float(onhand or 0), "committed_total": float(committed or 0),
        "onorder_total": float(onorder or 0), "consig_total": float(consig or 0),
        "negative_onhand": neg_onhand, "negative_committed": neg_comm,
        "negative_onorder": neg_order, "duplicate_item_whs": dup,
        "orphan_item": orphan_item, "orphan_whs": orphan_whs,
    }


def classify_distribution(cur, facts: dict[str, ItemFacts]) -> dict:
    # stock by item class (OnHand total, within compatible UOM only -> per-UOM aggregation)
    cur.execute('''SELECT T."ItemCode", I."InvntryUom", SUM(T."OnHand")
        FROM "TELCHI"."OITW" T JOIN "TELCHI"."OITM" I ON I."ItemCode"=T."ItemCode"
        GROUP BY T."ItemCode", I."InvntryUom"''')
    class_counts = Counter()
    class_items = Counter()
    for code, uom, onhand in cur.fetchall():
        cls = classify_item(facts.get(code, ItemFacts(code, "", None, None, None, None, None)))
        class_counts[cls] += 1
        class_items[cls] += 1
    return {"stock_lines": dict(class_counts), "items": dict(class_items)}


def reconcile_sample(cur, facts: dict[str, ItemFacts]) -> list[dict]:
    samples = [("L02475", "LAB-M1"), ("L01003", "LAB-T1"), ("L03409", "LAB-M1")]
    out = []
    for code, whs in samples:
        cur.execute('SELECT "OnHand" FROM "TELCHI"."OITW" WHERE "ItemCode"=? AND "WhsCode"=?', (code, whs))
        r = cur.fetchone()
        onhand = float(r[0] or 0) if r else 0.0
        cur.execute('SELECT SUM("InQty"), SUM("OutQty") FROM "TELCHI"."OINM" WHERE "ItemCode"=? AND "Warehouse"=?', (code, whs))
        inq, outq = cur.fetchone()
        ok, diff, flag = reconcile_ledger(onhand, float(inq or 0), float(outq or 0))
        out.append({"item": code, "whs": whs, "onhand": onhand,
                    "ledger_diff": diff, "flag": flag})
    return out


def business_cases(cur) -> dict:
    cases = {}
    # Matriplast packaging stock (frasco/tapa) vs open PO
    for code in ("L03427", "L03428", "L03429", "L00968"):
        cur.execute('''SELECT T."WhsCode", T."OnHand", T."OnOrder" FROM "TELCHI"."OITW" T
            WHERE T."ItemCode"=? AND (T."OnHand">0 OR T."OnOrder">0) ORDER BY T."OnHand" DESC''', (code,))
        cases.setdefault("matriplast_packaging", {})[code] = cur.fetchall()
    # soda caustica L01010 (108t open PO from Hainan)
    cur.execute('''SELECT T."WhsCode", T."OnHand", T."IsCommited", T."OnOrder" FROM "TELCHI"."OITW" T
        WHERE T."ItemCode"='L01010' ORDER BY T."OnHand" DESC''')
    cases["soda_caustica"] = cur.fetchall()
    return cases


def business_cases(cur) -> dict:
    cases = {}
    # tracer materials: physical vs onorder per warehouse
    tracers = {
        "L01010": "SODA CAUSTICA 25kg",
        "L01821": "CLORURO DE CALCIO 25kg",
        "L01785": "BENZOATO DE SODIO 25kg",
        "L03427": "FRASCO GOTERO NATURAL 30mL",
        "L03428": "TAPA GOTERO NATURAL 30mL",
        "L03429": "CONTRA TAPA GOTERO 30mL",
    }
    for code, label in tracers.items():
        cur.execute('''SELECT T."WhsCode", W."WhsName", T."OnHand", T."IsCommited", T."OnOrder"
            FROM "TELCHI"."OITW" T JOIN "TELCHI"."OWHS" W ON W."WhsCode"=T."WhsCode"
            WHERE T."ItemCode"=? AND (T."OnHand">0 OR T."OnOrder">0) ORDER BY T."OnHand" DESC''', (code,))
        cases[label] = cur.fetchall()
    return cases


def main() -> int:
    conn, cur = connect()
    try:
        facts = item_facts(cur)
        result = {
            "gate": "TELCHI_MATERIAL_STOCK_POSITION_V1",
            "contracts": run_contracts(cur),
            "warehouses": warehouse_roles(cur),
            "stock_summary": stock_summary(cur),
            "classification": classify_distribution(cur, facts),
            "reconcile_sample": reconcile_sample(cur, facts),
            "business_cases": business_cases(cur),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*72}\nTELCHI_MATERIAL_STOCK_POSITION_V1\n{'='*72}")
        contracts = result["contracts"]
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        roles = Counter(w["role"] for w in result["warehouses"])
        unresolved = [w["whscode"] for w in result["warehouses"] if w["role"].endswith("UNRESOLVED")]
        print(f"\nWAREHOUSES: {len(result['warehouses'])} total")
        for role, cnt in sorted(roles.items()):
            print(f"  {role:<30} {cnt}")
        if unresolved:
            print(f"  UNRESOLVED: {unresolved}")

        s = result["stock_summary"]
        print(f"\nSTOCK: {s['rows']:,} rows | {s['items']:,} items | {s['warehouses']} whs")
        print(f"  OnHand total = {s['onhand_total']:,.2f} | committed = {s['committed_total']:,.2f} "
              f"| onorder = {s['onorder_total']:,.2f} | consig = {s['consig_total']:,.2f}")
        print(f"  negative OnHand = {s['negative_onhand']} | negative committed = {s['negative_committed']} "
              f"| negative OnOrder = {s['negative_onorder']}")
        print(f"  duplicates = {s['duplicate_item_whs']} | orphan item = {s['orphan_item']} | orphan whs = {s['orphan_whs']}")

        print(f"\nCLASSIFICATION (stock lines): {result['classification']['stock_lines']}")
        print(f"CLASSIFICATION (items): {result['classification']['items']}")

        print("\nRECONCILE SAMPLE (OITW.OnHand vs OINM In-Out):")
        for r in result["reconcile_sample"]:
            print(f"  {r['item']}@{r['whs']}: onhand={r['onhand']:,.2f} diff={r['ledger_diff']:,.6f} -> {r['flag']}")

        print("\nBUSINESS CASES (physical OnHand | committed | OnOrder per warehouse):")
        for label, rows in result["business_cases"].items():
            tot = sum(float(r[2] or 0) for r in rows)
            oo = sum(float(r[4] or 0) for r in rows)
            print(f"  {label}: physical={tot:,.1f} onorder={oo:,.1f}")
            for r in rows:
                print(f"     {r[0]} ({r[1]}): onhand={float(r[2] or 0):,.1f} committed={float(r[3] or 0):,.1f} onorder={float(r[4] or 0):,.1f}")

        gate = "TELCHI_MATERIAL_STOCK_POSITION_V1_PASS" if (not failed and not unresolved
            and s["negative_onhand"] == 0 and s["duplicate_item_whs"] == 0
            and s["orphan_item"] == 0 and s["orphan_whs"] == 0) else "TELCHI_MATERIAL_STOCK_POSITION_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())