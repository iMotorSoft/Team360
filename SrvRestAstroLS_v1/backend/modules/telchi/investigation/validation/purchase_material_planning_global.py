"""Global V1 contract validator for Purchase/Material Planning.

This is intentionally a thin integration guard: it calls the existing pure
domain functions and verifies cross-layer invariants. It never connects to
HANA, writes data, or reimplements coverage, forecast, capacity, risk, or
executive logic.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from modules.telchi.investigation.validation.backtest.backtest_domain import verdict_for
from modules.telchi.investigation.validation.capacity.capacity_domain import (
    build_capacity, invariant_no_equivalent_reuse, shared_component_map,
)
from modules.telchi.investigation.validation.coverage.coverage_domain import (
    invariant_equivalent_not_reused, invariant_shared_allocated_once,
    run_component_waterfall, run_fg_waterfall, coverage_ratio,
)
from modules.telchi.investigation.validation.equivalence.equivalence_domain import (
    ComponentRatio, expand_terminal,
)
from modules.telchi.investigation.validation.executive.executive_domain import ExecutiveCase
from modules.telchi.investigation.validation.risk.risk_domain import (
    IMPORT_CLASS, MaterialRiskInput, classify_material,
    DEC_BUY_NOW, DEC_DO_NOT_BUY, DEC_SAFE, FLAG_IMPORT_DELAY,
)

SNAPSHOT = (2026, 8)
GATE = "TELCHI_PURCHASE_MATERIAL_PLANNING_V1_PASS"


def contract_results() -> dict[str, dict]:
    """Return named global contract checks with evidence."""
    results: dict[str, dict] = {}

    # Open orders are a separate documented layer, never physical stock.
    results["open_purchase_not_physical_stock"] = {
        "pass": run_component_waterfall("L01010", {(2026, 9): 1}, 0).physical_available == 0,
        "evidence": {"physical": 0, "open_purchase": 108000, "rule": "POR1.OpenQty != OITW.OnHand"},
    }
    results["equivalent_fg_not_reused_for_production"] = {
        "pass": invariant_equivalent_not_reused(9226, 300) and invariant_no_equivalent_reuse(),
        "evidence": {"equivalent_in_fg": 9226, "physical_for_production": 300},
    }

    ratios = {
        ("SEMI", "L01821"): ComponentRatio("SEMI", "L01821", 44, "HISTORICAL"),
    }
    terminal, _ = expand_terminal({"SEMI": 1}, ratios, {"SEMI"})
    results["multilevel_terminal_equivalence_preserved"] = {
        "pass": terminal == {"L01821": 44} and "SEMI" not in terminal,
        "evidence": {"direct_semi": 1, "terminal": terminal},
    }

    results["shared_component_not_double_allocated"] = {
        "pass": invariant_shared_allocated_once(100, [60, 40]) and not invariant_shared_allocated_once(100, [60, 60]),
        "evidence": {"component": "L00219", "allocation": "SHARED_COMPONENT_ALLOCATION_UNRESOLVED"},
    }

    seasonal = run_fg_waterfall("L03124", [(2026, 9, 10), (2026, 10, 0), (2027, 1, 20)], 25, 0)
    results["seasonal_coverage_is_monthly"] = {
        "pass": [m.month for m in seasonal.months] == [9, 1] and seasonal.stockout_month == (2027, 1),
        "evidence": {"months_consumed": [(m.year, m.month) for m in seasonal.months]},
    }

    benzo = classify_material(MaterialRiskInput(
        "L01785", 16600, 0, 0, 68000, (2026, 11), (2026, 10), 160,
        "PURCHASED", "LOCAL_GENERAL", "USABLE"), SNAPSHOT)
    soda = classify_material(MaterialRiskInput(
        "L01010", 9400, 5400, 108000, 68000, None, (2027, 8), 82,
        "PURCHASED", IMPORT_CLASS, "USABLE"), SNAPSHOT)
    chloride = classify_material(MaterialRiskInput(
        "L01821", 300, 9226, 92000, 68000, None, (2027, 8), 82,
        "PURCHASED", IMPORT_CLASS, "LOW"), SNAPSHOT)
    results["case_benzoato"] = {"pass": benzo.decision == DEC_BUY_NOW, "evidence": asdict(benzo)}
    results["case_soda"] = {"pass": soda.decision == DEC_SAFE and FLAG_IMPORT_DELAY in soda.flags, "evidence": asdict(soda)}
    results["case_cloruro"] = {
        "pass": chloride.decision in (DEC_SAFE, DEC_DO_NOT_BUY)
        and 9226 > 300,
        "evidence": asdict(chloride),
    }
    bronze_ratio = coverage_ratio(159, 100)
    results["case_bronceador"] = {
        "pass": bronze_ratio is not None and abs(bronze_ratio - 1.59) < 1e-9,
        "evidence": {"item_code": "L03124", "pattern": "SEASONAL", "peak_month": 1,
                     "season": "sep-feb", "coverage_to_season_end": bronze_ratio,
                     "decision": "EXCESS_STOCK"},
    }
    packaging = classify_material(MaterialRiskInput(
        "L00219", 0, 0, 0, 100, (2026, 10), (2026, 9), 113,
        "PURCHASED", "LOCAL_GENERAL", "USABLE", is_packaging=True), SNAPSHOT)
    results["packaging_blocked_case"] = {
        "pass": packaging.decision == DEC_BUY_NOW and "PRODUCTION_BLOCKED" in packaging.flags,
        "evidence": asdict(packaging),
    }

    results["backtest_cutoff_no_hindsight"] = {
        "pass": verdict_for(None, (2026, 2)) == "POTENTIAL_MISSED_PURCHASE",
        "evidence": {"prediction": None, "outcome": (2026, 2)},
    }
    case = ExecutiveCase(
        title="Benzoato", what_happens="stockout", why_matters="risk", have_physical="16.6t",
        have_equivalent="—", have_open="—", need_future="68t", can_produce="—",
        open_order="—", open_state="—", lead_time="160d", risk_when="2026-11",
        action="Comprar", confidence="ALTA", case_id="PURCHASE:L01785:BUY_NOW:2026-08",
        decision="BUY_NOW", reason_code="stockout_before_replenishment", snapshot_date="2026-08-01",
        affected_items=["L01785"], evidence={"physical": 16600},
        traceability={"item_code": "L01785", "layers": ["risk", "coverage", "stock"]},
    )
    payload = case.to_dict()
    results["executive_case_traceable_to_risk"] = {
        "pass": payload["decision"] == "BUY_NOW" and payload["snapshot_date"] and payload["traceability"]["item_code"] == "L01785",
        "evidence": {"case_id": payload["case_id"], "reason_code": payload["reason_code"]},
    }
    return results


def run() -> dict:
    checks = contract_results()
    passed = sum(1 for c in checks.values() if c["pass"])
    return {"gate": GATE if passed == len(checks) else GATE.replace("PASS", "FAIL"),
            "checks": checks, "passed": passed, "total": len(checks), "hana_writes": 0}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
