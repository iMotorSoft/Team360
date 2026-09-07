"""TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1 - validator (READ ONLY on HANA).

Executes the max-producible gate:
  1. SQL contracts (sql/current/capacity/*.sql)
  2. AVAILABLE_COMPONENT_FOR_PRODUCTION (raw warehouses, OnHand-IsCommited)
  3. requirement per FG-component (historical ratio + BOM fallback)
  4. terminal (multi-level) requirement expansion
  5. COMPONENT_CAPACITY + THEORETICAL_MAX_IF_PRIORITY + LIMITING_COMPONENT
  6. shared component detection
  7. tracer cases (gotero, soda, cloruro, benzoato)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.capacity.capacity_domain import (  # noqa: E402
    available_for_production, build_capacity, requirement_per_fg, shared_component_map,
)
from modules.telchi.investigation.validation.equivalence.equivalence_domain import current_bom_ratio  # noqa: E402

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "capacity"


def run_contracts(cur) -> dict:
    out = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        try:
            cur.execute(f.read_text(encoding="utf-8"))
            n = len(cur.fetchall())
            out[f.name] = {"rows": n, "ok": True}
        except Exception as exc:  # pragma: no cover
            out[f.name] = {"rows": 0, "ok": False, "error": str(exc)}
    return out


def load_availability(cur) -> dict[str, float]:
    cur.execute('''SELECT T."ItemCode", T."WhsCode", T."OnHand", T."IsCommited"
        FROM "TELCHI"."OITW" T
        JOIN (SELECT DISTINCT "Code" AS c FROM "TELCHI"."ITT1") B ON B.c=T."ItemCode"
        WHERE T."WhsCode" IN ('LAB-M1','SAA-M1','MAG-M1')''')
    rows = [(r[0], r[1], float(r[2] or 0), float(r[3] or 0)) for r in cur.fetchall()]
    return available_for_production(rows)


def load_requirement(cur) -> tuple[dict[tuple[str, str], float], dict[str, float]]:
    # consumed per order
    cur.execute('''SELECT O."ItemCode", C."ItemCode", SUM(C."Quantity")
        FROM "TELCHI"."IGE1" C JOIN "TELCHI"."OWOR" O ON O."DocEntry"=C."BaseEntry"
        WHERE C."BaseType"=202 GROUP BY O."ItemCode", C."ItemCode"''')
    consumed = {(r[0], r[1]): float(r[2] or 0) for r in cur.fetchall()}
    cur.execute('''SELECT O."ItemCode", SUM(I."Quantity")
        FROM "TELCHI"."IGN1" I JOIN "TELCHI"."OWOR" O ON O."DocEntry"=I."BaseEntry"
        WHERE I."BaseType"=202 AND I."ItemCode"=O."ItemCode" GROUP BY O."ItemCode"''')
    produced = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    return requirement_per_fg(consumed, produced), produced


def load_bom(cur) -> dict[tuple[str, str], float]:
    cur.execute('''SELECT B."Father", B."Code", B."Quantity", H."Qauntity"
        FROM "TELCHI"."ITT1" B JOIN "TELCHI"."OITT" H ON H."Code"=B."Father"''')
    out = {}
    for fg, comp, qty, batch in cur.fetchall():
        r = current_bom_ratio(float(qty or 0), float(batch or 0))
        if r is not None and r > 0:
            out[(fg, comp)] = r
    return out


def load_item_codes(cur) -> set[str]:
    cur.execute('SELECT "ItemCode" FROM "TELCHI"."OITM"')
    return {r[0] for r in cur.fetchall()}


def main() -> int:
    conn, cur = connect()
    try:
        contracts = run_contracts(cur)
        item_codes = load_item_codes(cur)
        available = load_availability(cur)
        direct_req, produced_map = load_requirement(cur)
        bom = load_bom(cur)

        # BOM fallback for FG with no production history ratio
        for k, v in bom.items():
            if k not in direct_req:
                direct_req[k] = v

        # filter noise: keep only real material components (in OITM, != FG)
        filtered = {}
        for (fg, comp), v in direct_req.items():
            if comp in item_codes and comp != fg and v > 0:
                filtered[(fg, comp)] = v
        direct_req = filtered

        produced_set = {fg for fg, p in produced_map.items()}
        produced_set |= {r[0] for r in _q(cur, 'SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "Type"=\'S\'')}

        fg_universe = sorted({k[0] for k in direct_req})
        smap = shared_component_map(direct_req)

        capacities = {}
        for fg in fg_universe:
            cap = build_capacity(fg, direct_req, available, produced_set)
            capacities[fg] = cap

        # summary
        n_fg = len(fg_universe)
        n_with_limiting = sum(1 for c in capacities.values() if c.limiting_component is not None)
        shared = {c for c, fgs in smap.items() if len(fgs) > 1}

        result = {
            "gate": "TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1",
            "contracts": contracts,
            "fg_universe": n_fg,
            "fg_with_capacity": n_with_limiting,
            "components_available": len(available),
            "shared_components": len(shared),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*72}\nTELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1\n{'='*72}")
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")
        print(f"FG UNIVERSE: {n_fg} | with capacity: {n_with_limiting}")
        print(f"COMPONENTS available (raw whs): {len(available)} | shared: {len(shared)}")

        # tracer: gotero (which FG use it, capacity)
        print("\nTRACER GOTERO (L03427 FRASCO GOTERO 30mL):")
        gotero_fgs = sorted(smap.get("L03427", set()))
        print(f"  used by {len(gotero_fgs)} FG")
        for fg in gotero_fgs[:8]:
            cap = capacities.get(fg)
            if cap and "L03427" in cap.capacity_by_component:
                c = cap.capacity_by_component["L03427"]
                print(f"    {fg}: gotero_capacity={c:,.0f} immediate_max={cap.immediate_max:,.0f} "
                      f"limiting={cap.limiting_component}")

        # tracer materials -> FG capacity
        names = {r[0]: r[1] for r in _q(cur, 'SELECT "ItemCode","ItemName" FROM "TELCHI"."OITM"')}
        print("\nTRACER MATERIALS (physical avail -> FG capacity):")
        for comp, label in [("L01010", "SODA CAUSTICA 25kg"), ("L01821", "CLORURO DE CALCIO 25kg"),
                            ("L01785", "BENZOATO 25kg")]:
            fgs = sorted({k[0] for k in direct_req if k[1] == comp})
            print(f"  {label}: physical_avail={available.get(comp,0):,.1f} used by {len(fgs)} FG")
            for fg in fgs[:6]:
                cap = capacities.get(fg)
                cc = cap.capacity_by_component.get(comp) if cap else None
                if cc is not None:
                    print(f"    {fg} {names.get(fg,'')[:35]}: comp_cap={cc:,.0f} "
                          f"limiting={cap.limiting_component} {names.get(cap.limiting_component,'')[:28]}")

        # top FG by immediate max (sample)
        print("\nSAMPLE FG CAPACITY (top 15 by immediate max):")
        ranked = sorted(capacities.values(), key=lambda c: -c.immediate_max)[:15]
        for c in ranked:
            print(f"  {c.fg}: max={c.immediate_max:,.0f} limiting={c.limiting_component} "
                  f"expanded={c.expanded_max:,.0f}")

        gate = "TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_PASS" if not failed else \
            "TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


def _q(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


if __name__ == "__main__":
    sys.exit(main())