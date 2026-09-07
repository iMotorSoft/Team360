"""TELCHI_PURCHASE_RISK_ENGINE_V1 - validator (READ ONLY on HANA).

Converts Gate 7 coverage positions into explainable purchase decisions:
  BUY_NOW / BUY_SOON / WATCH / SAFE / DO_NOT_BUY / EXCESS_STOCK
plus risk flags PRODUCTION_BLOCKED / IMPORT_DELAY_RISK / SUPPLIER_RISK.

No opaque score: every decision derives from visible variables (coverage,
stockout month, lead time p90, open purchase, supply confidence, seasonality,
component criticality, shared-component exposure).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402

from modules.telchi.investigation.validation.coverage import coverage_domain as cov  # noqa: E402
from modules.telchi.investigation.validation.coverage.equivalent_material_coverage_v1 import (  # noqa: E402
    SNAPSHOT, TRACER_MATERIALS, forecast_method_for, load_bom, load_fg_usable,
    load_open_purchase,
)
from modules.telchi.investigation.validation.stock.stock_domain import (  # noqa: E402
    ITEM_PACKAGING, classify_item,
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
    build_equivalence, expand_terminal, global_equivalent_total,
)
from modules.telchi.investigation.validation.equivalence.finished_goods_material_equivalence_v1 import (  # noqa: E402
    USABLE_ROLES, load_fg_stock, load_item_facts, load_ratios,
)
from modules.telchi.investigation.validation.seasonality.seasonality_validator import load_monthly  # noqa: E402
from modules.telchi.investigation.validation.lead_time.purchase_lead_time_v1 import load_events  # noqa: E402
from modules.telchi.investigation.validation.lead_time.lead_time_domain import (  # noqa: E402
    classify_procurement_mode, sample_confidence, summarize,
)
from modules.telchi.investigation.validation.risk.risk_domain import (  # noqa: E402
    DEC_BUY_NOW, DEC_BUY_SOON, MaterialRiskInput, classify_material,
    decision_priority,
)

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "risk"


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


def load_open_import_items(cur) -> set[str]:
    cur.execute('''SELECT DISTINCT P."ItemCode" FROM "TELCHI"."POR1" P
        JOIN "TELCHI"."OPOR" O ON O."DocEntry"=P."DocEntry"
        WHERE O."CANCELED"='N' AND O."DocStatus"='O' AND P."OpenQty">0
          AND O."U_TIPOCOMPRA"='IMP' ''')
    return {r[0] for r in cur.fetchall()}


def build_components(cur):
    facts = load_item_facts(cur)
    produced_set = {c for c, f in facts.items() if f.is_produced}
    available = load_availability(cur)
    direct_req, produced_map = load_requirement(cur)
    bom = load_bom(cur)
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

    comp_to_fgs: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (fg, comp), q in terminal_req.items():
        comp_to_fgs[comp].append((fg, q))
    smap = shared_component_map(terminal_req)
    shared = {c for c, fgs in smap.items() if len(fgs) > 1}

    stocks, role_cnt = load_fg_stock(cur)
    ratios = load_ratios(cur, facts)
    lines_usable = build_equivalence([s for s in stocks if s.role in USABLE_ROLES], ratios, bom)
    direct_usable = global_equivalent_total(lines_usable)
    terminal_equiv, _ = expand_terminal(direct_usable, ratios, produced_set)

    open_purchase, reconcile = load_open_purchase(cur)

    return (facts, produced_set, available, terminal_req, comp_to_fgs, shared,
            additional_producible, limiting, terminal_equiv, open_purchase)


def build_forecast(series):
    fg_forecast: dict[str, dict[tuple[int, int], float]] = {}
    patterns: dict[str, sd.DemandProfile] = {}
    start_y, start_m = cov.month_add(SNAPSHOT[0], SNAPSHOT[1], 1)
    for fg, s in series.items():
        p = sd.classify(s, SNAPSHOT[0], SNAPSHOT[1])
        p.itemcode = fg
        patterns[fg] = p
        fn = fc.FORECAST_METHODS[forecast_method_for(p.pattern)]
        fg_forecast[fg] = cov.build_forward_forecast(
            lambda y, m: fn(s, y, m), start_y, start_m, 12)
    return fg_forecast, patterns


def main() -> int:
    conn, cur = connect()
    try:
        contracts = run_contracts(cur)
        (facts, produced_set, available, terminal_req, comp_to_fgs, shared,
         additional_producible, limiting, terminal_equiv, open_purchase) = build_components(cur)

        events = load_events(cur)
        item_days = defaultdict(list)
        purchased_items: set[str] = set()
        item_import_hist: dict[str, bool] = defaultdict(bool)
        for e in events:
            if e.item_code:
                purchased_items.add(e.item_code)
                if e.tipo_compra == "IMP":
                    item_import_hist[e.item_code] = True
                if e.first_lead_days is not None:
                    item_days[e.item_code].append(e.first_lead_days)
        item_lead = {i: summarize(d) for i, d in item_days.items()}
        import_open = load_open_import_items(cur)

        fg_usable = load_fg_usable(cur, facts)
        series = load_monthly(cur)
        fg_forecast, patterns = build_forecast(series)

        # component coverage
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

        # FG coverage (for PRODUCTION_BLOCKED + affected-FG coverage)
        fg_covs: dict[str, cov.FgCoverage] = {}
        for fg in produced_set:
            supply = fg_usable.get(fg, 0.0) + additional_producible.get(fg, 0.0)
            fc_demand = fg_forecast.get(fg, {})
            if supply <= 0 and sum(fc_demand.values()) <= 0:
                continue
            demand = [(y, m, q) for (y, m), q in fc_demand.items() if q > 0]
            fg_covs[fg] = cov.run_fg_waterfall(fg, demand, fg_usable.get(fg, 0.0),
                                               additional_producible.get(fg, 0.0))

        # recommendations
        recs = []
        for comp, cc in comp_covs.items():
            is_produced = comp in produced_set
            is_purchased = comp in purchased_items
            mode = classify_procurement_mode(is_purchased, is_produced)
            if mode == "PRODUCED":
                continue  # risk lives in terminal components, not a purchase decision
            stats = item_lead.get(comp, {"p90": None, "n": 0})
            lt_p90 = stats.get("p90")
            supplier_conf = sample_confidence(stats.get("n", 0))
            import_cls = "IMPORT_OR_LOGISTICS" if (comp in import_open or item_import_hist.get(comp)) else "LOCAL_GENERAL"
            is_pack = classify_item(facts.get(comp)) == ITEM_PACKAGING
            affected_fgs = [fg for fg, _ in comp_to_fgs.get(comp, [])]
            pats = [patterns.get(fg).pattern for fg in affected_fgs if fg in patterns]
            declining = bool(pats) and all(p in (sd.PATTERN_DECLINING, sd.PATTERN_DISCONTINUED) for p in pats)
            uncertain = any(p in (sd.PATTERN_INSUFFICIENT, sd.PATTERN_NEW, sd.PATTERN_INTERMITTENT) for p in pats) \
                or any((patterns.get(fg).confidence == "LOW") for fg in affected_fgs if fg in patterns)

            inp = MaterialRiskInput(
                component=comp, physical_available=cc.physical_available,
                equivalent_in_fg=cc.equivalent_in_fg, open_purchase=cc.open_purchase,
                total_required=cc.total_required, stockout_month=cc.stockout_month,
                covered_through_month=cc.covered_through_month, lead_time_p90=lt_p90,
                procurement_mode=mode, import_class=import_cls,
                supplier_confidence=supplier_conf, is_shared=comp in shared,
                is_packaging=is_pack, forecast_uncertain=uncertain,
                declining_or_discontinued=declining)
            rec = classify_material(inp, SNAPSHOT)
            recs.append((rec, inp, affected_fgs, pats))

        recs.sort(key=lambda t: decision_priority(t[0].decision))

        # production blocked (FG-level): packaging is the limiting component
        blocked = []
        for fg, cc in fg_covs.items():
            if cc.stockout_month is None:
                continue
            lim = limiting.get(fg)
            if lim and classify_item(facts.get(lim)) == ITEM_PACKAGING:
                blocked.append({"fg": fg, "limiting_packaging": lim,
                                "stockout_month": list(cc.stockout_month),
                                "usable_fg": cc.usable_fg,
                                "additional_producible": cc.additional_producible})

        out_recs = []
        for rec, inp, affected_fgs, pats in recs:
            out_recs.append({
                **rec.to_dict(),
                "material_name": facts[rec.component].itemname if rec.component in facts else None,
                "physical_available": round(inp.physical_available, 2),
                "equivalent_in_fg": round(inp.equivalent_in_fg, 2),
                "open_purchase": round(inp.open_purchase, 2),
                "total_required": round(inp.total_required, 2),
                "lead_time_p90": inp.lead_time_p90,
                "supply_confidence": inp.supplier_confidence,
                "procurement_mode": inp.procurement_mode,
                "import_class": inp.import_class,
                "is_shared": inp.is_shared,
                "affected_fg": affected_fgs,
                "fg_patterns": sorted(set(pats)),
                "stockout_month": list(inp.stockout_month) if inp.stockout_month else None,
                "covered_through_month": list(inp.covered_through_month) if inp.covered_through_month else None,
            })

        dec_cnt = Counter(r["decision"] for r in out_recs)

        result = {
            "gate": "TELCHI_PURCHASE_RISK_ENGINE_V1",
            "snapshot": list(SNAPSHOT),
            "contracts": contracts,
            "materials_evaluated": len(out_recs),
            "decision_dist": dict(dec_cnt),
            "production_blocked_fg": blocked,
            "recommendations": out_recs,
        }
        print(json.dumps(result, indent=2, default=str))

        # human-readable report
        print(f"\n{'='*72}\nTELCHI_PURCHASE_RISK_ENGINE_V1\n{'='*72}")
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        print(f"\nMATERIALS EVALUATED: {len(out_recs)}")
        print(f"DECISION DIST: {dict(dec_cnt)}")

        print("\nTOP RECOMMENDATIONS (BUY_NOW / BUY_SOON):")
        urgent = [r for r in out_recs if r["decision"] in (DEC_BUY_NOW, DEC_BUY_SOON)]
        for r in urgent[:25]:
            print(f"  [{r['decision']}] {r['component']} ({r['material_name'][:32]}) "
                  f"stockout={r['stockout_month']} lso={r['latest_safe_order_month']} "
                  f"lt_p90={r['lead_time_p90']} phys={r['physical_available']:,.0f} "
                  f"open={r['open_purchase']:,.0f} FG={len(r['affected_fg'])} "
                  f"flags={r['flags']}")

        print(f"\nPRODUCTION BLOCKED (packaging limiting, FG will stockout): {len(blocked)}")
        for b in blocked[:15]:
            print(f"  {b['fg']} <- {b['limiting_packaging']} stockout={b['stockout_month']}")

        print("\nTRACER RECOMMENDATIONS:")
        for comp, label in TRACER_MATERIALS.items():
            row = next((r for r in out_recs if r["component"] == comp), None)
            if row:
                print(f"  {label}: {row['decision']} lso={row['latest_safe_order_month']} "
                      f"stockout={row['stockout_month']} flags={row['flags']} conf={row['confidence']}")

        gate = "TELCHI_PURCHASE_RISK_ENGINE_V1_PASS" if not failed else \
            "TELCHI_PURCHASE_RISK_ENGINE_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
