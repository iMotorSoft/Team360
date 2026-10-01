"""Run TELCHI Gate 5B using availability as the primary service metric.

This is an investigation-only, observed-demand backtest.  It reuses exactly
Gate 5A's ten L products in branch 2A and the 365-day Level E projection.  No
lost demand is imputed into the primary run and no Level B data is touched.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    LEAD_TIME_SCENARIOS,
    METRIC_TOLERANCE,
    PolicyConfiguration,
    current_policy_metrics,
    deterministic_signature,
    policy_configurations,
    run_pair,
    simulate_pair,
)
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import (
    ResourceGuard,
    ResourceGuardAbort,
    _dump_json,
    resource_snapshot,
)
from modules.telchi.investigation.validation.branch_replenishment.fill_rate_sanity_check import (
    audit_current_pair,
    normalise_daily_rows,
)
from modules.telchi.investigation.validation.branch_replenishment.run_backtest_engine_v1 import (
    DEFAULT_INPUT,
    _daily_rows,
    _read_stock_index,
    _select_pairs,
)

DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_availability_backtest" / "v1_level_A"
EXPECTED_DAYS = 365
EXPECTED_PAIRS = 10
EXPECTED_CONFIGURATIONS = 19


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> int:
    with path.open("w", encoding="utf-8") as handle:
        count = 0
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
            count += 1
        return count


def _current_contract(row: dict[str, Any]) -> dict[str, Any]:
    """Expose the same explicit names as policy comparison rows."""
    result = dict(row)
    availability = float(row.get("availability_rate") or 0.0)
    stockout = int(row.get("historical_stockout_days_raw") or row.get("stockout_days") or 0)
    inventory = float(row.get("average_inventory") or 0.0)
    replenishments = int(row.get("replenishment_count") or 0)
    result.update({
        "CURRENT_AVAILABILITY": availability,
        "CURRENT_STOCKOUT_DAYS": stockout,
        "CURRENT_AVG_INVENTORY": inventory,
        "CURRENT_REPLENISHMENTS": replenishments,
        "OBSERVED_FILL_RATE": row.get("fill_rate"),
        "availability": availability,
        "stockout_days": stockout,
        "avg_inventory": inventory,
        "replenishments": replenishments,
        "service_metric_primary": "AVAILABILITY",
        "fill_rate_metric_role": "SECONDARY_CONTROL",
    })
    return result


def _problem_class(current: dict[str, Any], simulations: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    stockout = int(current.get("CURRENT_STOCKOUT_DAYS") or 0)
    availability = float(current.get("CURRENT_AVAILABILITY") or 0.0)
    service_problem = stockout > 0 or availability < 1.0 - METRIC_TOLERANCE
    inventory_opportunity = any(
        float(row.get("policy_availability") or 0.0) >= availability - METRIC_TOLERANCE
        and float(row.get("delta_avg_inventory") or 0.0) < 0
        for row in simulations
    )
    if service_problem and inventory_opportunity:
        classification = "BOTH"
    elif service_problem:
        classification = "SERVICE_PROBLEM"
    elif inventory_opportunity:
        classification = "EXCESS_INVENTORY_PROBLEM"
    else:
        classification = "NEITHER"
    return classification, {
        "service_problem": service_problem,
        "excess_inventory_opportunity": inventory_opportunity,
        "definition": (
            "SERVICE_PROBLEM = CURRENT availability < 100% or stockout days > 0; "
            "EXCESS_INVENTORY_PROBLEM = a policy preserves practically equivalent "
            "availability while reducing average inventory"
        ),
    }


def _candidate_view(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ItemCode", "Branch", "Policy", "policy_parameters", "LeadTimeScenario",
        "availability_rate", "availability_days", "stockout_days", "stockout_episodes",
        "stockout_duration_mean", "stockout_duration_median", "stockout_duration_p90",
        "stockout_duration_max", "average_inventory", "median_inventory", "max_inventory",
        "inventory_days", "average_days_of_supply", "replenishment_count",
        "replenishment_quantity", "average_order_quantity", "replenishment_interval_mean",
        "replenishment_interval_median", "fill_rate", "result_class", "pareto_status",
        "delta_availability", "delta_stockout_days", "delta_avg_inventory",
        "delta_replenishments", "ROBUST_LT_COUNT", "pareto_lt_count",
    )
    return {key: row.get(key) for key in keys}


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["Policy"]), int(row["LeadTimeScenario"]))].append(row)
    output = []
    for (policy, lead_time), values in sorted(groups.items()):
        def mean(field: str) -> float | None:
            numbers = [float(value[field]) for value in values if value.get(field) is not None]
            return sum(numbers) / len(numbers) if numbers else None

        output.append({
            "Policy": policy,
            "LeadTimeScenario": lead_time,
            "product_pairs": len({(row["ItemCode"], row["Branch"]) for row in values}),
            "availability_mean": mean("availability_rate"),
            "stockout_days_mean": mean("stockout_days"),
            "stockout_episodes_mean": mean("stockout_episodes"),
            "stockout_duration_mean": mean("stockout_duration_mean"),
            "stockout_duration_median_mean": mean("stockout_duration_median"),
            "stockout_duration_p90_mean": mean("stockout_duration_p90"),
            "stockout_duration_max_mean": mean("stockout_duration_max"),
            "average_inventory_mean": mean("average_inventory"),
            "median_inventory_mean": mean("median_inventory"),
            "max_inventory_mean": mean("max_inventory"),
            "inventory_days_mean": mean("inventory_days"),
            "days_of_supply_mean": mean("average_days_of_supply"),
            "replenishment_count_mean": mean("replenishment_count"),
            "replenishment_quantity_mean": mean("replenishment_quantity"),
            "average_order_quantity_mean": mean("average_order_quantity"),
            "replenishment_interval_mean": mean("replenishment_interval_mean"),
            "observed_fill_rate_mean_secondary": mean("fill_rate"),
            "delta_availability_mean": mean("delta_availability"),
            "delta_stockout_days_mean": mean("delta_stockout_days"),
            "delta_avg_inventory_mean": mean("delta_avg_inventory"),
            "delta_replenishments_mean": mean("delta_replenishments"),
            "result_classes": {name: sum(row.get("result_class") == name for row in values) for name in (
                "CLEAR_WIN", "AVAILABILITY_WIN_WITH_INVENTORY_COST",
                "INVENTORY_WIN_WITH_AVAILABILITY_COST", "LOGISTICS_COST", "DOMINATED", "INCONCLUSIVE",
            ) if any(row.get("result_class") == name for row in values)},
            "pareto_optimal": sum(row.get("pareto_status") == "PARETO_OPTIMAL" for row in values),
            "ROBUST_LT_COUNT": max(int(row.get("ROBUST_LT_COUNT") or 0) for row in values),
        })
    return output


def _lead_time_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        parameters = json.dumps(row.get("policy_parameters", {}), sort_keys=True, default=str)
        by_policy[(str(row["Policy"]), parameters)].append(row)
    output = []
    for (policy, parameters), values in sorted(by_policy.items()):
        output.append({
            "Policy": policy,
            "policy_parameters": json.loads(parameters),
            "ROBUST_LT_COUNT": max(int(row.get("ROBUST_LT_COUNT") or 0) for row in values),
            "PARETO_LT_COUNT": max(int(row.get("pareto_lt_count") or 0) for row in values),
            "lead_times": [{
                "LeadTimeScenario": row["LeadTimeScenario"],
                "availability": row["policy_availability"],
                "stockout_days": row["policy_stockout_days"],
                "average_inventory": row["policy_avg_inventory"],
                "replenishments": row["policy_replenishments"],
                "delta_availability": row["delta_availability"],
                "delta_stockout_days": row["delta_stockout_days"],
                "delta_avg_inventory": row["delta_avg_inventory"],
                "delta_replenishments": row["delta_replenishments"],
                "result_class": row["result_class"],
                "pareto_status": row["pareto_status"],
            } for row in sorted(values, key=lambda item: int(item["LeadTimeScenario"]))],
        })
    return output


def _runtime_contracts(pair: tuple[str, str], rows: list[dict[str, Any]]) -> dict[str, str]:
    config = PolicyConfiguration("REORDER_POINT", {"service_level": 0.98})
    original = simulate_pair(pair[0], pair[1], rows, config, 3, trace=True)
    changed = [dict(row) for row in rows]
    pivot = len(changed) // 2
    for row in changed[pivot:]:
        row["OBSERVED_DEMAND"] = float(row["OBSERVED_DEMAND"]) * 11 + 1
    changed_result = simulate_pair(pair[0], pair[1], changed, config, 3, trace=True)
    original_prior = [r for r in original["trace"] if r["date"] < rows[pivot]["Date"]]
    changed_prior = [r for r in changed_result["trace"] if r["date"] < rows[pivot]["Date"]]
    lookahead = [
        (r["order_qty"], r["order_trigger"], r["inventory_position"])
        for r in original_prior
    ] == [
        (r["order_qty"], r["order_trigger"], r["inventory_position"])
        for r in changed_prior
    ]
    conservation = all(
        abs(r["closing_stock"] - (r["opening_stock"] + r["arrival"] - r["fulfilled_demand"])) < 1e-9
        and r["closing_stock"] >= 0
        for r in original["trace"]
    )
    first = run_pair_for_signature(pair, rows, config)
    second = run_pair_for_signature(pair, rows, config)
    return {
        "NO_LOOKAHEAD": "PASS" if lookahead else "FAIL",
        "INVENTORY_CONSERVATION": "PASS" if conservation else "FAIL",
        "DETERMINISM": "PASS" if first == second else "FAIL",
    }


def run_pair_for_signature(pair: tuple[str, str], rows: list[dict[str, Any]], config: PolicyConfiguration) -> tuple[Any, ...]:
    result = run_pair(pair[0], pair[1], rows, [], [config], [3])
    return deterministic_signature(result["simulations"][0])


def run(input_dir: Path = DEFAULT_INPUT, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    for filename in (
        "current_policy.jsonl", "policy_metrics.jsonl", "pareto_candidates.jsonl",
        "product_summary.jsonl", "lead_time_robustness.jsonl", "aggregate.json",
        "gate_result.json", "resource_metrics.jsonl",
    ):
        (output / filename).unlink(missing_ok=True)
    started = time.monotonic()
    guard = ResourceGuard(output)
    guard.check("input_before", 0, 0, 1)
    stock, stock_row_count = _read_stock_index(input_dir / "daily_item_branch_stock.jsonl.gz")
    pairs = _select_pairs(stock, ("2A",), EXPECTED_PAIRS)
    if len(pairs) != EXPECTED_PAIRS or any(len(stock[pair]) != EXPECTED_DAYS for pair in pairs):
        raise RuntimeError("Gate 5B requires exactly the Gate 5A 10 pairs with 365 daily rows")
    event_rows = _read_jsonl(input_dir / "replenishment_events.jsonl.gz")
    episode_path = input_dir / "stockout_episodes.jsonl.gz"
    episode_rows = _read_jsonl(episode_path) if episode_path.exists() else []
    selected = set(pairs)
    events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    episodes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in event_rows:
        key = (str(row["ItemCode"]), str(row["Branch"]))
        if key in selected:
            events[key].append(row)
    for row in episode_rows:
        key = (str(row["ItemCode"]), str(row["Branch"]))
        if key in selected:
            episodes[key].append(row)
    guard.check("input_loaded", stock_row_count + len(event_rows) + len(episode_rows), 0, 1)

    configurations = policy_configurations()
    if len(configurations) != EXPECTED_CONFIGURATIONS:
        raise RuntimeError("policy grid changed: Gate 5B requires the same 19 configurations")
    current_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    product_rows: list[dict[str, Any]] = []
    runtime = None
    for index, pair in enumerate(pairs, 1):
        daily = _daily_rows(stock[pair])
        normalised = normalise_daily_rows(daily)
        current = _current_contract(current_policy_metrics(pair[0], pair[1], normalised, events[pair]))
        current_audit = audit_current_pair(pair[0], pair[1], normalised, episodes[pair])
        current.update({
            "POSSIBLE_CENSORED_DEMAND_DAYS": current_audit["possible_censored_demand_days"],
            "censored_demand_analysis": "SEPARATE_ONLY_NOT_PRIMARY",
        })
        result = run_pair(pair[0], pair[1], normalised, events[pair], configurations, LEAD_TIME_SCENARIOS)
        current_rows.append(current)
        metric_rows.extend(result["simulations"])
        pareto = [row for row in result["simulations"] if row.get("pareto_status") == "PARETO_OPTIMAL"]
        candidate_rows.extend(_candidate_view(row) for row in pareto)
        problem, problem_detail = _problem_class(current, result["simulations"])
        product_rows.append({
            "ItemCode": pair[0], "Branch": pair[1],
            "CURRENT": current,
            "PROBLEM_CLASS": problem,
            "problem_class_detail": problem_detail,
            "BEST_NON_DOMINATED_POLICIES": [_candidate_view(row) for row in sorted(
                pareto,
                key=lambda row: (
                    -int(bool(row.get("robust_policy"))),
                    -float(row.get("policy_availability") or 0),
                    float(row.get("policy_avg_inventory") or 0),
                    int(row.get("policy_replenishments") or 0),
                    str(row.get("Policy")),
                    int(row.get("LeadTimeScenario") or 0),
                ),
            )],
            "LEAD_TIME_SENSITIVITY": _lead_time_summary(result["simulations"]),
            "observed_fill_rate_secondary": current.get("OBSERVED_FILL_RATE"),
        })
        if runtime is None:
            runtime = _runtime_contracts(pair, normalised)
        guard.check(
            f"pair_{index:02d}_{pair[1]}_{pair[0]}",
            len(normalised) + len(events[pair]) + len(episodes[pair]),
            len(result["simulations"]) + 1,
            1,
        )

    _write_jsonl(output / "current_policy.jsonl", current_rows)
    _write_jsonl(output / "policy_metrics.jsonl", metric_rows)
    _write_jsonl(output / "pareto_candidates.jsonl", candidate_rows)
    _write_jsonl(output / "product_summary.jsonl", product_rows)
    lead_time_rows = [
        {"ItemCode": product["ItemCode"], "Branch": product["Branch"], **row}
        for product in product_rows
        for row in product["LEAD_TIME_SENSITIVITY"]
    ]
    _write_jsonl(output / "lead_time_robustness.jsonl", lead_time_rows)
    aggregate = _aggregate(metric_rows)
    _dump_json(output / "aggregate.json", aggregate)
    resource = guard.summary()
    problem_counts = defaultdict(int)
    for row in product_rows:
        problem_counts[row["PROBLEM_CLASS"]] += 1
    distinguishable = any(
        row.get("result_class") in {
            "CLEAR_WIN", "AVAILABILITY_WIN_WITH_INVENTORY_COST",
            "INVENTORY_WIN_WITH_AVAILABILITY_COST", "LOGISTICS_COST",
        }
        for row in metric_rows
    )
    result = {
        "gate": "TELCHI_AVAILABILITY_BASED_BACKTEST_V1",
        "verdict": "TELCHI_AVAILABILITY_BACKTEST_V1_PASS" if all(
            value == "PASS" for value in (runtime or {}).values()
        ) and resource["resource_abort_count"] == 0 else "DEGRADED",
        "context": {
            "ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION",
            "SOURCES": ["SAP_HANA", "DATA_LAKE"], "READ_ONLY": True, "SAP_WRITE_COUNT": 0,
            "PRIMARY_UNIVERSE": "ItemCode LIKE 'L%'", "NON_L_UNIVERSE": "EXCLUDED_FROM_PRIMARY_ANALYSIS",
            "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED",
        },
        "continuation": "FILL_RATE_CEILING_EFFECT_DETECTED",
        "level": "A",
        "level_b_executed": False,
        "universe": {
            "branches": ["2A"], "ItemCodes": [item for item, _ in pairs],
            "combinations": len(pairs), "daily_rows": sum(len(stock[pair]) for pair in pairs),
            "days": EXPECTED_DAYS, "date_start": min(min(stock[pair]) for pair in pairs),
            "date_end": max(max(stock[pair]) for pair in pairs), "non_l_pairs": 0,
        },
        "policy_grid": {
            "configurations": len(configurations), "lead_time_scenarios": list(LEAD_TIME_SCENARIOS),
            "simulation_rows": len(metric_rows), "expected_simulation_rows": EXPECTED_PAIRS * EXPECTED_CONFIGURATIONS * len(LEAD_TIME_SCENARIOS),
            "pareto_dimensions": ["Availability_UP", "AverageInventory_DOWN", "ReplenishmentCount_DOWN"],
            "fill_rate_role": "SECONDARY_CONTROL_ONLY",
        },
        "primary_metrics": [
            "availability", "stockout_days", "stockout_episodes", "stockout_duration_mean",
            "stockout_duration_median", "stockout_duration_p90", "stockout_duration_max",
            "average_inventory", "median_inventory", "max_inventory", "inventory_days",
            "days_of_supply", "replenishment_count", "replenishment_quantity",
            "average_order_quantity", "replenishment_interval",
        ],
        "problem_class_counts": dict(problem_counts),
        "classification": {
            "CLEAR_WIN": "service improves or remains practically equivalent while inventory is not higher",
            "AVAILABILITY_WIN_WITH_INVENTORY_COST": "availability and stockout improve with higher inventory",
            "INVENTORY_WIN_WITH_AVAILABILITY_COST": "inventory falls while availability/stockout worsens",
            "LOGISTICS_COST": "service/inventory advantage requires excessive replenishment count",
            "DOMINATED": "another policy is no worse on availability, inventory and replenishments and strictly better on one",
            "INCONCLUSIVE": "no clear primary-metric advantage or insufficient state",
        },
        "robustness": {
            "definition": "ROBUST_LT_COUNT counts lead-time scenarios where the policy is non-dominated and has service improvement or lower inventory with comparable service",
            "scenarios": list(LEAD_TIME_SCENARIOS), "artifact": "lead_time_robustness.jsonl",
        },
        "censored_demand": {
            "status": "SEPARATE_ANALYSIS_NOT_USED_AS_PRIMARY_CRITERION",
            "possible_censored_demand_is_not_lost_sales": True,
            "imputation": "NOT_USED_IN_PRIMARY_BACKTEST",
        },
        "comparison": {
            "current_artifact": "current_policy.jsonl", "metrics_artifact": "policy_metrics.jsonl",
            "candidate_artifact": "pareto_candidates.jsonl", "product_artifact": "product_summary.jsonl",
            "aggregate_artifact": "aggregate.json",
        },
        "decision": "EXECUTE_LEVEL_B" if distinguishable else "DO_NOT_EXECUTE_LEVEL_B",
        "decision_cause": (
            "At least one policy has a reproducible primary-metric win or quantified service/inventory trade-off."
            if distinguishable
            else "All policies are dominated or inconclusive under the availability-based dimensions."
        ),
        "engine_validation": {
            **(runtime or {"NO_LOOKAHEAD": "DEGRADED", "INVENTORY_CONSERVATION": "DEGRADED", "DETERMINISM": "DEGRADED"}),
            "RESOURCE_SAFETY": "PASS" if resource["resource_abort_count"] == 0 else "FAIL",
            "SAP_WRITE_COUNT": 0,
        },
        "resource_safety": {**resource, "elapsed_seconds": round(time.monotonic() - started, 4)},
        "artifacts": [
            "current_policy.jsonl", "policy_metrics.jsonl", "pareto_candidates.jsonl",
            "product_summary.jsonl", "lead_time_robustness.jsonl", "aggregate.json",
            "resource_metrics.jsonl", "gate_result.json",
        ],
    }
    _dump_json(output / "gate_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI Gate 5B availability-based backtest V1")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.output)
    except ResourceGuardAbort as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        _dump_json(args.output / "gate_result.json", {
            "gate": "TELCHI_AVAILABILITY_BASED_BACKTEST_V1", "verdict": "DEGRADED",
            "result": "RESOURCE_GUARD_ABORT", "MAX_WORKERS": 1, "SAP_WRITE_COUNT": 0,
            "RESOURCE_GUARD": "ENABLED", "error": str(exc), "snapshot": resource_snapshot(),
        })
        return 3
    print(json.dumps({
        "gate": result["gate"], "verdict": result["verdict"], "universe": result["universe"],
        "policy_grid": result["policy_grid"], "problem_class_counts": result["problem_class_counts"],
        "decision": result["decision"], "engine_validation": result["engine_validation"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
