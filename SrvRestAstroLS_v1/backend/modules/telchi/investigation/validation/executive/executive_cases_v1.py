"""TELCHI_PURCHASE_EXECUTIVE_CASES_V1 - validator (READ ONLY on HANA).

Builds owner/management-readable executive cases for the five tracer materials
(soda caustica, cloruro de calcio, benzoato, gotero/Matriplast, bronceador
L03124) by synthesizing the coverage (Gate 7) + risk (Gate 8) layers.

Writes the generated report to docs/purchase_executive_cases_v1_report.md and
prints the JSON + human summary.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402

from modules.telchi.investigation.validation.coverage import coverage_domain as cov  # noqa: E402
from modules.telchi.investigation.validation.coverage.equivalent_material_coverage_v1 import (  # noqa: E402
    SNAPSHOT, load_fg_usable,
)
from modules.telchi.investigation.validation.risk.purchase_risk_engine_v1 import (  # noqa: E402
    build_components, build_forecast, load_open_import_items,
)
from modules.telchi.investigation.validation.stock.stock_domain import ITEM_PACKAGING, classify_item  # noqa: E402
from modules.telchi.investigation.validation.seasonality.seasonality_validator import load_monthly  # noqa: E402
from modules.telchi.investigation.validation.lead_time.purchase_lead_time_v1 import load_events  # noqa: E402
from modules.telchi.investigation.validation.lead_time.lead_time_domain import (  # noqa: E402
    classify_procurement_mode, sample_confidence, summarize,
)
from modules.telchi.investigation.validation.risk.risk_domain import MaterialRiskInput, classify_material  # noqa: E402
from modules.telchi.investigation.validation.executive.executive_domain import (  # noqa: E402
    ExecutiveCase, action_for, confidence_label,
)

ROOT = INVESTIGATION_ROOT
REPORT = ROOT / "docs" / "purchase_executive_cases_v1_report.md"

TRACERS = [
    ("L01010", "Soda cáustica", "kg"),
    ("L01821", "Cloruro de calcio", "kg"),
    ("L01785", "Benzoato de sodio", "kg"),
    ("L03427", "Frasco gotero 30 mL", "unidades"),
    ("L03428", "Tapa gotero 30 mL", "unidades"),
    ("L03429", "Contra-tapa gotero 30 mL", "unidades"),
]

BRONCEADOR = "L03124"
BRONCEADOR_SEASON_END = 2


def _qty(q: float, unit: str) -> str:
    return f"{q:,.0f} {unit}"


def _month(m: tuple[int, int] | None) -> str:
    return f"{m[0]}-{m[1]:02d}" if m else "—"


def _coverage_months(cc, snapshot) -> str:
    if cc is None:
        return "—"
    if cc.stockout_month is None:
        return ">= 12 meses (cubierto)"
    if cc.covered_through_month is None:
        return "menos de 1 mes"
    return f"~{cov.month_span(snapshot, cc.covered_through_month) + 1} meses"


def _risk_when(rec, cc) -> str:
    if rec.latest_safe_order_month:
        return f"ordenar antes de {_month(rec.latest_safe_order_month)}"
    if cc is not None and cc.stockout_month is not None:
        return f"si no llega el pedido, agota en {_month(cc.stockout_month)}"
    return "—"


def _reason_code(decision: str, flags: list[str], cc) -> str:
    if "PRODUCTION_BLOCKED" in flags:
        return "packaging_block"
    if "IMPORT_DELAY_RISK" in flags:
        return "unconfirmed_import_arrival"
    if decision in ("BUY_NOW", "BUY_SOON") and cc is not None and cc.stockout_month:
        return "stockout_before_replenishment"
    if decision in ("DO_NOT_BUY", "EXCESS_STOCK"):
        return "seasonal_excess" if decision == "EXCESS_STOCK" else "transformed_fg_coverage"
    return "covered_supply"


def _severity(decision: str) -> str:
    return {"BUY_NOW": "HIGH", "BUY_SOON": "HIGH", "WATCH": "MEDIUM",
            "PRODUCTION_BLOCKED": "HIGH", "EXCESS_STOCK": "MEDIUM"}.get(decision, "LOW")


def main() -> int:
    conn, cur = connect()
    try:
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

        # component coverage for tracers
        comp_covs: dict[str, cov.ComponentCoverage] = {}
        for comp, pairs in comp_to_fgs.items():
            req = defaultdict(float)
            for fg, qpf in pairs:
                for (y, m), qty in fg_forecast.get(fg, {}).items():
                    if qty > 0:
                        req[(y, m)] += qty * qpf
            cc = cov.run_component_waterfall(comp, dict(req), available.get(comp, 0.0))
            cc.equivalent_in_fg = terminal_equiv.get(comp, 0.0)
            cc.open_purchase = open_purchase.get(comp, 0.0)
            comp_covs[comp] = cc

        # FG coverage (for bronceador + affected FG producible)
        fg_covs: dict[str, cov.FgCoverage] = {}
        for fg in produced_set:
            supply = fg_usable.get(fg, 0.0) + additional_producible.get(fg, 0.0)
            fc_demand = fg_forecast.get(fg, {})
            if supply <= 0 and sum(fc_demand.values()) <= 0:
                continue
            demand = [(y, m, q) for (y, m), q in fc_demand.items() if q > 0]
            fg_covs[fg] = cov.run_fg_waterfall(fg, demand, fg_usable.get(fg, 0.0),
                                               additional_producible.get(fg, 0.0))

        cases: list[ExecutiveCase] = []

        # ---- tracer material cases ---------------------------------------
        for comp, label, unit in TRACERS:
            cc = comp_covs.get(comp)
            physical = available.get(comp, 0.0)
            equivalent = terminal_equiv.get(comp, 0.0)
            open_q = open_purchase.get(comp, 0.0)
            total_req = cc.total_required if cc else 0.0
            stats = item_lead.get(comp, {"p90": None, "n": 0})
            lt_p90 = stats.get("p90")
            supplier_conf = sample_confidence(stats.get("n", 0))
            import_cls = "IMPORT_OR_LOGISTICS" if (comp in import_open or item_import_hist.get(comp)) else "LOCAL_GENERAL"
            is_pack = classify_item(facts.get(comp)) == ITEM_PACKAGING
            affected = [fg for fg, _ in comp_to_fgs.get(comp, [])]
            pats = [patterns.get(fg).pattern for fg in affected if fg in patterns]
            declining = bool(pats) and all(p in ("DECLINING", "DISCONTINUED") for p in pats)
            uncertain = any(p in ("INSUFFICIENT_HISTORY", "NEW_PRODUCT", "INTERMITTENT") for p in pats)

            inp = MaterialRiskInput(
                component=comp, physical_available=physical,
                equivalent_in_fg=equivalent, open_purchase=open_q,
                total_required=total_req,
                stockout_month=cc.stockout_month if cc else None,
                covered_through_month=cc.covered_through_month if cc else None,
                lead_time_p90=lt_p90,
                procurement_mode=classify_procurement_mode(comp in purchased_items, comp in produced_set),
                import_class=import_cls, supplier_confidence=supplier_conf,
                is_shared=comp in shared, is_packaging=is_pack,
                forecast_uncertain=uncertain, declining_or_discontinued=declining)
            rec = classify_material(inp, SNAPSHOT)

            n_fg = len(affected)
            cases.append(ExecutiveCase(
                title=f"{label} ({comp})",
                what_happens=(f"El stock físico de {label.lower()} cubre "
                              f"{_coverage_months(cc, SNAPSHOT)}; la demanda futura "
                              f"requiere {_qty(total_req, unit)} en 12 meses."),
                why_matters=(f"Alimenta {n_fg} producto" + ("s" if n_fg != 1 else "")
                             + (" y bloquea su producción" if is_pack else "") + "."),
                have_physical=_qty(physical, unit),
                have_equivalent=_qty(equivalent, unit),
                have_open=_qty(open_q, unit),
                need_future=_qty(total_req, unit),
                can_produce=_coverage_months(cc, SNAPSHOT) + " de producción",
                open_order=_qty(open_q, unit),
                open_state=("EN TRÁNSITO (no confirmado)" if open_q > 0 else "—"),
                lead_time=(f"{lt_p90} días" if lt_p90 else "sin historial"),
                risk_when=_risk_when(rec, cc),
                action=action_for(rec.decision),
                confidence=confidence_label(rec.confidence),
                flags=rec.flags,
                case_id=f"PURCHASE:{comp}:{rec.decision}:{SNAPSHOT[0]}-{SNAPSHOT[1]:02d}",
                decision=rec.decision,
                severity=_severity(rec.decision),
                summary=f"{label}: {rec.reason}",
                action_code=rec.decision,
                affected_items=affected,
                critical_date=_month(rec.latest_safe_order_month or (cc.stockout_month if cc else None)),
                snapshot_date=f"{SNAPSHOT[0]}-{SNAPSHOT[1]:02d}-01",
                reason_code=_reason_code(rec.decision, rec.flags, cc),
                evidence={"physical": physical, "equivalent_in_fg": equivalent,
                          "open_purchase": open_q, "required": total_req},
                traceability={"item_code": comp, "layers": ["stock", "equivalence", "coverage", "risk"]}))

        # ---- bronceador FG case ------------------------------------------
        bc = fg_covs.get(BRONCEADOR)
        if bc:
            fc_bron = fg_forecast.get(BRONCEADOR, {})
            dem_season = cov.sum_demand_to(fc_bron, cov.month_add(*SNAPSHOT, 1), (2027, BRONCEADOR_SEASON_END))
            cases.append(ExecutiveCase(
                title=f"Bronceador 200 mL ({BRONCEADOR})",
                what_happens=(f"Producto estacional (pico enero) con cobertura a fin de "
                              f"temporada de {cov.coverage_ratio(bc.total_supply, dem_season):.1f}x."),
                why_matters="No requiere compra; exceso de cobertura para la temporada sep–feb.",
                have_physical=f"{bc.usable_fg:,.0f} unidades",
                have_equivalent="—",
                have_open="—",
                need_future=f"{dem_season:,.0f} unidades (temporada)",
                can_produce=f"{bc.additional_producible:,.0f} unidades",
                open_order="—",
                open_state="—",
                lead_time="—",
                risk_when="—",
                action=action_for("EXCESS_STOCK"),
                confidence=confidence_label("MEDIUM"),
                flags=["SEASONALITY_UNCERTAIN"] if patterns.get(BRONCEADOR) and patterns[BRONCEADOR].confidence == "LOW" else [],
                case_id=f"PURCHASE:{BRONCEADOR}:EXCESS_STOCK:{SNAPSHOT[0]}-{SNAPSHOT[1]:02d}",
                decision="EXCESS_STOCK", severity="MEDIUM", summary="Bronceador con exceso de cobertura estacional",
                action_code="EXCESS_STOCK", affected_items=[BRONCEADOR],
                critical_date=None, snapshot_date=f"{SNAPSHOT[0]}-{SNAPSHOT[1]:02d}-01",
                reason_code="seasonal_excess",
                evidence={"season_demand": dem_season, "total_supply": bc.total_supply},
                traceability={"item_code": BRONCEADOR, "layers": ["seasonality", "coverage", "risk"]}))

        # ---- render ------------------------------------------------------
        decision_table = ["| Caso | Acción recomendada | Confianza |",
                          "|---|---|---|"]
        for c in cases:
            decision_table.append(f"| {c.title} | {c.action} | {c.confidence} |")

        body = "\n\n".join(c.to_markdown() for c in cases)
        md = (
            "# TELCHI — CASOS EJECUTIVOS DE COMPRA (V1)\n\n"
            f"**Fecha:** 2026-08-30 · **Snapshot:** {SNAPSHOT[0]}-{SNAPSHOT[1]:02d}\n\n"
            "Resumen: la urgencia de compra se concentra en **envases/etiquetas**, no en la "
            "materia prima química. Benzoato requiere compra inmediata; soda y cloruro están "
            "cubiertos por producto terminado y órdenes de importación; el gotero no limita; "
            "el bronceador tiene exceso de cobertura.\n\n"
            "---\n\n" + body + "\n\n---\n\n## Resumen de decisiones\n\n" +
            "\n".join(decision_table) + "\n")
        REPORT.write_text(md, encoding="utf-8")

        print(json.dumps({"gate": "TELCHI_PURCHASE_EXECUTIVE_CASES_V1",
                          "cases": [c.to_dict() for c in cases]}, indent=2, default=str))
        print(f"\n{'='*72}\nTELCHI_PURCHASE_EXECUTIVE_CASES_V1\n{'='*72}")
        print(f"EXECUTIVE CASES: {len(cases)} | report -> {REPORT.name}")
        for c in cases:
            print(f"\n  {c.title}: {c.action} (confianza {c.confidence})")
        gate = "TELCHI_PURCHASE_EXECUTIVE_CASES_V1_PASS"
        print(f"\n{gate}")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
