"""Gate 6: select replenishment policies under lead-time uncertainty.

The runner consumes the already generated Level B3 artefacts.  It does not rerun
SAP extraction or daily traces.  All quantities remain item/UoM scoped; no
cross-UoM quantity total is produced.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import (
    MAX_WORKERS,
    ResourceGuard,
    ResourceGuardAbort,
    _dump_json,
    resource_snapshot,
)

GATE = "TELCHI_POLICY_SELECTION_UNCERTAIN_LT_V1"
VERDICT = "TELCHI_REPLENISHMENT_POLICY_SELECTION_UNCERTAIN_LT_V1_PASS"
LEAD_TIMES = (0, 1, 2, 3, 5, 7)
DEFAULT_INPUT = EVIDENCE_ROOT / "branch_replenishment_level_b" / "v1_B3_100"
DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_policy_selection" / "v1"
DEFAULT_BRANCH = "2A"
EPS = 1e-9

# Materiality is intentionally explicit and conservative.  It is not a claim
# about commercial value or lost sales.
MATERIALITY = {
    "availability_delta_min": 0.02,       # +2 percentage points
    "stockout_days_reduction_min": 3,
    "inventory_reduction_pct_min": 0.10,  # -10%
    "replenishment_reduction_pct_min": 0.10,
    "service_noninferior_availability": -0.01,
    "service_noninferior_stockout_days": 3,
    "severe_worst_case_availability_drop": 0.05,
    "severe_worst_case_stockout_increase": 10,
}

COMPLEXITY = {
    "CURRENT_POLICY": "LOW",
    "KEEP_CURRENT": "LOW",
    "MIN_MAX": "LOW",
    "DAYS_OF_SUPPLY": "LOW",
    "PERIODIC_REVIEW": "LOW",
    "REORDER_POINT": "MEDIUM",
    "DYNAMIC_TARGET": "HIGH",
    "HYBRID": "HIGH",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _pct_change(value: float, current: float) -> float | None:
    return (value - current) / current if abs(current) > EPS else None


def _current(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "availability": _number(row.get("CURRENT_AVAILABILITY", row.get("availability_rate"))),
        "stockout_days": int(row.get("CURRENT_STOCKOUT_DAYS", row.get("historical_stockout_days_raw", 0)) or 0),
        "average_inventory": _number(row.get("CURRENT_AVG_INVENTORY", row.get("average_inventory"))),
        "replenishments": int(row.get("CURRENT_REPLENISHMENTS", row.get("replenishment_count", 0)) or 0),
    }


def _metric_value(row: Mapping[str, Any], metric: str) -> float:
    names = {
        "availability": ("policy_availability", "availability_rate"),
        "stockout_days": ("policy_stockout_days", "stockout_days"),
        "average_inventory": ("policy_avg_inventory", "average_inventory"),
        "replenishments": ("policy_replenishments", "replenishment_count"),
    }
    for name in names[metric]:
        if row.get(name) is not None:
            return _number(row[name])
    return 0.0


def _delta(row: Mapping[str, Any], metric: str, current: Mapping[str, Any]) -> float:
    return _metric_value(row, metric) - _number(current[metric])


def _material_service(row: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    availability = _delta(row, "availability", current)
    stockout = _delta(row, "stockout_days", current)
    return (
        availability >= MATERIALITY["availability_delta_min"]
        or stockout <= -MATERIALITY["stockout_days_reduction_min"]
    )


def _material_inventory(row: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    inventory_pct = _pct_change(_metric_value(row, "average_inventory"), current["average_inventory"])
    return (
        inventory_pct is not None
        and inventory_pct <= -MATERIALITY["inventory_reduction_pct_min"]
        and _delta(row, "availability", current) >= MATERIALITY["service_noninferior_availability"]
        and _delta(row, "stockout_days", current) <= MATERIALITY["service_noninferior_stockout_days"]
    )


def _material_movements(row: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    movement_pct = _pct_change(_metric_value(row, "replenishments"), current["replenishments"])
    return (
        movement_pct is not None
        and movement_pct <= -MATERIALITY["replenishment_reduction_pct_min"]
        and _delta(row, "availability", current) >= MATERIALITY["service_noninferior_availability"]
        and _delta(row, "stockout_days", current) <= MATERIALITY["service_noninferior_stockout_days"]
    )


def _worst_case(rows: list[Mapping[str, Any]], current: Mapping[str, Any]) -> dict[str, Any]:
    by = {
        "availability": [(_metric_value(row, "availability"), row) for row in rows],
        "stockout_days": [(_metric_value(row, "stockout_days"), row) for row in rows],
        "average_inventory": [(_metric_value(row, "average_inventory"), row) for row in rows],
        "replenishments": [(_metric_value(row, "replenishments"), row) for row in rows],
    }
    best_availability, best_availability_row = max(by["availability"], key=lambda x: x[0])
    worst_availability, worst_availability_row = min(by["availability"], key=lambda x: x[0])
    best_stockout, best_stockout_row = min(by["stockout_days"], key=lambda x: x[0])
    worst_stockout, worst_stockout_row = max(by["stockout_days"], key=lambda x: x[0])
    best_inventory, best_inventory_row = min(by["average_inventory"], key=lambda x: x[0])
    worst_inventory, worst_inventory_row = max(by["average_inventory"], key=lambda x: x[0])
    best_replenishments, best_replenishments_row = min(by["replenishments"], key=lambda x: x[0])
    worst_replenishments, worst_replenishments_row = max(by["replenishments"], key=lambda x: x[0])
    return {
        "BEST_AVAILABILITY": best_availability,
        "WORST_CASE_AVAILABILITY": worst_availability,
        "BEST_STOCKOUT_DAYS": best_stockout,
        "WORST_CASE_STOCKOUT_DAYS": worst_stockout,
        "BEST_AVG_INVENTORY": best_inventory,
        "WORST_CASE_AVG_INVENTORY": worst_inventory,
        "BEST_REPLENISHMENTS": int(best_replenishments),
        "WORST_CASE_REPLENISHMENTS": int(worst_replenishments),
        "WORST_CASE_AVAILABILITY_DELTA": worst_availability - current["availability"],
        "WORST_CASE_STOCKOUT_DELTA": worst_stockout - current["stockout_days"],
        "WORST_CASE_INVENTORY_DELTA": worst_inventory - current["average_inventory"],
        "WORST_CASE_REPLENISHMENT_DELTA": int(worst_replenishments) - current["replenishments"],
        "BEST_CASE_SCENARIOS": {
            "availability": best_availability_row.get("LeadTimeScenario"),
            "stockout_days": best_stockout_row.get("LeadTimeScenario"),
            "average_inventory": best_inventory_row.get("LeadTimeScenario"),
            "replenishments": best_replenishments_row.get("LeadTimeScenario"),
        },
        "WORST_CASE_SCENARIO": {
            "availability": worst_availability_row.get("LeadTimeScenario"),
            "stockout_days": worst_stockout_row.get("LeadTimeScenario"),
            "average_inventory": worst_inventory_row.get("LeadTimeScenario"),
            "replenishments": worst_replenishments_row.get("LeadTimeScenario"),
        },
    }


def _regret_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Calculate transparent, per-scenario relative regret.

    Each component is distance from the best available value in that LT
    scenario, normalized by the current baseline.  Equal-weight mean is only a
    reporting index; component regrets remain available for audit.
    """
    output: list[dict[str, Any]] = []
    by_lt: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_lt[int(row["LeadTimeScenario"])].append(row)
    for lt, scenario_rows in by_lt.items():
        ideals = {
            "availability": max(_metric_value(row, "availability") for row in scenario_rows),
            "stockout_days": min(_metric_value(row, "stockout_days") for row in scenario_rows),
            "average_inventory": min(_metric_value(row, "average_inventory") for row in scenario_rows),
            "replenishments": min(_metric_value(row, "replenishments") for row in scenario_rows),
        }
        current = _current(scenario_rows[0])
        components = []
        for row in scenario_rows:
            service = max(0.0, ideals["availability"] - _metric_value(row, "availability")) / max(ideals["availability"], 1.0)
            stockout = max(0.0, _metric_value(row, "stockout_days") - ideals["stockout_days"]) / max(current["stockout_days"], 1)
            inventory = max(0.0, _metric_value(row, "average_inventory") - ideals["average_inventory"]) / max(current["average_inventory"], 1.0)
            replenishments = max(0.0, _metric_value(row, "replenishments") - ideals["replenishments"]) / max(current["replenishments"], 1)
            regret = statistics.fmean((service, stockout, inventory, replenishments))
            components.append({
                "ItemCode": row["ItemCode"], "Branch": row["Branch"], "Policy": row["Policy"],
                "policy_parameters": row.get("policy_parameters", {}), "LeadTimeScenario": lt,
                "REGRET": regret, "AVAILABILITY_REGRET": service, "STOCKOUT_REGRET": stockout,
                "INVENTORY_REGRET": inventory, "REPLENISHMENT_REGRET": replenishments,
                "SCENARIO_IDEAL": ideals,
            })
        output.extend(components)
    return output


def _robust_evaluation(group: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    count = int(group.get("ROBUST_LT_COUNT") or 0)
    robustness_class = "ROBUST_HIGH" if count >= 5 else "ROBUST_MEDIUM" if count >= 3 else "ROBUST_LOW" if count >= 1 else "NOT_ROBUST"
    worst_service = (
        group["WORST_CASE_AVAILABILITY_DELTA"] >= MATERIALITY["availability_delta_min"]
        or group["WORST_CASE_STOCKOUT_DELTA"] <= -MATERIALITY["stockout_days_reduction_min"]
    )
    worst_inventory = (
        group["WORST_CASE_INVENTORY_DELTA"] <= -MATERIALITY["inventory_reduction_pct_min"] * max(current["average_inventory"], 1.0)
        and group["WORST_CASE_AVAILABILITY_DELTA"] >= MATERIALITY["service_noninferior_availability"]
        and group["WORST_CASE_STOCKOUT_DELTA"] <= MATERIALITY["service_noninferior_stockout_days"]
    )
    severe_deterioration = (
        group["WORST_CASE_AVAILABILITY_DELTA"] < -MATERIALITY["severe_worst_case_availability_drop"]
        or group["WORST_CASE_STOCKOUT_DELTA"] > MATERIALITY["severe_worst_case_stockout_increase"]
    )
    return {
        "ROBUST_LT_COUNT": count,
        "lead_time_scenarios_passed": f"{count}/{len(LEAD_TIMES)}",
        "robustness_class": robustness_class,
        "ROBUSTNESS_WORST_CASE_MATERIAL": bool(worst_service or worst_inventory),
        "ROBUSTNESS_SEVERE_WORST_CASE_DETERIORATION": bool(severe_deterioration),
        "ROBUSTNESS_VALIDATED": bool(count >= 1 and (worst_service or worst_inventory) and not severe_deterioration),
    }


def _family_name(master: Mapping[str, Any] | None) -> str:
    if not master:
        return "UNRESOLVED"
    for field in ("U_LINEA", "ItmsGrpCod"):
        value = master.get(field)
        if value not in (None, "", "0"):
            return f"{field}:{value}"
    return "UNRESOLVED"


def _complexity(policy: str) -> dict[str, Any]:
    level = COMPLEXITY.get(policy, "HIGH")
    details = {
        "LOW": {"frequency_of_calculation": "LOW/MEDIUM", "parameter_count": "LOW", "forecast_dependency": "NONE", "lead_time_dependency": "LOW"},
        "MEDIUM": {"frequency_of_calculation": "MEDIUM", "parameter_count": "MEDIUM", "forecast_dependency": "LOW", "lead_time_dependency": "MEDIUM"},
        "HIGH": {"frequency_of_calculation": "HIGH", "parameter_count": "HIGH", "forecast_dependency": "MEDIUM/HIGH", "lead_time_dependency": "HIGH"},
    }[level]
    return {"policy": policy, "OPERATIONAL_COMPLEXITY": level, **details}


def _load_master_artifact(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "NOT_RUN", "items": {}, "warehouse_capacity_schema": {}, "cost_observation": {}}


def fetch_master_data(items: list[str]) -> dict[str, Any]:
    """Read-only audit of physical master data and current cost coverage."""
    from modules.telchi.investigation.atomic.connection import connect

    placeholders = ",".join("?" for _ in items)
    conn, cur = connect()
    try:
        cur.execute(f'''SELECT "ItemCode","ItemName","InvntryUom","BuyUnitMsr","SalUnitMsr","ItmsGrpCod","U_TYPE","U_LINEA",
            "NumInBuy","NumInSale","PurPackMsr","PurPackUn","SalPackMsr","SalPackUn",
            "SLength1","SLen1Unit","SWidth1","SWdth1Unit","SHeight1","SHght1Unit","SVolume","SVolUnit","SWeight1","SWght1Unit",
            "BLength1","BLen1Unit","BWidth1","BWdth1Unit","BHeight1","BHght1Unit","BVolume","BVolUnit","BWeight1","BWght1Unit",
            "AvgPrice","LastPurPrc","LastPurCur","LastPurDat"
            FROM "TELCHI"."OITM" WHERE "ItemCode" IN ({placeholders}) ORDER BY "ItemCode"''', tuple(items))
        names = [d[0] for d in cur.description]
        raw = [dict(zip(names, row)) for row in cur.fetchall()]
        cur.execute(f'''SELECT "ItemCode","WhsCode","OnHand","AvgPrice","StockValue"
            FROM "TELCHI"."OITW" WHERE "ItemCode" IN ({placeholders}) AND "WhsCode" IN ('2A-SAL','2A-SMK')''', tuple(items))
        wh_names = [d[0] for d in cur.description]
        wh_rows = [dict(zip(wh_names, row)) for row in cur.fetchall()]
        cur.execute('SELECT * FROM "TELCHI"."OWHS" LIMIT 0')
        warehouse_columns = [d[0] for d in cur.description]
    finally:
        cur.close(); conn.close()

    def positive(row: Mapping[str, Any], *fields: str) -> bool:
        return any(_number(row.get(field)) > 0 for field in fields)

    records: dict[str, dict[str, Any]] = {}
    for row in raw:
        item = str(row["ItemCode"])
        records[item] = {
            **row,
            "family": _family_name(row),
            "has_length_data": positive(row, "SLength1", "BLength1"),
            "has_width_data": positive(row, "SWidth1", "BWidth1"),
            "has_height_data": positive(row, "SHeight1", "BHeight1"),
            "has_volume_data": positive(row, "SVolume", "BVolume") or all(positive(row, f) for f in ("SLength1", "SWidth1", "SHeight1")),
            "has_weight_data": positive(row, "SWeight1", "BWeight1"),
            "has_packaging_physical_data": positive(row, "BLength1", "BWidth1", "BHeight1", "BVolume", "BWeight1"),
            "has_packaging_uom_data": any(row.get(field) not in (None, "") for field in ("PurPackMsr", "SalPackMsr")),
            "has_package_data": positive(row, "BLength1", "BWidth1", "BHeight1", "BVolume", "BWeight1") or any(row.get(field) not in (None, "") for field in ("PurPackMsr", "SalPackMsr")),
            "has_uom_data": any(row.get(field) not in (None, "") for field in ("InvntryUom", "BuyUnitMsr", "SalUnitMsr")),
            "has_units_per_box": (_number(row.get("PurPackUn")) > 1 or _number(row.get("SalPackUn")) > 1),
        }
    branch_cost = defaultdict(list)
    for row in wh_rows:
        branch_cost[str(row["ItemCode"])].append({**row})
    for item, record in records.items():
        record["branch_stock_observation"] = branch_cost.get(item, [])
    cost_valid = [row for row in raw if _number(row.get("AvgPrice")) > 0]
    coverage_fields = {
        "L_PRODUCTS_WITH_VOLUME_DATA": "has_volume_data",
        "L_PRODUCTS_WITH_PACKAGE_DATA": "has_package_data",
        "L_PRODUCTS_WITH_WEIGHT_DATA": "has_weight_data",
        "L_PRODUCTS_WITH_LENGTH_DATA": "has_length_data",
        "L_PRODUCTS_WITH_WIDTH_DATA": "has_width_data",
        "L_PRODUCTS_WITH_HEIGHT_DATA": "has_height_data",
        "L_PRODUCTS_WITH_UOM_DATA": "has_uom_data",
        "L_PRODUCTS_WITH_UNITS_PER_BOX": "has_units_per_box",
    }
    coverage = {name: sum(bool(row.get(field)) for row in records.values()) for name, field in coverage_fields.items()}
    missing = []
    for item, row in sorted(records.items()):
        missing_fields = [name for name, field in coverage_fields.items() if not row.get(field)]
        if missing_fields:
            missing.append({"ItemCode": item, "missing": missing_fields})
    return {
        "status": "PASS_READ_ONLY",
        "items": records,
        "coverage": coverage,
        "MISSING_PHYSICAL_MASTER_DATA": missing,
        "warehouse_capacity_schema": {
            "columns": warehouse_columns,
            "required_missing": ["usable_m3", "positions", "racks", "zone_capacity", "max_weight", "restrictions"],
            "status": "NOT_AVAILABLE_IN_OWHS_MASTER" if not any("VOLUME" in c.upper() or "CAPAC" in c.upper() for c in warehouse_columns) else "REVIEW_REQUIRED",
        },
        "cost_observation": {
            "oitm_rows": len(raw), "avg_price_positive": len(cost_valid),
            "avg_price_coverage_pct": 100 * len(cost_valid) / len(items) if items else 0.0,
            "branch_oitw_rows": len(wh_rows),
            "status": "OBSERVED_CURRENT_COST_ONLY_NOT_VALIDATED_FOR_HISTORICAL_POLICY_VALUE",
            "INVENTORY_VALUE": "NOT_READY",
            "reason": "policy simulations span historical dates but SAP cost fields are current/item-level observations; no validated time-aligned cost series was reused",
        },
    }


def _build_family_comparison(product_rows: list[dict[str, Any]], groups: Mapping[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in product_rows:
        if row["family"] != "UNRESOLVED":
            by_family[row["family"]].append(row)
    result = []
    for family, products in sorted(by_family.items()):
        if len(products) < 2:
            continue
        # Use a common policy/configuration among products, not the per-item key.
        common: dict[tuple[str, str], list[float]] = defaultdict(list)
        for product in products:
            for (item, config), summary in groups.items():
                if item == product["ItemCode"]:
                    common[config].append(float(summary.get("AVG_REGRET") or 0.0))
        if not common:
            continue
        family_regret, common_key = min((statistics.fmean(values), key) for key, values in common.items())
        per_item = [product.get("selected_avg_regret") for product in products]
        per_item_regret = statistics.fmean(float(value) for value in per_item if value is not None) if per_item and all(value is not None for value in per_item) else None
        result.append({
            "family": family, "products": len(products), "item_codes": [p["ItemCode"] for p in products],
            "family_policy": {"Policy": common_key.split("|", 1)[0], "policy_parameters": json.loads(common_key.split("|", 1)[1])},
            "family_policy_avg_regret": family_regret, "per_item_policy_avg_regret": per_item_regret,
            "family_policy_regret_delta": family_regret - per_item_regret if per_item_regret is not None else None,
            "family_policy_preferred": bool(per_item_regret is not None and family_regret <= per_item_regret * 1.05),
            "decision": "FAMILY_POLICY_CANDIDATE" if per_item_regret is not None and family_regret <= per_item_regret * 1.05 else "KEEP_PER_ITEM_POLICY" if per_item_regret is not None else "NOT_COMPARABLE_CURRENT_MISSING_REGRET",
        })
    return result


def _low_cause_hypothesis(product: Mapping[str, Any], feature: Mapping[str, Any] | None) -> dict[str, Any]:
    """Rank observable sensitivity signals; do not claim causal diagnosis."""
    if not feature:
        return {"cause": "OTHER", "causal_status": "NOT_IDENTIFIABLE", "evidence": {}}
    if product.get("lead_time_sensitivity") == "LT_HIGHLY_SENSITIVE":
        cause = "LT_SENSITIVE_TRIGGER"
    elif feature.get("demand_variability") == "VARIABLE":
        cause = "HIGH_DEMAND_VARIABILITY"
    elif feature.get("demand_pattern") == "INTERMITTENT":
        cause = "INTERMITTENT_DEMAND"
    elif _number(feature.get("average_inventory")) <= 1 and _number(feature.get("demand_sum")) > 0:
        cause = "LOW_INITIAL_STOCK"
    elif _number(feature.get("replenishment_count")) >= 20:
        cause = "HIGH_REPLENISHMENT_DEPENDENCE"
    else:
        cause = "POLICY_PARAMETER_SENSITIVITY"
    return {
        "cause": cause,
        "causal_status": "HYPOTHESIS_FROM_OBSERVED_BACKTEST_FEATURES_NOT_CAUSAL",
        "evidence": {key: feature.get(key) for key in ("demand_cv", "demand_pattern", "demand_variability", "stockout_days", "average_inventory", "replenishment_count")},
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def run(input_dir: Path = DEFAULT_INPUT, output: Path = DEFAULT_OUTPUT, *, master_artifact: Path | None = None, fetch_master: bool = True) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    for name in ("product_selection.jsonl", "worst_case.jsonl", "regret.jsonl", "service_robustness.jsonl", "excess_inventory.jsonl", "family_comparison.jsonl", "executive_cases.jsonl", "master_data_audit.json", "gate_result.json", "resource_metrics.jsonl"):
        (output / name).unlink(missing_ok=True)
    guard = ResourceGuard(output)
    guard.check("before_artifacts", 0, 0, MAX_WORKERS)
    products = _read_jsonl(input_dir / "product_summary.jsonl")
    metrics = _read_jsonl(input_dir / "policy_metrics.jsonl")
    current_rows = {str(row["ItemCode"]): row for row in _read_jsonl(input_dir / "current_policy.jsonl")}
    selection_path = input_dir / "sample_selection.json"
    selection_features = {}
    if selection_path.exists():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        selection_features = {str(row["ItemCode"]): row for row in selection.get("selected_features", [])}
    guard.check("artifacts_loaded", len(products) + len(metrics) + len(current_rows), 0, MAX_WORKERS)
    if len(products) != 100 or any(not str(row["ItemCode"]).startswith("L") for row in products):
        raise ValueError("Gate 6 requires the validated 100-product L% Level B3 universe")

    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in metrics:
        by_group[(str(row["ItemCode"]), str(row["Policy"]) + "|" + json.dumps(row.get("policy_parameters", {}), sort_keys=True))].append(row)
    regret_rows = _regret_rows(metrics)
    regret_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in regret_rows:
        regret_by_group[(str(row["ItemCode"]), str(row["Policy"]) + "|" + json.dumps(row.get("policy_parameters", {}), sort_keys=True))].append(row)

    group_summaries: dict[tuple[str, str], dict[str, Any]] = {}
    for key, rows in by_group.items():
        item = key[0]
        current = _current(current_rows[item])
        summary = {"ItemCode": item, "Branch": DEFAULT_BRANCH, "Policy": rows[0]["Policy"], "policy_parameters": rows[0].get("policy_parameters", {})}
        summary.update(_worst_case(rows, current))
        summary.update(_robust_evaluation({**summary, "ROBUST_LT_COUNT": rows[0].get("ROBUST_LT_COUNT")}, current))
        regrets = regret_by_group[key]
        summary["MAX_REGRET"] = max((r["REGRET"] for r in regrets), default=None)
        summary["AVG_REGRET"] = statistics.fmean(r["REGRET"] for r in regrets) if regrets else None
        summary["lead_time_scenarios"] = [{"LT": row["LeadTimeScenario"], "availability": _metric_value(row, "availability"), "stockout_days": _metric_value(row, "stockout_days"), "average_inventory": _metric_value(row, "average_inventory"), "replenishments": _metric_value(row, "replenishments"), "regret": next((r["REGRET"] for r in regrets if r["LeadTimeScenario"] == row["LeadTimeScenario"]), None)} for row in sorted(rows, key=lambda r: int(r["LeadTimeScenario"]))]
        group_summaries[key] = summary

    master = _load_master_artifact(master_artifact)
    if fetch_master and master.get("status") == "NOT_RUN":
        master = fetch_master_data(sorted(str(row["ItemCode"]) for row in products))
        _dump_json(output / "master_data_audit.json", master)
    else:
        _dump_json(output / "master_data_audit.json", master)

    product_rows: list[dict[str, Any]] = []
    for product in products:
        item = str(product["ItemCode"])
        current = _current(current_rows[item])
        candidate = product.get("BEST_CANDIDATE")
        candidate_group = None
        if candidate:
            key = (item, str(candidate["Policy"]) + "|" + json.dumps(candidate.get("policy_parameters", {}), sort_keys=True))
            candidate_group = group_summaries.get(key)
        selected = {**candidate, **candidate_group} if candidate and candidate_group else (dict(candidate) if candidate else None)
        if selected:
            selected["operational_complexity"] = _complexity(str(selected["Policy"]))
            selected["MAX_REGRET"] = candidate_group.get("MAX_REGRET") if candidate_group else None
            selected["AVG_REGRET"] = candidate_group.get("AVG_REGRET") if candidate_group else None
            selected["worst_case"] = candidate_group
            selected["worst_case_inventory_delta_pct"] = _pct_change(candidate_group["WORST_CASE_AVG_INVENTORY"], current["average_inventory"])
            selected["availability_delta_worst_case"] = candidate_group["WORST_CASE_AVAILABILITY_DELTA"]
            selected["stockout_delta_worst_case"] = candidate_group["WORST_CASE_STOCKOUT_DELTA"]
            selected["material_worst_case_service"] = candidate_group["ROBUSTNESS_WORST_CASE_MATERIAL"]
            selected["robustness_validated"] = candidate_group["ROBUSTNESS_VALIDATED"]
        robustness = selected.get("robustness_class") if selected else None
        # Group C LOW candidates are explicitly not definitive recommendations,
        # even when one scenario looks attractive.
        robust_ok = bool(selected and robustness in {"ROBUST_HIGH", "ROBUST_MEDIUM"} and selected.get("ROBUSTNESS_VALIDATED"))
        conservative = bool(selected and selected.get("WORST_CASE_INVENTORY_DELTA", 0) > MATERIALITY["inventory_reduction_pct_min"] * max(current["average_inventory"], 1.0))
        if robust_ok and conservative:
            decision = "READY_WITH_CONSERVATIVE_POLICY"
        elif robust_ok:
            decision = "READY_FOR_POLICY"
        elif product.get("DECISION_STATUS") == "KEEP_CURRENT_CANDIDATE":
            decision = "KEEP_CURRENT"
        elif selected and robustness == "ROBUST_LOW" and product.get("sensitivity_class") in {"LT_HIGHLY_SENSITIVE", "LT_MODERATE"}:
            decision = "LEAD_TIME_DEPENDENT"
        elif not selected and product.get("PROBLEM_CLASS") == "NEITHER":
            decision = "KEEP_CURRENT"
        elif selected:
            decision = "NEEDS_OPERATIONAL_DATA"
        else:
            decision = "NEEDS_OPERATIONAL_DATA"
        family = _family_name(master.get("items", {}).get(item))
        row = {
            "ItemCode": item, "Branch": DEFAULT_BRANCH, "family": family, "PROBLEM_CLASS": product["PROBLEM_CLASS"],
            "CURRENT": current, "DECISION_CLASS": decision, "selected_candidate": selected,
            "robustness_class": robustness, "lead_time_sensitivity": product.get("sensitivity_class"),
            "sensitivity_score": product.get("sensitivity_score"), "B3_DECISION_STATUS": product.get("DECISION_STATUS"),
            "B3_BEST_CANDIDATE": candidate,
            "low_sensitivity_cause_hypothesis": _low_cause_hypothesis({"lead_time_sensitivity": product.get("sensitivity_class")}, selection_features.get(item)),
            "operating_policy_output": {
                "ItemCode": item, "Branch": DEFAULT_BRANCH, "current_problem": product["PROBLEM_CLASS"],
                "recommended_policy_class": selected.get("Policy") if selected else "KEEP_CURRENT",
                "Robustness": robustness, "decision_confidence": "HIGH" if decision == "READY_FOR_POLICY" else "MEDIUM" if decision == "READY_WITH_CONSERVATIVE_POLICY" else "LOW",
                "availability_current": current["availability"], "availability_candidate_best": selected.get("availability_rate") if selected else None,
                "stockout_current_days": current["stockout_days"], "stockout_candidate_worst_case_days": selected.get("WORST_CASE_STOCKOUT_DAYS") if selected else None,
                "average_inventory_current": current["average_inventory"], "average_inventory_candidate_worst_case": selected.get("WORST_CASE_AVG_INVENTORY") if selected else None,
                "replenishments_current": current["replenishments"], "replenishments_candidate_worst_case": selected.get("WORST_CASE_REPLENISHMENTS") if selected else None,
                "lead_time_scenarios_passed": selected.get("lead_time_scenarios_passed") if selected else "0/6",
            },
        }
        if selected:
            row["selected_avg_regret"] = selected.get("AVG_REGRET")
            row["selected_max_regret"] = selected.get("MAX_REGRET")
        product_rows.append(row)

    service_rows = []
    excess_rows = []
    for product in product_rows:
        item = product["ItemCode"]
        current = product["CURRENT"]
        candidates = [summary for (candidate_item, _), summary in group_summaries.items() if candidate_item == item]
        stockout_counts = [sum(_delta(row, "stockout_days", current) <= -MATERIALITY["stockout_days_reduction_min"] for row in by_group[(item, str(summary["Policy"]) + "|" + json.dumps(summary["policy_parameters"], sort_keys=True))]) for summary in candidates]
        best_count = max(stockout_counts, default=0)
        service_rows.append({"ItemCode": item, "Branch": DEFAULT_BRANCH, "problem": product["PROBLEM_CLASS"], "stockout_reduction_all_scenarios": best_count == 6, "stockout_reduction_majority": best_count >= 4, "stockout_reduction_some": 1 <= best_count <= 3, "STOCKOUT_REDUCTION_ROBUSTNESS": "ALL_SCENARIOS" if best_count == 6 else "MAJORITY" if best_count >= 4 else "SOME_SCENARIOS" if best_count else "NONE", "best_material_stockout_reduction_scenarios": best_count})
        if product["PROBLEM_CLASS"] in {"EXCESS_INVENTORY_PROBLEM", "BOTH"}:
            reductions = []
            for summary in candidates:
                key = (item, str(summary["Policy"]) + "|" + json.dumps(summary["policy_parameters"], sort_keys=True))
                rows = by_group[key]
                count = sum(_material_inventory(row, current) for row in rows)
                if count:
                    reductions.append((count, summary))
            best = max(reductions, key=lambda value: value[0], default=(0, None))
            candidate = best[1]
            excess_rows.append({"ItemCode": item, "Branch": DEFAULT_BRANCH, "problem": product["PROBLEM_CLASS"], "INVENTORY_REDUCTION_ROBUSTNESS": best[0], "INVENTORY_REDUCTION_PCT": _pct_change(candidate["WORST_CASE_AVG_INVENTORY"], current["average_inventory"]) if candidate else None, "AVAILABILITY_DELTA": candidate["WORST_CASE_AVAILABILITY_DELTA"] if candidate else None, "candidate": candidate})

    family_groups = {(item, config): summary for (item, config), summary in group_summaries.items()}
    family_rows = _build_family_comparison(product_rows, family_groups)
    family_counts = Counter(row["family"] for row in product_rows)
    cases: list[dict[str, Any]] = []
    for wanted, predicate, limit in (("HIGH", lambda r: r["robustness_class"] == "ROBUST_HIGH", 10), ("MEDIUM_LOW", lambda r: r["robustness_class"] in {"ROBUST_MEDIUM", "ROBUST_LOW"}, 5), ("KEEP_CURRENT", lambda r: r["DECISION_CLASS"] == "KEEP_CURRENT", 5)):
        for row in sorted((r for r in product_rows if predicate(r)), key=lambda r: (-r["CURRENT"]["stockout_days"], r["ItemCode"]))[:limit]:
            cases.append({"case_group": wanted, "ItemCode": row["ItemCode"], "Branch": DEFAULT_BRANCH, "problem": row["PROBLEM_CLASS"], "decision": row["DECISION_CLASS"], "current": row["CURRENT"], "candidate": row.get("selected_candidate"), "lead_time_scenarios": row.get("selected_candidate", {}).get("lead_time_scenarios", []) if row.get("selected_candidate") else [], "traceability": "product_summary.jsonl + policy_metrics.jsonl; no new SAP trace"})

    # Write compact artefacts only.  Full 11,400 source rows remain in Gate 5B.
    for filename, rows in (("product_selection.jsonl", product_rows), ("worst_case.jsonl", [{"ItemCode": k[0], **v} for k, v in group_summaries.items()]), ("regret.jsonl", regret_rows), ("service_robustness.jsonl", service_rows), ("excess_inventory.jsonl", excess_rows), ("family_comparison.jsonl", family_rows), ("executive_cases.jsonl", cases)):
        with (output / filename).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(_jsonable(row), ensure_ascii=False) + "\n")
    complexity = Counter(str((row.get("selected_candidate") or {}).get("Policy", "KEEP_CURRENT")) for row in product_rows)
    decision_counts = Counter(row["DECISION_CLASS"] for row in product_rows)
    robustness_counts = Counter(row["robustness_class"] for row in product_rows if row["robustness_class"])
    portfolio = {policy: complexity.get(policy, 0) for policy in ("MIN_MAX", "REORDER_POINT", "DAYS_OF_SUPPLY", "PERIODIC_REVIEW", "DYNAMIC_TARGET", "HYBRID", "KEEP_CURRENT")}
    resource = guard.summary()
    result = {
        "gate": GATE, "verdict": VERDICT if resource["resource_abort_count"] == 0 and len(product_rows) == 100 else "DEGRADED",
        "context": {"ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION", "PRIMARY_UNIVERSE": "ItemCode LIKE 'L%'", "branch": DEFAULT_BRANCH, "SAP_WRITE_COUNT": 0, "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED", "READ_ONLY": True},
        "universe": {"products": len(product_rows), "days": 365, "lead_time_scenarios": list(LEAD_TIMES), "source": "Gate 5B B3 artefacts; no full retrace"},
        "decision_classes": dict(decision_counts), "robustness": {"baseline_gate_5b": {name: robustness_counts.get(name, 0) for name in ("ROBUST_HIGH", "ROBUST_MEDIUM", "ROBUST_LOW", "NOT_ROBUST")}, "classes": ["ROBUST_HIGH", "ROBUST_MEDIUM", "ROBUST_LOW", "NOT_ROBUST"]},
        "policy_portfolio": portfolio,
        "complexity": {policy: _complexity(policy) for policy in portfolio},
        "worst_case": {"artifact": "worst_case.jsonl", "metrics": ["WORST_CASE_AVAILABILITY", "WORST_CASE_STOCKOUT_DAYS", "WORST_CASE_AVG_INVENTORY", "WORST_CASE_REPLENISHMENTS"]},
        "regret": {"artifact": "regret.jsonl", "MAX_REGRET": "max six scenario composite regret", "AVG_REGRET": "mean six scenario composite regret", "formula": "equal-weight mean of relative distance from scenario ideal for availability, stockout, inventory and replenishments"},
        "materiality_thresholds": MATERIALITY,
        "service": {"artifact": "service_robustness.jsonl", "STOCKOUT_REDUCTION_ROBUSTNESS": ["ALL_SCENARIOS", "MAJORITY", "SOME_SCENARIOS", "NONE"]},
        "inventory": {"artifact": "excess_inventory.jsonl", "INVENTORY_VALUE": master.get("cost_observation", {}).get("INVENTORY_VALUE", "NOT_READY")},
        "families": {"artifact": "family_comparison.jsonl", "family_count": len(family_counts), "resolved_family_products": len(product_rows) - family_counts.get("UNRESOLVED", 0), "policy_not_forced": True},
        "physical_master_data": {"artifact": "master_data_audit.json", "coverage_status": master.get("status", "NOT_RUN"), **master.get("coverage", {}), "MISSING_PHYSICAL_MASTER_DATA": len(master.get("MISSING_PHYSICAL_MASTER_DATA", []))},
        "lead_time_instrumentation": {"required": ["dispatch_timestamp", "receipt_timestamp"], "keys": ["DocEntry / transfer_id", "source_warehouse", "destination_branch"], "optional": "shipment_id/load_id only when one load contains multiple OWTR", "quality": ["receipt_timestamp >= dispatch_timestamp", "closed loads cannot have null timestamps", "timezone required", "post-close changes require audit"]},
        "executive_cases": {"artifact": "executive_cases.jsonl", "required_groups": {"ROBUST_HIGH": 10, "MEDIUM_LOW": 5, "KEEP_CURRENT": 5}, "generated": dict(Counter(case["case_group"] for case in cases))},
        "resource_safety": resource,
        "SAP_WRITE_COUNT": 0,
        "next_gate": "GATE 7 — PILOT REPLENISHMENT POLICY DESIGN" if decision_counts.get("READY_FOR_POLICY", 0) + decision_counts.get("READY_WITH_CONSERVATIVE_POLICY", 0) >= 20 else "GATE — PHYSICAL LEAD-TIME CAPTURE PRIORITY",
        "artifacts": ["product_selection.jsonl", "worst_case.jsonl", "regret.jsonl", "service_robustness.jsonl", "excess_inventory.jsonl", "family_comparison.jsonl", "executive_cases.jsonl", "master_data_audit.json", "resource_metrics.jsonl", "gate_result.json"],
    }
    _dump_json(output / "gate_result.json", result)
    return result


def _abort(output: Path, error: str) -> dict[str, Any]:
    result = {"gate": GATE, "verdict": "DEGRADED", "result": "RESOURCE_GUARD_ABORT", "error": error, "SAP_WRITE_COUNT": 0, "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED", "snapshot": resource_snapshot()}
    _dump_json(output / "gate_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI Gate 6 policy selection under lead-time uncertainty")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--master-artifact", type=Path)
    parser.add_argument("--skip-master", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.output, master_artifact=args.master_artifact, fetch_master=not args.skip_master)
    except ResourceGuardAbort as exc:
        result = _abort(args.output, str(exc))
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "decision_classes": result.get("decision_classes"), "robustness": result.get("robustness"), "SAP_WRITE_COUNT": 0, "output": str(args.output)}, ensure_ascii=False, indent=2, default=str))
    return 3 if result.get("result") == "RESOURCE_GUARD_ABORT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
