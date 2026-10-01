"""TELCHI Gate 5C Level B: stratified 100-product availability backtest.

The runner deliberately keeps the Level 5B policy grid and simulation semantics,
but changes the universe selection and reporting layer.  Products are selected
from the complete 2A ``L%`` universe by observed behaviour, not by a simple
``LIMIT 100`` query.  The primary run stores pair/configuration aggregates;
daily traces are written only for a small, reproducible priority case set.

This is investigation-only.  It never connects to SAP and never writes SAP.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    EPSILON,
    LEAD_TIME_SCENARIOS,
    METRIC_TOLERANCE,
    PolicyConfiguration,
    classify_robustness,
    compare_to_current,
    current_policy_metrics,
    deterministic_signature,
    pareto_frontier,
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
)

DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_level_b" / "v1_B3_100"
EXPECTED_DAYS = 365
EXPECTED_CONFIGURATIONS = 19
MIN_HISTORY_DAYS = 365
SMOKE_COUNTS = (25, 50, 100)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _quantile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _item_features(
    stock: Mapping[tuple[str, str], Mapping[date, tuple[float, float, float]]],
    events: Iterable[Mapping[str, Any]],
    *,
    branch: str = "2A",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build deterministic observed-behaviour features for valid 2A products."""
    event_counts: Counter[str] = Counter()
    for event in events:
        if str(event.get("Branch")) == branch and str(event.get("ItemCode", "")).startswith("L"):
            event_counts[str(event["ItemCode"])] += 1

    features: list[dict[str, Any]] = []
    excluded = Counter()
    for (item, item_branch), values in sorted(stock.items()):
        if item_branch != branch or not item.startswith("L"):
            continue
        rows = list(values.values())
        days = len(rows)
        demand = [max(0.0, _number(value[1])) for value in rows]
        stock_values = [max(0.0, _number(value[0])) for value in rows]
        movements = [abs(_number(value[2])) for value in rows]
        demand_sum = sum(demand)
        demand_mean = statistics.fmean(demand) if demand else 0.0
        demand_std = statistics.pstdev(demand) if len(demand) > 1 else 0.0
        record = {
            "ItemCode": item,
            "Branch": item_branch,
            "history_days": days,
            "demand_sum": demand_sum,
            "demand_days": sum(value > EPSILON for value in demand),
            "demand_rate": (sum(value > EPSILON for value in demand) / days) if days else 0.0,
            "demand_cv": demand_std / demand_mean if demand_mean > EPSILON else None,
            "stockout_days": sum(value <= EPSILON for value in stock_values),
            "availability": (sum(value > EPSILON for value in stock_values) / days) if days else 0.0,
            "average_inventory": statistics.fmean(stock_values) if stock_values else 0.0,
            "max_inventory": max(stock_values, default=0.0),
            "movement_abs": sum(movements),
            "replenishment_count": event_counts[item],
            "active": bool(demand_sum > EPSILON or sum(movements) > EPSILON),
        }
        if days < MIN_HISTORY_DAYS:
            excluded["INSUFFICIENT_HISTORY"] += 1
            continue
        if not record["active"]:
            excluded["INACTIVE"] += 1
            continue
        features.append(record)

    if not features:
        return [], {"excluded": dict(excluded), "thresholds": {}}
    thresholds = {
        "demand_q33": _quantile([r["demand_sum"] for r in features], 1 / 3),
        "demand_q67": _quantile([r["demand_sum"] for r in features], 2 / 3),
        "cv_q50": _quantile([r["demand_cv"] or 0.0 for r in features], 0.5),
        "stockout_q67_positive": _quantile([r["stockout_days"] for r in features if r["stockout_days"] > 0], 2 / 3),
        "inventory_q67": _quantile([r["average_inventory"] for r in features], 2 / 3),
        "replenishment_q50": _quantile([r["replenishment_count"] for r in features], 0.5),
        "demand_rate_q33": _quantile([r["demand_rate"] for r in features], 1 / 3),
    }
    for record in features:
        demand = record["demand_sum"]
        record["rotation_band"] = (
            "LOW" if demand <= thresholds["demand_q33"] else
            "MEDIUM" if demand <= thresholds["demand_q67"] else "HIGH"
        )
        record["demand_pattern"] = "INTERMITTENT" if record["demand_rate"] <= thresholds["demand_rate_q33"] else "REGULAR"
        record["demand_variability"] = "VARIABLE" if (record["demand_cv"] or 0.0) > thresholds["cv_q50"] else "STABLE"
        record["stockout_frequency"] = (
            "NONE" if record["stockout_days"] == 0 else
            "FREQUENT" if record["stockout_days"] >= max(1, thresholds["stockout_q67_positive"]) else "OCCASIONAL"
        )
        record["availability_band"] = "HIGH" if record["availability"] >= _quantile([r["availability"] for r in features], 2 / 3) else "OTHER"
        record["inventory_band"] = "HIGH" if record["average_inventory"] >= thresholds["inventory_q67"] else "OTHER"
        record["replenishment_band"] = "MANY" if record["replenishment_count"] >= thresholds["replenishment_q50"] else "FEW"
    return features, {"excluded": dict(excluded), "thresholds": thresholds}


def select_stratified_products(
    stock: Mapping[tuple[str, str], Mapping[date, tuple[float, float, float]]],
    events: Iterable[Mapping[str, Any]],
    count: int,
    *,
    branch: str = "2A",
    control_item: str = "L02467",
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Select a nested, behaviour-stratified product sample without cherry-picking."""
    if count not in SMOKE_COUNTS:
        raise ValueError(f"count must be one of {SMOKE_COUNTS}")
    event_rows = list(events)
    features, discovery = _item_features(stock, event_rows, branch=branch)
    by_item = {row["ItemCode"]: row for row in features}
    if len(features) < count:
        raise RuntimeError(f"only {len(features)} valid active L products available; need {count}")

    # Each list is a transparent behavioural stratum.  Round-robin across all
    # lists gives coverage of rare behaviours while retaining deterministic order.
    strata: dict[str, list[dict[str, Any]]] = {
        "HIGH_ROTATION": sorted(features, key=lambda r: (-r["demand_sum"], r["ItemCode"])),
        "MEDIUM_ROTATION": sorted(
            (r for r in features if r["rotation_band"] == "MEDIUM"), key=lambda r: (-r["demand_sum"], r["ItemCode"])
        ),
        "LOW_ROTATION": sorted(
            (r for r in features if r["rotation_band"] == "LOW"), key=lambda r: (r["demand_sum"], r["ItemCode"])
        ),
        "INTERMITTENT": sorted(
            (r for r in features if r["demand_pattern"] == "INTERMITTENT"), key=lambda r: (r["demand_rate"], r["ItemCode"])
        ),
        "STOCKOUT_FREQUENT": sorted(
            (r for r in features if r["stockout_frequency"] == "FREQUENT"), key=lambda r: (-r["stockout_days"], r["ItemCode"])
        ),
        "AVAILABILITY_HIGH": sorted(
            (r for r in features if r["availability_band"] == "HIGH"), key=lambda r: (-r["availability"], r["ItemCode"])
        ),
        "INVENTORY_HIGH": sorted(
            (r for r in features if r["inventory_band"] == "HIGH"), key=lambda r: (-r["average_inventory"], r["ItemCode"])
        ),
        "REPLENISHMENTS_MANY": sorted(
            (r for r in features if r["replenishment_band"] == "MANY"), key=lambda r: (-r["replenishment_count"], r["ItemCode"])
        ),
        "REPLENISHMENTS_FEW": sorted(
            (r for r in features if r["replenishment_band"] == "FEW"), key=lambda r: (r["replenishment_count"], r["ItemCode"])
        ),
        "DEMAND_STABLE": sorted(
            (r for r in features if r["demand_variability"] == "STABLE"), key=lambda r: (r["demand_cv"] or 0.0, r["ItemCode"])
        ),
        "DEMAND_VARIABLE": sorted(
            (r for r in features if r["demand_variability"] == "VARIABLE"), key=lambda r: (-(r["demand_cv"] or 0.0), r["ItemCode"])
        ),
    }
    selected: list[str] = []
    selected_set: set[str] = set()
    if control_item in by_item:
        selected.append(control_item)
        selected_set.add(control_item)
    pointers = {name: 0 for name in strata}
    while len(selected) < count:
        progressed = False
        for name, candidates in strata.items():
            while pointers[name] < len(candidates) and candidates[pointers[name]]["ItemCode"] in selected_set:
                pointers[name] += 1
            if pointers[name] >= len(candidates):
                continue
            item = candidates[pointers[name]]["ItemCode"]
            pointers[name] += 1
            if item not in selected_set:
                selected.append(item)
                selected_set.add(item)
                progressed = True
                if len(selected) == count:
                    break
        if not progressed:
            break
    if len(selected) != count:
        raise RuntimeError("stratified selector could not fill requested sample")
    selected_rows = [by_item[item] for item in selected]
    criteria_counts = {
        name: sum(row["ItemCode"] in selected_set for row in candidates)
        for name, candidates in strata.items()
    }
    selection = {
        "method": "DETERMINISTIC_STRATIFIED_ROUND_ROBIN",
        "branch": branch,
        "filter": "ItemCode LIKE 'L%'",
        "requested_products": count,
        "selected_products": len(selected),
        "selected_item_codes": selected,
        "control_item": control_item,
        "control_in_sample": control_item in selected_set,
        "strata_coverage": criteria_counts,
        "criteria": [
            "high/medium/low rotation by empirical demand-sum tertiles",
            "intermittent demand by empirical demand-day-rate lower tertile",
            "stockout frequent by upper tertile among positive stockout days",
            "high availability and inventory by empirical upper tertile",
            "many/few replenishments by empirical median",
            "stable/variable demand by empirical CV median",
            "round-robin over non-empty strata; ItemCode is only a deterministic tie-breaker",
        ],
        "universe_discovery": {
            "valid_active_l_products": len(features),
            "excluded": discovery["excluded"],
            "thresholds": discovery["thresholds"],
        },
        "selected_features": selected_rows,
    }
    return [(item, branch) for item in selected], selection


def _current_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    availability = float(row.get("availability_rate") or 0.0)
    stockout = int(row.get("historical_stockout_days_raw") or row.get("stockout_days") or 0)
    result.update({
        "CURRENT_AVAILABILITY": availability,
        "CURRENT_STOCKOUT_DAYS": stockout,
        "CURRENT_AVG_INVENTORY": float(row.get("average_inventory") or 0.0),
        "CURRENT_REPLENISHMENTS": int(row.get("replenishment_count") or 0),
        "CURRENT_MEDIAN_INTERVAL": row.get("replenishment_interval_median"),
        "CURRENT_MEDIAN_QTY": row.get("median_order_quantity"),
        "service_metric_primary": "AVAILABILITY",
        "fill_rate_metric_role": "SECONDARY_CONTROL_ONLY",
    })
    return result


def _run_pair_level_b(
    item: str,
    branch: str,
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    configurations: list[PolicyConfiguration],
) -> dict[str, Any]:
    """Reuse Gate 5B's pair runner and its exact robustness semantics.

    In particular, Pareto and ``ROBUST_LT_COUNT`` are intentionally not
    redefined here.  This is what makes the L02467 control comparable to 5B
    and prevents a Level B reporting change from looking like a policy change.
    """
    current = _current_contract(current_policy_metrics(item, branch, rows, events))
    result = run_pair(item, branch, rows, events, configurations, LEAD_TIME_SCENARIOS)
    # run_pair computes the current baseline itself; retain the explicit
    # current contract used by this gate (including the raw stockout aliases).
    return {"current": current, "simulations": result["simulations"]}


def _problem_class(current: Mapping[str, Any], simulations: list[Mapping[str, Any]], history_days: int) -> tuple[str, dict[str, Any]]:
    if history_days < MIN_HISTORY_DAYS:
        return "INSUFFICIENT_HISTORY", {"history_days": history_days, "minimum_history_days": MIN_HISTORY_DAYS}
    service_problem = int(current.get("CURRENT_STOCKOUT_DAYS") or 0) > 0
    excess = any(
        row.get("pareto_status") == "PARETO_OPTIMAL"
        and abs(float(row.get("delta_availability") or 0.0)) <= METRIC_TOLERANCE
        and int(row.get("delta_stockout_days") or 0) == 0
        and float(row.get("delta_avg_inventory") or 0.0) < -EPSILON
        for row in simulations
    )
    if service_problem and excess:
        result = "BOTH"
    elif service_problem:
        result = "SERVICE_PROBLEM"
    elif excess:
        result = "EXCESS_INVENTORY_PROBLEM"
    else:
        result = "NEITHER"
    return result, {
        "service_problem": service_problem,
        "service_definition": "CURRENT stockout days > 0 (availability below 100% under the observed-stock semantic)",
        "excess_inventory_problem": excess,
        "excess_definition": "a Gate 5B-compatible Pareto policy preserves availability and stockout days while reducing average inventory",
    }


def _view(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "ItemCode", "Branch", "Policy", "policy_parameters", "LeadTimeScenario",
        "availability_rate", "availability_days", "stockout_days", "stockout_episodes",
        "stockout_duration_mean", "stockout_duration_median", "stockout_duration_p90",
        "stockout_duration_max", "average_inventory", "median_inventory", "max_inventory",
        "inventory_days", "average_days_of_supply", "replenishment_count", "replenishment_quantity",
        "average_order_quantity", "median_order_quantity", "replenishment_interval_mean",
        "replenishment_interval_median", "fill_rate", "result_class", "pareto_status",
        "delta_availability", "delta_stockout_days", "delta_avg_inventory", "delta_replenishments",
        "ROBUST_LT_COUNT", "robust_policy", "pareto_lt_count", "robustness_class",
    )
    return {key: row.get(key) for key in keys}


def _improves(row: Mapping[str, Any]) -> bool:
    return row.get("pareto_status") == "PARETO_OPTIMAL" and (
        (float(row.get("delta_availability") or 0.0) > METRIC_TOLERANCE and int(row.get("delta_stockout_days") or 0) < 0)
        or (
            abs(float(row.get("delta_availability") or 0.0)) <= METRIC_TOLERANCE
            and int(row.get("delta_stockout_days") or 0) == 0
            and float(row.get("delta_avg_inventory") or 0.0) < -EPSILON
        )
    )


def _best(rows: list[Mapping[str, Any]], predicate: Any = None) -> dict[str, Any] | None:
    candidates = [row for row in rows if predicate(row)] if predicate else list(rows)
    if not candidates:
        return None
    return dict(sorted(candidates, key=lambda row: (
        -int(row.get("ROBUST_LT_COUNT") or 0),
        -float(row.get("delta_availability") or 0.0),
        int(row.get("delta_stockout_days") or 0),
        float(row.get("delta_avg_inventory") or 0.0),
        int(row.get("delta_replenishments") or 0),
        str(row.get("Policy")), json.dumps(row.get("policy_parameters", {}), sort_keys=True),
        int(row.get("LeadTimeScenario") or 0),
    ))[0])


def _lead_time_summary(simulations: list[Mapping[str, Any]], days: int) -> tuple[dict[str, Any], dict[str, Any]]:
    by_policy: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulations:
        by_policy[(str(row["Policy"]), json.dumps(row.get("policy_parameters", {}), sort_keys=True))].append(row)
    all_avail = [float(row.get("policy_availability") or 0.0) for row in simulations]
    all_stockout = [int(row.get("policy_stockout_days") or 0) for row in simulations]
    sensitivity_score = (max(all_avail, default=0.0) - min(all_avail, default=0.0)) + (
        max(all_stockout, default=0) - min(all_stockout, default=0)
    ) / max(1, days)
    policies = []
    for (policy, parameters), rows in sorted(by_policy.items()):
        policies.append({
            "Policy": policy,
            "policy_parameters": json.loads(parameters),
            "ROBUST_LT_COUNT": max(int(row.get("ROBUST_LT_COUNT") or 0) for row in rows),
            "lead_times": [{
                "LeadTimeScenario": row["LeadTimeScenario"],
                "availability": row.get("policy_availability"), "stockout_days": row.get("policy_stockout_days"),
                "average_inventory": row.get("policy_avg_inventory"), "replenishments": row.get("policy_replenishments"),
                "result_class": row.get("result_class"), "pareto_status": row.get("pareto_status"),
            } for row in sorted(rows, key=lambda row: int(row["LeadTimeScenario"]))],
        })
    return {"score": sensitivity_score, "policies": policies}, {"all_availability": all_avail, "all_stockout": all_stockout}


def _robustness_class(count: int) -> str:
    if count >= 5:
        return "ROBUST_HIGH"
    if count >= 3:
        return "ROBUST_MEDIUM"
    if count >= 1:
        return "ROBUST_LOW"
    return "NOT_ROBUST"


def _mean(rows: Iterable[Mapping[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return statistics.fmean(values) if values else None


def _metric_block(rows: list[Mapping[str, Any]], *, prefix: str = "") -> dict[str, Any]:
    return {
        f"{prefix}availability_mean": _mean(rows, "availability_rate"),
        f"{prefix}stockout_days_mean": _mean(rows, "stockout_days"),
        f"{prefix}average_inventory_mean_per_product": _mean(rows, "average_inventory"),
        f"{prefix}replenishments_mean": _mean(rows, "replenishment_count"),
        f"{prefix}inventory_days_mean_per_product": _mean(rows, "inventory_days"),
        "products": len(rows),
    }


def _rankings(product_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    def top(name: str, values: Iterable[dict[str, Any]], key: Any) -> list[dict[str, Any]]:
        return [{k: row.get(k) for k in ("ItemCode", "Branch", "PROBLEM_CLASS", "sensitivity_score", "sensitivity_class", "CURRENT", "BEST_CANDIDATE", "DECISION_STATUS")} for row in sorted(values, key=key)[:20]]
    return {
        "TOP_SERVICE_PROBLEM": top("service", (r for r in product_rows if r["PROBLEM_CLASS"] in {"SERVICE_PROBLEM", "BOTH"}), lambda r: (-int(r["CURRENT"].get("CURRENT_STOCKOUT_DAYS") or 0), r["ItemCode"])),
        "TOP_AVAILABILITY_IMPROVEMENT": top("availability", (r for r in product_rows if r["BEST_CANDIDATE"]), lambda r: (-float(r["BEST_CANDIDATE"].get("delta_availability") or 0.0), r["ItemCode"])),
        "TOP_STOCKOUT_REDUCTION": top("stockout", (r for r in product_rows if r["BEST_CANDIDATE"]), lambda r: (int(r["BEST_CANDIDATE"].get("delta_stockout_days") or 0), r["ItemCode"])),
        "TOP_INVENTORY_REDUCTION": top("inventory", (r for r in product_rows if r["BEST_CANDIDATE"]), lambda r: (float(r["BEST_CANDIDATE"].get("delta_avg_inventory") or 0.0), r["ItemCode"])),
        "TOP_BOTH_PROBLEM": top("both", (r for r in product_rows if r["PROBLEM_CLASS"] == "BOTH"), lambda r: (-int(r["CURRENT"].get("CURRENT_STOCKOUT_DAYS") or 0), r["ItemCode"])),
        "TOP_LT_SENSITIVE": top("lt", product_rows, lambda r: (-float(r.get("sensitivity_score") or 0.0), r["ItemCode"])),
        "TOP_KEEP_CURRENT": top("keep", (r for r in product_rows if r["DECISION_STATUS"] == "KEEP_CURRENT_CANDIDATE"), lambda r: r["ItemCode"]),
    }


def _select_cases(product_rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    categories = (
        lambda r: r["PROBLEM_CLASS"] == "SERVICE_PROBLEM",
        lambda r: r["PROBLEM_CLASS"] == "EXCESS_INVENTORY_PROBLEM",
        lambda r: r["PROBLEM_CLASS"] == "BOTH",
        lambda r: r["PROBLEM_CLASS"] == "NEITHER",
        lambda r: r["sensitivity_class"] == "LT_HIGHLY_SENSITIVE",
        lambda r: r["DECISION_STATUS"] == "KEEP_CURRENT_CANDIDATE",
    )
    for predicate in categories:
        for row in sorted((r for r in product_rows if predicate(r)), key=lambda r: r["ItemCode"]):
            if row["ItemCode"] not in seen:
                chosen.append(row)
                seen.add(row["ItemCode"])
                break
    for row in sorted(product_rows, key=lambda r: (-int(r["CURRENT"].get("CURRENT_STOCKOUT_DAYS") or 0), -float(r.get("sensitivity_score") or 0.0), r["ItemCode"])):
        if len(chosen) >= limit:
            break
        if row["ItemCode"] not in seen:
            chosen.append(row)
            seen.add(row["ItemCode"])
    return chosen[:limit]


def _runtime_checks(pair: tuple[str, str], rows: list[dict[str, Any]]) -> dict[str, str]:
    config = PolicyConfiguration("REORDER_POINT", {"service_level": 0.98, "review_days": 7})
    first = simulate_pair(pair[0], pair[1], rows, config, 3, trace=True)
    changed = [dict(row) for row in rows]
    pivot = len(changed) // 2
    for row in changed[pivot:]:
        row["OBSERVED_DEMAND"] = _number(row.get("OBSERVED_DEMAND")) * 11 + 1
    second = simulate_pair(pair[0], pair[1], changed, config, 3, trace=True)
    before = [(r["order_qty"], r["order_trigger"], r["inventory_position"]) for r in first["trace"] if r["date"] < rows[pivot]["Date"]]
    after = [(r["order_qty"], r["order_trigger"], r["inventory_position"]) for r in second["trace"] if r["date"] < rows[pivot]["Date"]]
    conservation = all(abs(r["closing_stock"] - (r["opening_stock"] + r["arrival"] - r["fulfilled_demand"])) < 1e-9 for r in first["trace"])
    sig1 = deterministic_signature(simulate_pair(pair[0], pair[1], rows, config, 3))
    sig2 = deterministic_signature(simulate_pair(pair[0], pair[1], rows, config, 3))
    return {"NO_LOOKAHEAD": "PASS" if before == after else "FAIL", "INVENTORY_CONSERVATION": "PASS" if conservation else "FAIL", "DETERMINISM": "PASS" if sig1 == sig2 else "FAIL"}


def _trace_cases(output: Path, cases: list[dict[str, Any]], rows_by_pair: dict[tuple[str, str], list[dict[str, Any]]]) -> int:
    values = []
    for index, case in enumerate(cases, 1):
        pair = (case["ItemCode"], case["Branch"])
        rows = rows_by_pair[pair]
        candidate = case.get("BEST_CANDIDATE")
        if candidate:
            policy = PolicyConfiguration(candidate["Policy"], candidate.get("policy_parameters") or {})
            result = simulate_pair(pair[0], pair[1], rows, policy, int(candidate["LeadTimeScenario"]), trace=True)
            trace = result.get("trace") or []
            trace_kind = "CANDIDATE"
        else:
            trace = [{"date": row["Date"], "stock_end": row["StockEndOfDay"], "observed_demand": row["OBSERVED_DEMAND"]} for row in rows]
            trace_kind = "CURRENT_OBSERVED"
        values.append({"case_id": f"B3-{index:02d}", "ItemCode": pair[0], "Branch": pair[1], "problem_class": case["PROBLEM_CLASS"], "decision_status": case["DECISION_STATUS"], "trace_kind": trace_kind, "policy": candidate, "daily_trace": trace})
    return _write_jsonl(output / "case_traces.jsonl", values)


def run(input_dir: Path = DEFAULT_INPUT, output: Path = DEFAULT_OUTPUT, count: int = 100, label: str = "B3") -> dict[str, Any]:
    if count not in SMOKE_COUNTS:
        raise ValueError(f"count must be one of {SMOKE_COUNTS}")
    output.mkdir(parents=True, exist_ok=True)
    for filename in ("sample_selection.json", "current_policy.jsonl", "policy_metrics.jsonl", "pareto_candidates.jsonl", "product_summary.jsonl", "lead_time_robustness.jsonl", "aggregate.json", "rankings.json", "case_traces.jsonl", "gate_result.json", "resource_metrics.jsonl"):
        (output / filename).unlink(missing_ok=True)
    started = time.monotonic()
    guard = ResourceGuard(output)
    guard.check("input_before", 0, 0, 1)
    stock, stock_rows = _read_stock_index(input_dir / "daily_item_branch_stock.jsonl.gz")
    event_path = input_dir / "replenishment_events_enriched.jsonl"
    if not event_path.exists():
        event_path = input_dir / "replenishment_events.jsonl.gz"
    events_all = _read_jsonl(event_path)
    pairs, selection = select_stratified_products(stock, events_all, count)
    _dump_json(output / "sample_selection.json", selection)
    selected = set(pairs)
    events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events_all:
        key = (str(event.get("ItemCode")), str(event.get("Branch")))
        if key in selected:
            events[key].append(event)
    episode_path = input_dir / "stockout_episodes.jsonl.gz"
    episodes_all = _read_jsonl(episode_path) if episode_path.exists() else []
    episodes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes_all:
        key = (str(episode.get("ItemCode")), str(episode.get("Branch")))
        if key in selected:
            episodes[key].append(episode)
    guard.check("input_loaded", stock_rows + len(events_all) + len(episodes_all), 0, 1)

    configurations = policy_configurations()
    if len(configurations) != EXPECTED_CONFIGURATIONS:
        raise RuntimeError("Gate 5C must reuse exactly 19 policy configurations")
    current_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    product_rows: list[dict[str, Any]] = []
    rows_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    runtime: dict[str, str] | None = None
    for index, pair in enumerate(pairs, 1):
        daily = normalise_daily_rows(_daily_rows(stock[pair]))
        rows_by_pair[pair] = daily
        pair_result = _run_pair_level_b(pair[0], pair[1], daily, events[pair], configurations)
        current = pair_result["current"]
        current_audit = audit_current_pair(pair[0], pair[1], daily, episodes[pair])
        current["POSSIBLE_CENSORED_DEMAND_DAYS"] = current_audit["possible_censored_demand_days"]
        current["censored_demand_analysis"] = "SENSITIVITY_ONLY_NOT_PRIMARY"
        simulations = pair_result["simulations"]
        classification, class_detail = _problem_class(current, simulations, len(daily))
        for row in simulations:
            row["robustness_class"] = _robustness_class(int(row.get("ROBUST_LT_COUNT") or 0))
        sensitivity, _ = _lead_time_summary(simulations, len(daily))
        product_rows.append({
            "ItemCode": pair[0], "Branch": pair[1], "PROBLEM_CLASS": classification,
            "problem_class_detail": class_detail, "CURRENT": current,
            "sensitivity_score": sensitivity["score"], "sensitivity_policies": sensitivity["policies"],
            "BEST_NON_DOMINATED_POLICIES": [_view(row) for row in simulations if row.get("pareto_status") == "PARETO_OPTIMAL"],
            "BEST_CANDIDATE": _view(_best(simulations, _improves)) if _best(simulations, _improves) else None,
            "DECISION_STATUS": "IMPROVEMENT_CANDIDATE" if _best(simulations, _improves) else "NO_CLEAR_IMPROVEMENT",
            "observed_fill_rate_secondary": current.get("fill_rate"),
        })
        current_rows.append(current)
        metric_rows.extend(simulations)
        if runtime is None:
            runtime = _runtime_checks(pair, daily)
        guard.check(f"pair_{index:03d}_{pair[1]}_{pair[0]}", len(daily) + len(events[pair]), len(simulations) + 1, 1)

    sensitivity_values = [float(row["sensitivity_score"]) for row in product_rows]
    sensitivity_q33, sensitivity_q67 = _quantile(sensitivity_values, 1 / 3), _quantile(sensitivity_values, 2 / 3)
    for row in product_rows:
        score = float(row["sensitivity_score"])
        row["sensitivity_class"] = "LT_INSENSITIVE" if score <= sensitivity_q33 else "LT_MODERATE" if score <= sensitivity_q67 else "LT_HIGHLY_SENSITIVE"
        candidate = row["BEST_CANDIDATE"]
        if candidate:
            candidate["robustness_class"] = _robustness_class(int(candidate.get("ROBUST_LT_COUNT") or 0))
        if row["PROBLEM_CLASS"] == "NEITHER" and not candidate:
            row["DECISION_STATUS"] = "KEEP_CURRENT_CANDIDATE"
        # Keep only the first five frontier rows in the compact product artifact.
        row["BEST_NON_DOMINATED_POLICIES"] = row["BEST_NON_DOMINATED_POLICIES"][:5]
    for row in metric_rows:
        if row.get("robustness_class") is None:
            row["robustness_class"] = _robustness_class(int(row.get("ROBUST_LT_COUNT") or 0))

    _write_jsonl(output / "current_policy.jsonl", current_rows)
    _write_jsonl(output / "policy_metrics.jsonl", metric_rows)
    _write_jsonl(output / "pareto_candidates.jsonl", (_view(row) for row in metric_rows if row.get("pareto_status") == "PARETO_OPTIMAL"))
    _write_jsonl(output / "product_summary.jsonl", product_rows)
    lead_rows = []
    for product in product_rows:
        for policy in product["sensitivity_policies"]:
            lead_rows.append({"ItemCode": product["ItemCode"], "Branch": product["Branch"], **policy})
    _write_jsonl(output / "lead_time_robustness.jsonl", lead_rows)

    current_by_item = [row["CURRENT"] for row in product_rows]
    candidate_by_item = [row["BEST_CANDIDATE"] for row in product_rows if row["BEST_CANDIDATE"]]
    best_robustness = Counter(_robustness_class(int(row.get("ROBUST_LT_COUNT") or 0)) for row in candidate_by_item)
    family = Counter(str(row["Policy"]) for row in candidate_by_item)
    policy_families = ("MIN_MAX", "REORDER_POINT", "DAYS_OF_SUPPLY", "PERIODIC_REVIEW", "DYNAMIC_TARGET", "HYBRID")
    problem_counts = Counter(row["PROBLEM_CLASS"] for row in product_rows)
    sensitivity_counts = Counter(row["sensitivity_class"] for row in product_rows)
    aggregate = {
        "product_count": len(product_rows),
        "problem_distribution": {name: {"count": problem_counts.get(name, 0), "percentage": round(100 * problem_counts.get(name, 0) / len(product_rows), 2)} for name in ("SERVICE_PROBLEM", "EXCESS_INVENTORY_PROBLEM", "BOTH", "NEITHER", "INSUFFICIENT_HISTORY", "INCONCLUSIVE")},
        "policy_distribution_best_candidates": {name: family.get(name, 0) for name in policy_families},
        "robustness_distribution_best_candidates": {name: best_robustness.get(name, 0) for name in ("ROBUST_HIGH", "ROBUST_MEDIUM", "ROBUST_LOW", "NOT_ROBUST")},
        "lead_time_sensitivity_distribution": {name: sensitivity_counts.get(name, 0) for name in ("LT_INSENSITIVE", "LT_MODERATE", "LT_HIGHLY_SENSITIVE")},
        "current": _metric_block(current_by_item),
        "best_non_dominated_candidates": _metric_block(candidate_by_item),
        "candidate_products": len(candidate_by_item),
        "no_clear_improvement": sum(row["DECISION_STATUS"] == "NO_CLEAR_IMPROVEMENT" for row in product_rows),
        "no_policy_improves": sum(row["DECISION_STATUS"] == "NO_CLEAR_IMPROVEMENT" for row in product_rows),
        "keep_current_candidates": sum(row["DECISION_STATUS"] == "KEEP_CURRENT_CANDIDATE" for row in product_rows),
        "units": "inventory and replenishment quantities are per-product means; heterogeneous UoM are never summed",
    }
    _dump_json(output / "aggregate.json", aggregate)
    rankings = _rankings(product_rows)
    _dump_json(output / "rankings.json", rankings)
    cases = _select_cases(product_rows, 20)
    trace_count = _trace_cases(output, cases, rows_by_pair)

    control_product = next((row for row in product_rows if row["ItemCode"] == "L02467"), None)
    control_candidate = None
    if control_product:
        control_candidate = next((row for row in metric_rows if row["ItemCode"] == "L02467" and row["Policy"] == "DAYS_OF_SUPPLY" and row.get("policy_parameters") == {"target_dos": 7, "trigger_dos": 3} and row["LeadTimeScenario"] == 0), None)
    control = {
        "item": "L02467", "reproduced": bool(control_product and control_candidate),
        "current_availability": control_product["CURRENT"].get("CURRENT_AVAILABILITY") if control_product else None,
        "current_stockout_days": control_product["CURRENT"].get("CURRENT_STOCKOUT_DAYS") if control_product else None,
        "candidate_availability": control_candidate.get("policy_availability") if control_candidate else None,
        "candidate_stockout_days": control_candidate.get("policy_stockout_days") if control_candidate else None,
        "candidate_delta_inventory": control_candidate.get("delta_avg_inventory") if control_candidate else None,
        "expected": {"current_availability": 0.0712, "candidate_availability": 0.6795, "current_stockout_days": 339, "candidate_stockout_days": 117},
        "tolerance": {"availability": 0.002, "stockout_days": 1},
    }
    control["reproduced"] = bool(control_product and control_candidate and abs(control["current_availability"] - 0.0712328767) <= 0.002 and abs(control["candidate_availability"] - 0.6794520548) <= 0.002 and control["current_stockout_days"] == 339 and control["candidate_stockout_days"] == 117)
    resource = guard.summary()
    previous_smokes = {}
    for previous in (25, 50):
        previous_path = output.parent / f"v1_B{1 if previous == 25 else 2}_{previous}"
        gate_path = previous_path / "gate_result.json"
        previous_smokes[str(previous)] = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {"verdict": "NOT_RUN"}
    result = {
        "gate": "TELCHI_REPLENISHMENT_LEVEL_B_100_L_PRODUCTS_V1",
        "verdict": "TELCHI_REPLENISHMENT_LEVEL_B_100_L_PRODUCTS_V1_PASS" if resource["resource_abort_count"] == 0 and all(value == "PASS" for value in (runtime or {}).values()) and control["reproduced"] else "DEGRADED",
        "level": label, "authorization": "EXECUTE_LEVEL_B",
        "context": {"ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION", "PRIMARY_UNIVERSE": "ItemCode LIKE 'L%'", "branch": "2A", "TRANSIT": "TRANSIT_EXCLUDED", "SAP_WRITE_COUNT": 0, "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED"},
        "universe": {"products": len(product_rows), "pairs": len(pairs), "days": EXPECTED_DAYS, "non_l_primary_rows": 0, "date_start": min(min(stock[pair]) for pair in pairs), "date_end": max(max(stock[pair]) for pair in pairs)},
        "policy_grid": {"configurations": len(configurations), "lead_time_scenarios": list(LEAD_TIME_SCENARIOS), "simulation_rows": len(metric_rows), "expected_simulation_rows": len(pairs) * EXPECTED_CONFIGURATIONS * len(LEAD_TIME_SCENARIOS), "pareto_dimensions": ["Availability_UP", "AverageInventory_DOWN", "ReplenishmentCount_DOWN"], "fill_rate_role": "SECONDARY_CONTROL_ONLY"},
        "problem_distribution": aggregate["problem_distribution"], "policy_distribution": aggregate["policy_distribution_best_candidates"], "robustness_distribution": aggregate["robustness_distribution_best_candidates"], "lead_time_sensitivity_distribution": aggregate["lead_time_sensitivity_distribution"],
        "impact": aggregate, "rankings_artifact": "rankings.json", "case_count": trace_count, "control_L02467": control,
        "smoke_predecessors": previous_smokes,
        "lead_time_classification": {"method": "empirical tertiles of max policy availability spread plus stockout spread normalized by 365 days", "q33": sensitivity_q33, "q67": sensitivity_q67, "classes": ["LT_INSENSITIVE", "LT_MODERATE", "LT_HIGHLY_SENSITIVE"]},
        "censored_demand": {"primary": "OBSERVED_DEMAND_ONLY", "use": "SENSITIVITY_ONLY", "stockout_is_confirmed_lack_of_stock_not_confirmed_lost_sales": True},
        "engine_validation": {**(runtime or {"NO_LOOKAHEAD": "DEGRADED", "INVENTORY_CONSERVATION": "DEGRADED", "DETERMINISM": "DEGRADED"}), "RESOURCE_SAFETY": "PASS" if resource["resource_abort_count"] == 0 else "FAIL", "SAP_WRITE_COUNT": 0},
        "resource_safety": {**resource, "elapsed_seconds": round(time.monotonic() - started, 4), "rows_read": stock_rows, "rows_simulated": len(metric_rows) * EXPECTED_DAYS},
        "decision": "NO_PRODUCTION_RECOMMENDATION", "next_gate": "GATE_PHYSICAL_LEAD_TIME_LOGISTICS_PROCESS_INVESTIGATION",
        "artifacts": ["sample_selection.json", "current_policy.jsonl", "policy_metrics.jsonl", "pareto_candidates.jsonl", "product_summary.jsonl", "lead_time_robustness.jsonl", "aggregate.json", "rankings.json", "case_traces.jsonl", "resource_metrics.jsonl", "gate_result.json"],
    }
    # The next gate is deliberately decided from robustness, not from count alone.
    if len(product_rows) == 100 and sum(best_robustness.get(name, 0) for name in ("ROBUST_HIGH", "ROBUST_MEDIUM")) >= max(1, len(candidate_by_item) // 2):
        result["next_gate"] = "LEVEL_C_ALL_ACTIVE_L_2A"
    _dump_json(output / "gate_result.json", result)
    return result


def _abort(output: Path, error: str) -> dict[str, Any]:
    result = {"gate": "TELCHI_REPLENISHMENT_LEVEL_B_100_L_PRODUCTS_V1", "verdict": "DEGRADED", "result": "RESOURCE_GUARD_ABORT", "RESOURCE_GUARD": "ENABLED", "MAX_WORKERS": 1, "SAP_WRITE_COUNT": 0, "error": error, "snapshot": resource_snapshot()}
    _dump_json(output / "gate_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI Level B stratified availability backtest")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=int, choices=SMOKE_COUNTS, default=100)
    parser.add_argument("--label", choices=("B1", "B2", "B3"), default="B3")
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.output, args.count, args.label)
    except ResourceGuardAbort as exc:
        result = _abort(args.output, str(exc))
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "level": result.get("level"), "universe": result.get("universe"), "problem_distribution": result.get("problem_distribution"), "robustness_distribution": result.get("robustness_distribution"), "control_L02467": result.get("control_L02467"), "resource_safety": result.get("resource_safety"), "output": str(args.output)}, ensure_ascii=False, indent=2, default=str))
    return 3 if result.get("result") == "RESOURCE_GUARD_ABORT" else 0


if __name__ == "__main__":
    sys.exit(main())
