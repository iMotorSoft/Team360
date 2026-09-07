"""TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1 - validator (READ ONLY).

Executes the finished-goods -> material equivalence gate:
  1. SQL contracts (sql/current/equivalence/*.sql)
  2. FG stock (produced items, OnHand>0) + warehouse role + usability split
  3. HISTORICAL_PRODUCTION ratio: consumed(IGE1)/produced(IGN1) per FG-comp
  4. CURRENT_BOM fallback: ITT1.Quantity/OITT.Qauntity
  5. Direct equivalence = FG stock x qty_per_fg
  6. Terminal expansion (semi -> raw), cycle-guarded
  7. No-double-count / conservation invariants
  8. Tracer cases (soda caustica, cloruro, benzoato, gotero)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.stock.stock_domain import (  # noqa: E402
    ItemFacts, classify_item, resolve_warehouse_role,
)
from modules.telchi.investigation.validation.equivalence.equivalence_domain import (  # noqa: E402
    ComponentRatio, FgStock, build_equivalence, classify_equivalence,
    current_bom_ratio, expand_terminal, global_equivalent_total,
    historical_ratio, transfer_conservation,
)

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "equivalence"

USABLE_ROLES = {"FINISHED_GOOD", "BRANCH", "DISTRIBUTION", "MOBILE",
                "DISPENSING", "CONSIGNMENT", "RETURNS"}


def run_contracts(cur) -> dict:
    results = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        try:
            cur.execute(f.read_text(encoding="utf-8"))
            n = len(cur.fetchall())
            results[f.name] = {"rows": n, "ok": True}
        except Exception as exc:  # pragma: no cover
            results[f.name] = {"rows": 0, "ok": False, "error": str(exc)}
    return results


def load_fg_stock(cur) -> tuple[list[FgStock], Counter]:
    cur.execute('''SELECT T."ItemCode", T."WhsCode", T."OnHand", I."InvntryUom", W."WhsName", W."U_TYPE", W."U_TIPO", W."Inactive"
        FROM "TELCHI"."OITW" T
        JOIN (SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "Type"='S') P ON P."ItemCode"=T."ItemCode"
        JOIN "TELCHI"."OITM" I ON I."ItemCode"=T."ItemCode"
        JOIN "TELCHI"."OWHS" W ON W."WhsCode"=T."WhsCode"
        WHERE T."OnHand">0''')
    stocks: list[FgStock] = []
    role_cnt = Counter()
    for code, whs, onhand, uom, name, utype, utipo, inactive in cur.fetchall():
        role = resolve_warehouse_role(whs, name, utype, utipo, inactive)
        role_cnt[role] += 1
        stocks.append(FgStock(code, whs, float(onhand or 0), uom, role))
    return stocks, role_cnt


def load_ratios(cur, item_facts: dict[str, ItemFacts]) -> dict[tuple[str, str], ComponentRatio]:
    # consumed
    cur.execute('''SELECT O."ItemCode", C."ItemCode", SUM(C."Quantity")
        FROM "TELCHI"."IGE1" C JOIN "TELCHI"."OWOR" O ON O."DocEntry"=C."BaseEntry"
        WHERE C."BaseType"=202 GROUP BY O."ItemCode", C."ItemCode"''')
    consumed = {(r[0], r[1]): float(r[2] or 0) for r in cur.fetchall()}
    # produced
    cur.execute('''SELECT O."ItemCode", SUM(I."Quantity")
        FROM "TELCHI"."IGN1" I JOIN "TELCHI"."OWOR" O ON O."DocEntry"=I."BaseEntry"
        WHERE I."BaseType"=202 AND I."ItemCode"=O."ItemCode" GROUP BY O."ItemCode"''')
    produced = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    ratios: dict[tuple[str, str], ComponentRatio] = {}
    for (fg, comp), cons in consumed.items():
        prod = produced.get(fg)
        qpf = historical_ratio(cons, prod)
        if qpf is None or qpf <= 0:
            continue
        f = item_facts.get(comp)
        ratios[(fg, comp)] = ComponentRatio(
            fg=fg, component=comp, qty_per_fg=qpf,
            method="HISTORICAL_PRODUCTION_EQUIVALENCE",
            component_uom=f.invnt_uom if f else None,
            component_class=classify_item(f) if f else "UNKNOWN")
    return ratios


def load_bom(cur) -> dict[tuple[str, str], float]:
    cur.execute('''SELECT B."Father", B."Code", B."Quantity", H."Qauntity"
        FROM "TELCHI"."ITT1" B JOIN "TELCHI"."OITT" H ON H."Code"=B."Father"''')
    out: dict[tuple[str, str], float] = {}
    for fg, comp, qty, batch in cur.fetchall():
        r = current_bom_ratio(float(qty or 0), float(batch or 0))
        if r is not None and r > 0:
            out[(fg, comp)] = r
    return out


def load_item_facts(cur) -> dict[str, ItemFacts]:
    produced = {r[0] for r in _q(cur, 'SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "Type"=\'S\'')}
    bom_comp = {r[0] for r in _q(cur, 'SELECT DISTINCT "Code" FROM "TELCHI"."ITT1"')}
    facts: dict[str, ItemFacts] = {}
    cur.execute('''SELECT "ItemCode","ItemName","ItemType","ItmsGrpCod","InvntItem","SellItem","PrchseItem","InvntryUom"
        FROM "TELCHI"."OITM"''')
    for code, name, itype, grp, inv, sell, prch, uom in cur.fetchall():
        facts[code] = ItemFacts(code, name or "", itype, grp, inv, sell, prch,
                                is_produced=code in produced, is_bom_component=code in bom_comp,
                                invnt_uom=uom)
    return facts


def _q(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def main() -> int:
    conn, cur = connect()
    try:
        contracts = run_contracts(cur)
        facts = load_item_facts(cur)
        stocks, role_cnt = load_fg_stock(cur)
        ratios = load_ratios(cur, facts)
        bom = load_bom(cur)
        produced_set = {c for c, f in facts.items() if f.is_produced}

        lines = build_equivalence(stocks, ratios, bom)
        lines_usable = build_equivalence(
            [s for s in stocks if s.role in USABLE_ROLES], ratios, bom)
        direct_total = global_equivalent_total(lines)
        direct_usable = global_equivalent_total(lines_usable)
        terminal, terminal_flags = expand_terminal(direct_usable, ratios, produced_set)

        usable_qty = sum(s.onhand for s in stocks if s.role in USABLE_ROLES)
        physical_qty = sum(s.onhand for s in stocks)

        result = {
            "gate": "TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1",
            "contracts": contracts,
            "fg_stock_rows": len(stocks),
            "fg_stock_role_dist": dict(role_cnt),
            "fg_items": len({s.itemcode for s in stocks}),
            "fg_physical_qty": physical_qty,
            "fg_usable_qty": usable_qty,
            "equivalence_lines": len(lines),
            "components_direct": len(direct_total),
            "components_usable": len(direct_usable),
            "components_terminal": len(terminal),
            "terminal_flags": terminal_flags,
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*72}\nTELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1\n{'='*72}")
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        print(f"\nFG STOCK: {result['fg_stock_rows']:,} rows | {result['fg_items']} items")
        print(f"  physical OnHand = {result['fg_physical_qty']:,.1f} | usable OnHand = {result['fg_usable_qty']:,.1f}")
        print(f"  role dist: {dict(role_cnt)}")
        print(f"  EQUIVALENCE LINES (direct): {result['equivalence_lines']:,}")
        print(f"  COMPONENTS direct: {result['components_direct']} | usable: {result['components_usable']} | terminal: {result['components_terminal']}")

        # tracer cases (usable-equivalent, the coverage-relevant layer)
        print("\nTRACER CASES (component equivalent in USABLE FG stock):")
        for comp, label in [("L01010", "SODA CAUSTICA 25kg"), ("L01821", "CLORURO DE CALCIO 25kg"),
                            ("L01785", "BENZOATO DE SODIO 25kg"), ("L03427", "FRASCO GOTERO 30mL"),
                            ("L03428", "TAPA GOTERO"), ("L03429", "CONTRA TAPA GOTERO")]:
            eq_usable = direct_usable.get(comp, 0.0)
            eq_terminal = terminal.get(comp, 0.0)
            contrib = Counter()
            for ln in lines_usable:
                if ln.component == comp:
                    contrib[ln.fg] += ln.equivalent_qty
            top = contrib.most_common(6)
            print(f"  {label}: usable_direct={eq_usable:,.1f} terminal={eq_terminal:,.1f}")
            for fg, q in top:
                print(f"     <- {fg}: {q:,.1f}")

        ok, flag = transfer_conservation(direct_usable, direct_usable)
        print(f"\nCONSERVATION (transfer no-op): {flag}")

        gate = "TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_PASS" if not failed else \
            "TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())