"""TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1 - validator (READ ONLY on HANA).

Executes the equivalent-material coverage gate (Gate 7):

  1. SQL contracts (sql/current/coverage/*.sql)
  2. P0.2 reconcile OPEN_PURCHASE_POSITION vs OITW.OnOrder (anti double count)
  3. Layer A: USABLE_FG (OnHand - IsCommited, usable roles)
  4. Layer B: PHYSICAL_COMPONENT_STOCK (raw warehouses)
  5. Layer C: EQUIVALENT_IN_FG (terminal, usable) — never reused to produce
  6. Layer D: ADDITIONAL_PRODUCIBLE_FG (MAX_PRODUCIBLE terminal expansion)
  7. Layer E: OPEN_PURCHASE_POSITION (doc-linked, confidence DOCUMENTED_ORDER)
  8. Layer F: monthly forecast (Gate 6) + forward forecast
  9. FG month-by-month waterfall -> stockout month / coverage
  10. Component aggregate requirement + physical coverage + lead-time gap
  11. Tracers: L03124 bronceador + soda/cloruro/benzoato/gotero
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402

from modules.telchi.investigation.validation.coverage import coverage_domain as cov  # noqa: E402
from modules.telchi.investigation.validation.stock.stock_domain import (  # noqa: E402
    ItemFacts, resolve_warehouse_role,
)
from modules.telchi.investigation.validation.seasonality import forecast as fc  # noqa: E402
from modules.telchi.investigation.validation.seasonality import seasonality_domain as sd  # noqa: E402
from modules.telchi.investigation.validation.capacity.capacity_domain import (  # noqa: E402
    build_capacity, expand_requirement_terminal, shared_component_map,
)
from modules.telchi.investigation.validation.capacity.max_producible_by_component_v1 import (  # noqa: E402
    load_availability, load_requirement,
)
from modules.telchi.investigation.validation.equivalence.equivalence_domain import (  # noqa: E402
    build_equivalence, current_bom_ratio, expand_terminal, global_equivalent_total,
)
from modules.telchi.investigation.validation.equivalence.finished_goods_material_equivalence_v1 import (  # noqa: E402
    USABLE_ROLES, load_fg_stock, load_item_facts, load_ratios,
)
from modules.telchi.investigation.validation.seasonality.seasonality_validator import load_monthly  # noqa: E402
from modules.telchi.investigation.validation.lead_time.purchase_lead_time_v1 import load_events  # noqa: E402
from modules.telchi.investigation.validation.lead_time.lead_time_domain import summarize  # noqa: E402

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "coverage"

SNAPSHOT = (2026, 8)
FORECAST_START = (2026, 9)
HORIZON_MONTHS = 12

TRACER_MATERIALS = {
    "L01010": "SODA CAUSTICA 25kg",
    "L01821": "CLORURO DE CALCIO 25kg",
    "L01785": "BENZOATO DE SODIO 25kg",
    "L03427": "FRASCO GOTERO 30mL",
    "L03428": "TAPA GOTERO 30mL",
    "L03429": "CONTRA TAPA GOTERO 30mL",
}
CRITICAL_LEAD_COMPONENTS = ("L00205", "L00838", "L00219", "L00097")
BRONCEADOR = "L03124"
BRONCEADOR_SEASON_END = 2  # feb
BRONCEADOR_PEAK = 1  # ene


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


def load_bom(cur) -> dict[tuple[str, str], float]:
    cur.execute('''SELECT B."Father", B."Code", B."Quantity", H."Qauntity"
        FROM "TELCHI"."ITT1" B JOIN "TELCHI"."OITT" H ON H."Code"=B."Father"''')
    out = {}
    for fg, comp, qty, batch in cur.fetchall():
        r = current_bom_ratio(float(qty or 0), float(batch or 0))
        if r is not None and r > 0:
            out[(fg, comp)] = r
    return out


def load_fg_usable(cur, facts: dict[str, ItemFacts]) -> dict[str, float]:
    """Layer A: usable FG units per FG = SUM(OnHand - IsCommited) over usable
    warehouse roles, floored at 0 per FG."""
    cur.execute('''SELECT T."ItemCode", T."WhsCode", T."OnHand", T."IsCommited",
        W."WhsName", W."U_TYPE", W."U_TIPO", W."Inactive"
        FROM "TELCHI"."OITW" T
        JOIN (SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "Type"='S') P
            ON P."ItemCode"=T."ItemCode"
        JOIN "TELCHI"."OWHS" W ON W."WhsCode"=T."WhsCode"
        WHERE T."OnHand">0 OR T."IsCommited">0''')
    acc = defaultdict(float)
    for code, whs, onhand, committed, name, utype, utipo, inactive in cur.fetchall():
        role = resolve_warehouse_role(whs, name, utype, utipo, inactive)
        if role not in USABLE_ROLES:
            continue
        acc[code] += float(onhand or 0) - float(committed or 0)
    return {fg: max(0.0, v) for fg, v in acc.items()}


def load_open_purchase(cur) -> tuple[dict[str, float], list[dict]]:
    """Layer E canonical open purchase per item + reconciliation vs OnOrder."""
    cur.execute('''SELECT P."ItemCode", SUM(P."OpenQty"),
        COALESCE((SELECT SUM(T."OnOrder") FROM "TELCHI"."OITW" T
                  WHERE T."ItemCode"=P."ItemCode"), 0)
        FROM "TELCHI"."POR1" P JOIN "TELCHI"."OPOR" O ON O."DocEntry"=P."DocEntry"
        WHERE O."CANCELED"='N' AND O."DocStatus"='O' AND P."OpenQty">0
        GROUP BY P."ItemCode"''')
    open_qty: dict[str, float] = {}
    reconcile: list[dict] = []
    for item, op, oo in cur.fetchall():
        op = float(op or 0)
        oo = float(oo or 0)
        open_qty[item] = op
        reconcile.append({"item": item, "open_purchase": op, "onorder": oo,
                          "match": abs(op - oo) < 1e-6})
    return open_qty, reconcile


def load_item_lead_time(cur) -> dict[str, int]:
    """p90 first-receipt lead time (days) per item, from Gate 5 events."""
    item_days = defaultdict(list)
    for e in load_events(cur):
        if e.first_lead_days is not None and e.item_code:
            item_days[e.item_code].append(e.first_lead_days)
    return {item: (summarize(days).get("p90") or 0) for item, days in item_days.items()}


def forecast_method_for(pattern: str) -> str:
    if pattern in (sd.PATTERN_SEASONAL, sd.PATTERN_STABLE, sd.PATTERN_INTERMITTENT):
        return fc.METHOD_SEASONAL_MA
    if pattern in (sd.PATTERN_GROWING, sd.PATTERN_DECLINING):
        return fc.METHOD_YOY
    return fc.METHOD_NAIVE


def _q(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def main() -> int:
    conn, cur = connect()
    try:
        contracts = run_contracts(cur)
        facts = load_item_facts(cur)
        produced_set = {c for c, f in facts.items() if f.is_produced}

        # ---- Layers -------------------------------------------------------
        fg_usable = load_fg_usable(cur, facts)                       # A
        available = load_availability(cur)                           # B
        direct_req, produced_map = load_requirement(cur)             # raw ratios
        bom = load_bom(cur)                                          # BOM fallback
        for k, v in bom.items():
            if k not in direct_req:
                direct_req[k] = v
        filtered = {(fg, comp): v for (fg, comp), v in direct_req.items()
                    if comp in facts and comp != fg and v > 0}

        terminal_req: dict[tuple[str, str], float] = {}
        additional_producible: dict[str, float] = {}
        limiting: dict[str, str | None] = {}
        for fg in sorted({k[0] for k in filtered}):
            cap = build_capacity(fg, filtered, available, produced_set)
            additional_producible[fg] = cap.expanded_max
            limiting[fg] = cap.terminal_limiting_component
            for comp, q in expand_requirement_terminal(fg, filtered, produced_set).items():
                terminal_req[(fg, comp)] = q

        # Layer C: equivalent-in-FG (terminal, usable)
        stocks, role_cnt = load_fg_stock(cur)
        ratios = load_ratios(cur, facts)
        lines_usable = build_equivalence(
            [s for s in stocks if s.role in USABLE_ROLES], ratios, bom)
        direct_usable = global_equivalent_total(lines_usable)
        terminal_equiv, terminal_flags = expand_terminal(direct_usable, ratios, produced_set)

        # Layer E: open purchase + reconciliation
        open_purchase, reconcile = load_open_purchase(cur)

        # Lead time p90 per item
        item_lead = load_item_lead_time(cur)

        # Layer F: monthly series + pattern + forward forecast
        series = load_monthly(cur)
        fg_forecast: dict[str, dict[tuple[int, int], float]] = {}
        patterns: dict[str, sd.DemandProfile] = {}
        for fg, s in series.items():
            p = sd.classify(s, SNAPSHOT[0], SNAPSHOT[1])
            p.itemcode = fg
            patterns[fg] = p
            fn = fc.FORECAST_METHODS[forecast_method_for(p.pattern)]
            fg_forecast[fg] = cov.build_forward_forecast(
                lambda y, m: fn(s, y, m), FORECAST_START[0], FORECAST_START[1],
                HORIZON_MONTHS)

        # ---- FG waterfall -------------------------------------------------
        fg_covs: dict[str, cov.FgCoverage] = {}
        for fg in produced_set:
            supply = fg_usable.get(fg, 0.0) + additional_producible.get(fg, 0.0)
            fc_demand = fg_forecast.get(fg, {})
            total_demand = sum(fc_demand.values())
            if supply <= 0 and total_demand <= 0:
                continue
            demand = [(y, m, q) for (y, m), q in fc_demand.items() if q > 0]
            fg_covs[fg] = cov.run_fg_waterfall(
                fg, demand, fg_usable.get(fg, 0.0),
                additional_producible.get(fg, 0.0))

        n_analyzed = len(fg_covs)
        n_stockout = sum(1 for c in fg_covs.values() if c.stockout_month is not None)
        n_fully = n_analyzed - n_stockout

        # ---- Component coverage ------------------------------------------
        comp_to_fgs: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for (fg, comp), q in terminal_req.items():
            comp_to_fgs[comp].append((fg, q))
        smap = shared_component_map(terminal_req)
        shared = {c for c, fgs in smap.items() if len(fgs) > 1}

        comp_covs: dict[str, cov.ComponentCoverage] = {}
        for comp, pairs in comp_to_fgs.items():
            req = defaultdict(float)
            for fg, qpf in pairs:
                for (y, m), qty in fg_forecast.get(fg, {}).items():
                    if qty > 0:
                        req[(y, m)] += qty * qpf
            if not req and available.get(comp, 0) <= 0 and terminal_equiv.get(comp, 0) <= 0 \
                    and open_purchase.get(comp, 0) <= 0:
                continue
            cc = cov.run_component_waterfall(comp, dict(req), available.get(comp, 0.0))
            cc.equivalent_in_fg = terminal_equiv.get(comp, 0.0)
            cc.open_purchase = open_purchase.get(comp, 0.0)
            comp_covs[comp] = cc

        n_comps = len(comp_covs)
        comp_gap = []
        for comp, cc in comp_covs.items():
            lt = item_lead.get(comp)
            if lt is None:
                continue
            hdays = cov.horizon_days(SNAPSHOT, cc.covered_through_month)
            gap = cov.lead_time_coverage_gap(hdays, lt)
            if gap is not None and gap < 0:
                comp_gap.append({"component": comp, "coverage_days": hdays,
                                 "lead_time_p90": lt, "gap": gap})

        # ---- Tracers ------------------------------------------------------
        bronceador = {}
        if BRONCEADOR in fg_covs:
            c = fg_covs[BRONCEADOR]
            fc_bron = fg_forecast.get(BRONCEADOR, {})
            season_end = cov.month_add(FORECAST_START[0], FORECAST_START[1], 0)
            # season sep..feb (within forecast window)
            dem_season = cov.sum_demand_to(fc_bron, FORECAST_START, (2027, BRONCEADOR_SEASON_END))
            dem_peak = cov.sum_demand_to(fc_bron, FORECAST_START, (2027, BRONCEADOR_PEAK))
            bronceador = {
                "usable_fg": c.usable_fg,
                "additional_producible": c.additional_producible,
                "limiting_component": limiting.get(BRONCEADOR),
                "forecast_sep_feb": {f"{y}-{m:02d}": round(q, 1) for (y, m), q in sorted(fc_bron.items()) if (y, m) <= (2027, 2)},
                "demand_to_season_end": round(dem_season, 1),
                "demand_to_next_peak": round(dem_peak, 1),
                "coverage_to_season_end": cov.coverage_ratio(c.total_supply, dem_season),
                "coverage_to_next_peak": cov.coverage_ratio(c.total_supply, dem_peak),
                "stockout_month": list(c.stockout_month) if c.stockout_month else None,
                "covered_through_month": list(c.covered_through_month) if c.covered_through_month else None,
                "pattern": patterns.get(BRONCEADOR).pattern if BRONCEADOR in patterns else None,
            }

        tracers = {}
        for comp, label in TRACER_MATERIALS.items():
            cc = comp_covs.get(comp)
            lt = item_lead.get(comp)
            tracers[label] = {
                "component": comp,
                "physical_available": available.get(comp, 0.0),
                "equivalent_in_fg": terminal_equiv.get(comp, 0.0),
                "open_purchase": open_purchase.get(comp, 0.0),
                "dependent_fg": len(comp_to_fgs.get(comp, [])),
                "monthly_requirement": {f"{y}-{m:02d}": round(q, 2) for (y, m), q in sorted((cc.monthly_requirement if cc else {}).items())},
                "covered_through_month": list(cc.covered_through_month) if cc and cc.covered_through_month else None,
                "stockout_month": list(cc.stockout_month) if cc and cc.stockout_month else None,
                "lead_time_p90": lt,
                "lead_time_gap": cov.lead_time_coverage_gap(
                    cov.horizon_days(SNAPSHOT, cc.covered_through_month), lt) if cc else None,
            }

        result = {
            "gate": "TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1",
            "snapshot": list(SNAPSHOT),
            "contracts": contracts,
            "reconcile_open_vs_onorder": {
                "items_with_open_po": len(reconcile),
                "exact_match": sum(1 for r in reconcile if r["match"]),
                "mismatch": sum(1 for r in reconcile if not r["match"]),
            },
            "fg_analyzed": n_analyzed,
            "fg_fully_covered": n_fully,
            "fg_with_stockout": n_stockout,
            "components_analyzed": n_comps,
            "components_with_lead_time_gap": len(comp_gap),
            "shared_components": len(shared),
            "bronceador": bronceador,
            "tracers": tracers,
            "lead_time_gap_components": comp_gap[:30],
        }
        print(json.dumps(result, indent=2, default=str))

        # ---- human-readable report ----------------------------------------
        print(f"\n{'='*72}\nTELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1\n{'='*72}")
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        print(f"\nOPEN PURCHASE vs ONORDER (P0.2 reconciliation):")
        print(f"  items with open PO = {len(reconcile)} | exact match = "
              f"{result['reconcile_open_vs_onorder']['exact_match']} | "
              f"mismatch = {result['reconcile_open_vs_onorder']['mismatch']}")
        print(f"  (mismatch = UOM conversion + OnOrder sources beyond open POs; "
              f"canonical future-order qty = OPEN_PURCHASE)")

        print(f"\nFG COVERAGE: analyzed={n_analyzed} fully_covered={n_fully} "
              f"stockout={n_stockout}")
        print(f"COMPONENT COVERAGE: analyzed={n_comps} lead_time_gap={len(comp_gap)} "
              f"shared={len(shared)}")

        print(f"\nBRONCEADOR {BRONCEADOR} ({bronceador.get('pattern')}):")
        if bronceador:
            print(f"  usable_fg={bronceador['usable_fg']:,.0f} "
                  f"additional_producible={bronceador['additional_producible']:,.0f} "
                  f"limiting={bronceador['limiting_component']}")
            print(f"  coverage_to_season_end={bronceador['coverage_to_season_end']} "
                  f"coverage_to_next_peak={bronceador['coverage_to_next_peak']}")
            print(f"  stockout_month={bronceador['stockout_month']} "
                  f"covered_through={bronceador['covered_through_month']}")

        print("\nTRACER MATERIAL POSITION (physical | equivalent_in_FG | open_purchase):")
        for label, t in tracers.items():
            print(f"  {label}: physical={t['physical_available']:,.1f} "
                  f"equiv_in_fg={t['equivalent_in_fg']:,.1f} "
                  f"open_purchase={t['open_purchase']:,.1f} "
                  f"FG={t['dependent_fg']} lt_p90={t['lead_time_p90']} "
                  f"gap={t['lead_time_gap']} covered_through={t['covered_through_month']}")

        gate = "TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_PASS" if not failed else \
            "TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
