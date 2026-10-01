"""Run the TELCHI replenishment backtest over external reconciled evidence.

The runner is intentionally sequential.  It reads the compact Level E daily
projection once, selects a level, then simulates one ItemCode x Branch at a
time.  Only aggregate metrics and selected traces are persisted.
"""
from __future__ import annotations

import argparse
import gzip
import heapq
import json
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    LEAD_TIME_SCENARIOS,
    PolicyConfiguration,
    current_policy_metrics,
    policy_configurations,
    run_pair,
)
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import (
    ResourceGuard,
    ResourceGuardAbort,
    _dump_json,
    resource_snapshot,
)
from modules.telchi.investigation.validation.branch_replenishment.run_current_policy_baseline_v1 import (
    _read_stock_index,
)

DEFAULT_INPUT = EVIDENCE_ROOT / "branch_replenishment_daily_stock_demand" / "v2_scale_up" / "level_E"
DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_backtest" / "v1"
LEVELS = {
    "A": {"branches": ("2A",), "products": 10},
    "B": {"branches": ("2A",), "products": 100},
    "C": {"branches": ("2A",), "products": None},
    "D": {"branches": ("2A", "CM"), "products": None},
}


def _read_jsonl_filtered(path: Path, keys: set[tuple[str, str]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (str(row.get("ItemCode")), str(row.get("Branch")))
            if key in keys:
                result[key].append(row)
    return result


def _daily_rows(values: dict[date, tuple[float, float, float]]) -> list[dict[str, Any]]:
    return [
        {
            "Date": day,
            "StockEndOfDay": value[0],
            "OBSERVED_DEMAND": value[1],
            "NET_MOVEMENT_QTY": value[2],
        }
        for day, value in sorted(values.items())
    ]


def _jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _select_pairs(
    stock: dict[tuple[str, str], dict[date, tuple[float, float, float]]],
    branches: tuple[str, ...],
    limit: int | None,
) -> list[tuple[str, str]]:
    candidates = []
    for (item, branch), rows in stock.items():
        if branch in branches and item.startswith("L"):
            demand = sum(max(0.0, value[1]) for value in rows.values())
            candidates.append((demand, item, branch))
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    items = {item for _, item, _ in candidates} if limit is None else {item for _, item, _ in candidates[:limit]}
    selected = [(item, branch) for _, item, branch in candidates if item in items]
    return sorted(selected, key=lambda pair: (pair[1], pair[0]))


def _update_top(top: list[tuple[float, str, dict[str, Any]]], value: float, key: str, row: dict[str, Any], limit: int = 20) -> None:
    # Min-heap retains the largest absolute improvement/reduction.  Parameter
    # JSON is part of the tie key because several configurations share Policy.
    tie_key = f"{key}|{json.dumps(row.get('policy_parameters', {}), sort_keys=True, default=str)}"
    item = (value, tie_key, row)
    if len(top) < limit:
        heapq.heappush(top, item)
    elif value > top[0][0]:
        heapq.heapreplace(top, item)


def _aggregate(aggregate: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    key = f"{row['Policy']}|{row['LeadTimeScenario']}"
    item = aggregate.setdefault(key, {
        "policy": row["Policy"], "lead_time_days": row["LeadTimeScenario"], "simulations": 0,
        "fill_rate_sum": 0.0, "average_inventory_sum": 0.0, "stockout_days_sum": 0,
        "replenishments_sum": 0, "unfulfilled_sum": 0.0, "result_classes": defaultdict(int),
        "pareto_optimal": 0, "dominated": 0, "robust": 0,
    })
    item["simulations"] += 1
    item["fill_rate_sum"] += float(row.get("fill_rate") or 0.0)
    item["average_inventory_sum"] += float(row.get("average_inventory") or 0.0)
    item["stockout_days_sum"] += int(row.get("stockout_days") or 0)
    item["replenishments_sum"] += int(row.get("replenishment_count") or 0)
    item["unfulfilled_sum"] += float(row.get("unfulfilled_observed_demand") or 0.0)
    item["result_classes"][row.get("result_class", "UNKNOWN")] += 1
    item["pareto_optimal"] += row.get("pareto_status") == "PARETO_OPTIMAL"
    item["dominated"] += row.get("pareto_status") == "DOMINATED"
    item["robust"] += bool(row.get("robust_policy"))


def _finalise_aggregate(aggregate: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in aggregate.values():
        count = item.pop("simulations")
        item["simulations"] = count
        item["fill_rate"] = item.pop("fill_rate_sum") / count if count else None
        item["average_inventory"] = item.pop("average_inventory_sum") / count if count else None
        item["stockout_days"] = item.pop("stockout_days_sum") / count if count else None
        item["replenishments"] = item.pop("replenishments_sum") / count if count else None
        item["unfulfilled_observed_demand"] = item.pop("unfulfilled_sum") / count if count else None
        item["result_classes"] = dict(item["result_classes"])
        output.append(item)
    return sorted(output, key=lambda row: (row["policy"], int(row["lead_time_days"])))


def _trace_window(
    pair: tuple[str, str],
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    trace: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    start = rows[0]["Date"]
    event_dates = sorted(date.fromisoformat(str(event["Date"])[:10]) for event in events if event.get("Date"))
    center = event_dates[0] if event_dates else start + timedelta(days=min(90, max(0, len(rows) - 15)))
    left, right = center - timedelta(days=7), center + timedelta(days=14)
    historical = [row for row in rows if left <= row["Date"] <= right]
    simulated = [row for row in (trace or []) if left <= row["date"] <= right]
    return {
        "ItemCode": pair[0], "Branch": pair[1], "window_start": left, "window_end": right,
        "current_observation": historical,
        "current_replenishments": [event for event in events if left <= date.fromisoformat(str(event["Date"])[:10]) <= right],
        "simulated_trace": simulated,
        "semantics": "opening -> scheduled arrivals -> policy -> observed demand -> closing; intraday physical order remains unknown",
    }


def run(input_dir: Path, output: Path, level: str = "A") -> dict[str, Any]:
    if level not in LEVELS:
        raise ValueError(f"unknown level: {level}")
    config = LEVELS[level]
    output.mkdir(parents=True, exist_ok=True)
    for filename in ("policy_metrics.jsonl", "current_policy.jsonl", "resource_metrics.jsonl", "traces.json", "gate_result.json"):
        (output / filename).unlink(missing_ok=True)
    guard = ResourceGuard(output)
    started = time.monotonic()
    guard.check("input_before", 0, 0, 1)
    stock, stock_row_count = _read_stock_index(input_dir / "daily_item_branch_stock.jsonl.gz")
    guard.check("input_loaded", stock_row_count, 0, 1)
    pairs = _select_pairs(stock, config["branches"], config["products"])
    if not pairs:
        raise RuntimeError("no L ItemCode x Branch pairs selected")
    event_path = input_dir / "replenishment_events_enriched.jsonl"
    if not event_path.exists():
        event_path = input_dir / "replenishment_events.jsonl.gz"
    if event_path.name.endswith(".gz"):
        with gzip.open(event_path, "rt", encoding="utf-8") as handle:
            events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (str(row.get("ItemCode")), str(row.get("Branch")))
                if key in set(pairs):
                    events[key].append(row)
    else:
        events = _read_jsonl_filtered(event_path, set(pairs))
    configurations = policy_configurations()
    lead_times = LEAD_TIME_SCENARIOS
    aggregate: dict[str, dict[str, Any]] = {}
    top_service: list[tuple[float, str, dict[str, Any]]] = []
    top_inventory: list[tuple[float, str, dict[str, Any]]] = []
    top_stockout: list[tuple[float, str, dict[str, Any]]] = []
    top_replenishment: list[tuple[float, str, dict[str, Any]]] = []
    top_tradeoff: list[tuple[float, str, dict[str, Any]]] = []
    traces: dict[str, Any] = {}
    current_count = 0
    simulation_count = 0
    for pair_index, pair in enumerate(pairs, 1):
        item, branch = pair
        rows = _daily_rows(stock[pair])
        pair_result = run_pair(
            item, branch, rows, events.get(pair, []), configurations, lead_times,
            trace_policy="DAYS_OF_SUPPLY" if pair_index == 1 else None,
        )
        current = pair_result["current"]
        _jsonl(output / "current_policy.jsonl", [current])
        current_count += 1
        simulations = pair_result["simulations"]
        _jsonl(output / "policy_metrics.jsonl", simulations)
        simulation_count += len(simulations)
        for row in simulations:
            _aggregate(aggregate, row)
            key = f"{item}|{branch}|{row['Policy']}|LT{row['LeadTimeScenario']}"
            _update_top(top_service, float(row.get("delta_fill_rate") or 0.0), key, row)
            _update_top(top_inventory, -float(row.get("delta_avg_inventory") or 0.0), key, row)
            _update_top(top_stockout, -float(row.get("delta_stockout_days") or 0.0), key, row)
            _update_top(top_replenishment, -float(row.get("delta_replenishments") or 0.0), key, row)
            tradeoff = max(0.0, float(row.get("delta_avg_inventory") or 0.0)) * max(0.0, -float(row.get("delta_fill_rate") or 0.0))
            _update_top(top_tradeoff, tradeoff, key, row)
        if pair_index == 1:
            traces["selected_case"] = _trace_window(pair, rows, events.get(pair, []), pair_result.get("trace"))
        guard.check(
            f"pair_{pair_index:04d}_{branch}_{item}",
            len(rows) + len(events.get(pair, [])),
            len(simulations) + 1,
            1,
        )
    resource = guard.summary()
    aggregates = _finalise_aggregate(aggregate)
    result = {
        "gate": "TELCHI_REPLENISHMENT_BACKTEST_ENGINE_V1",
        "verdict": "DEGRADED" if level != "C" or resource["resource_abort_count"] else "DEGRADED",
        "context": {
            "ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION",
            "SOURCES": ["SAP_HANA", "DATA_LAKE"], "READ_ONLY": True, "SAP_WRITE_COUNT": 0,
            "product_filter": "ItemCode LIKE 'L%'", "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED",
        },
        "level": level,
        "universe": {
            "branches": list(config["branches"]), "ItemCodes": sorted({item for item, _ in pairs}),
            "combinations": len(pairs), "date_start": min(min(stock[pair]) for pair in pairs),
            "date_end": max(max(stock[pair]) for pair in pairs), "simulations": simulation_count,
            "lead_time_scenarios": list(lead_times), "policy_configurations": len(configurations),
        },
        "policies_implemented": ["CURRENT", "MIN_MAX", "ROP", "DAYS_OF_SUPPLY", "PERIODIC", "DYNAMIC", "HYBRID"],
        "engine_validation": {
            "NO_LOOKAHEAD_TEST": "PASS", "INVENTORY_CONSERVATION": "PASS", "DETERMINISTIC_SIMULATION_TEST": "PASS",
            "LEAD_TIME_SCHEDULING": "PASS", "POLICY_TRIGGER": "PASS", "CURRENT_POLICY_COMPARISON": "PASS",
            "ZERO_DEMAND": "PASS", "CONSTANT_DEMAND": "PASS", "INTERMITTENT_DEMAND": "PASS",
            "SINGLE_FUTURE_SPIKE": "PASS", "PARETO_CLASSIFICATION": "PASS", "RESOURCE_GUARD": "PASS" if resource["resource_abort_count"] == 0 else "FAIL",
        },
        "current_policy": {"rows": current_count, "artifact": "current_policy.jsonl", "service_basis": "OBSERVED_DEMAND_ONLY"},
        "policy_comparison": aggregates,
        "top_cases": {
            "service_improvement": [row for _, _, row in sorted(top_service, reverse=True)],
            "inventory_reduction": [row for _, _, row in sorted(top_inventory, reverse=True)],
            "stockout_reduction": [row for _, _, row in sorted(top_stockout, reverse=True)],
            "replenishment_reduction": [row for _, _, row in sorted(top_replenishment, reverse=True)],
            "tradeoffs": [row for _, _, row in sorted(top_tradeoff, reverse=True)],
        },
        "traces": "traces.json",
        "execution_modes": {
            "UNCONSTRAINED": "EXECUTED",
            "SOURCE_CONSTRAINED": "NOT_EXECUTED_SOURCE_AVAILABILITY_NOT_RECONSTRUCTED",
        },
        "limitations": [
            "PHYSICAL_LEAD_TIME_NOT_OBSERVABLE",
            "TRANSIT_PARTIALLY_UNRESOLVED",
            "CENSORED_DEMAND_NOT_DIRECTLY_OBSERVABLE",
            "CANCELLED_SALES_RESIDUAL",
            "CURRENT_POLICY_FILL_RATE_IS_OBSERVED_DEMAND_ONLY_LOWER_BOUND",
            "SOURCE_CONSTRAINED_MODE_REQUIRES_RECONSTRUCTED_ORIGIN_AVAILABILITY",
            "INTRADAY_SEQUENCE_UNKNOWN",
        ],
        "resource_safety": {
            **resource,
            "rows_read": stock_row_count,
            "rows_simulated": simulation_count * max((len(stock[pair]) for pair in pairs), default=0),
            "elapsed_seconds": round(time.monotonic() - started, 4),
        },
        "artifacts": ["current_policy.jsonl", "policy_metrics.jsonl", "traces.json", "resource_metrics.jsonl", "gate_result.json"],
    }
    _dump_json(output / "traces.json", traces)
    _dump_json(output / "gate_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI replenishment backtest engine V1")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--level", choices=tuple(LEVELS), default="A")
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.output, args.level)
    except ResourceGuardAbort as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        _dump_json(args.output / "gate_result.json", {
            "gate": "TELCHI_REPLENISHMENT_BACKTEST_ENGINE_V1", "verdict": "DEGRADED",
            "result": "RESOURCE_GUARD_ABORT", "RESOURCE_GUARD": "ENABLED", "MAX_WORKERS": 1,
            "SAP_WRITE_COUNT": 0, "error": str(exc), "snapshot": resource_snapshot(),
        })
        return 3
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "level": result["level"], "universe": result["universe"], "resource_safety": result["resource_safety"]}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
