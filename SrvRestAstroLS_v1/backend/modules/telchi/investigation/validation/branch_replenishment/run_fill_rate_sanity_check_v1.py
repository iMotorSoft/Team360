"""Run TELCHI Gate 5A over the already reconciled Level A evidence.

This is deliberately not Level B.  It audits the CURRENT fill-rate ceiling,
proves metric comparability, and runs only LOW/BASE/HIGH retrospective
sensitivity against the same ten L products.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    LEAD_TIME_SCENARIOS,
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
from modules.telchi.investigation.validation.branch_replenishment.fill_rate_sanity_check import (
    SENSITIVITY_LEVELS,
    audit_comparability,
    audit_current_pair,
    build_sensitivity_rows,
    normalise_daily_rows,
    stable_daily_signature,
)
from modules.telchi.investigation.validation.branch_replenishment.run_backtest_engine_v1 import (
    DEFAULT_INPUT,
    _daily_rows,
    _read_stock_index,
    _select_pairs,
)

DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_fill_rate_sanity" / "v1_level_A"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sensitivity_aggregate(
    level: str,
    metrics: list[dict[str, Any]],
    current_sensitivity: Mapping[str, float],
) -> list[dict[str, Any]]:
    current_demand = float(current_sensitivity.get("demand", 0.0))
    current_fulfilled = float(current_sensitivity.get("fulfilled", 0.0))
    current_fill = current_fulfilled / current_demand if current_demand else None
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in metrics:
        grouped[(str(row["Policy"]), int(row["LeadTimeScenario"]))].append(row)
    output = []
    for (policy, lead_time), rows in sorted(grouped.items()):
        demand = sum(float(row.get("observed_demand") or 0.0) for row in rows)
        fulfilled = sum(float(row.get("fulfilled_observed_demand") or 0.0) for row in rows)
        output.append({
            "sensitivity": level,
            "Policy": policy,
            "LeadTimeScenario": lead_time,
            "product_pairs": len({(str(row.get('ItemCode')), str(row.get('Branch'))) for row in rows}),
            "simulation_rows": len(rows),
            "fill_rate_mean_by_pair": _mean([float(row["fill_rate"]) for row in rows if row.get("fill_rate") is not None]),
            "fill_rate_weighted": fulfilled / demand if demand else None,
            "current_fill_rate_weighted": current_fill,
            "delta_fill_rate_weighted": (fulfilled / demand - current_fill) if demand and current_fill is not None else None,
            "stockout_days_mean_by_pair": _mean([float(row.get("stockout_days") or 0.0) for row in rows]),
            "stockout_episodes_mean_by_pair": _mean([float(row.get("stockout_episodes") or 0.0) for row in rows]),
            "stockout_duration_mean_by_pair": _mean([float(row.get("stockout_duration_mean") or 0.0) for row in rows]),
            "availability_days_mean_by_pair": _mean([float(row.get("availability_days") or 0.0) for row in rows]),
            "availability_rate_mean_by_pair": _mean([float(row.get("availability_rate") or 0.0) for row in rows]),
            "average_inventory_mean_by_pair": _mean([float(row.get("average_inventory") or 0.0) for row in rows]),
            "replenishment_count_mean_by_pair": _mean([float(row.get("replenishment_count") or 0.0) for row in rows]),
            "service_basis": "SENSITIVITY_DEMAND_NOT_SALES_FACT",
        })
    return output


def run(input_dir: Path = DEFAULT_INPUT, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    for filename in (
        "current_fill_rate_audit.jsonl", "comparability.jsonl", "observed_policy_metrics.jsonl",
        "sensitivity_rows.jsonl", "sensitivity_policy_metrics.jsonl", "sensitivity_comparison.jsonl",
        "gate_result.json", "resource_metrics.jsonl",
    ):
        (output / filename).unlink(missing_ok=True)
    started = time.monotonic()
    guard = ResourceGuard(output)
    guard.check("input_before", 0, 0, 1)
    stock, stock_row_count = _read_stock_index(input_dir / "daily_item_branch_stock.jsonl.gz")
    guard.check("input_loaded", stock_row_count, 0, 1)
    pairs = _select_pairs(stock, ("2A",), 10)
    if len(pairs) != 10:
        raise RuntimeError(f"Gate 5A requires exactly 10 Level A L pairs, got {len(pairs)}")
    event_rows = _read_jsonl(input_dir / "replenishment_events.jsonl.gz")
    episode_rows = _read_jsonl(input_dir / "stockout_episodes.jsonl.gz")
    events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    episodes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    selected = set(pairs)
    for row in event_rows:
        key = (str(row["ItemCode"]), str(row["Branch"]))
        if key in selected:
            events[key].append(row)
    for row in episode_rows:
        key = (str(row["ItemCode"]), str(row["Branch"]))
        if key in selected:
            episodes[key].append(row)

    current_audits: list[dict[str, Any]] = []
    comparability: list[dict[str, Any]] = []
    observed_metrics: list[dict[str, Any]] = []
    sensitivity_metrics: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    sensitivity_meta: dict[str, dict[str, Any]] = {
        level: {"level": level, "imputed_days": 0, "imputed_demand": 0.0}
        for level in SENSITIVITY_LEVELS
    }
    sensitivity_current: dict[str, dict[str, float]] = {
        level: {"demand": 0.0, "fulfilled": 0.0} for level in SENSITIVITY_LEVELS
    }
    configurations = policy_configurations()
    signatures: dict[tuple[str, str], str] = {}
    for pair_index, pair in enumerate(pairs, 1):
        rows = _daily_rows(stock[pair])
        normalised = normalise_daily_rows(rows)
        audit = audit_current_pair(pair[0], pair[1], normalised, episodes.get(pair, []))
        current = current_policy_metrics(pair[0], pair[1], normalised, events.get(pair, []))
        observed = run_pair(pair[0], pair[1], normalised, events.get(pair, []), configurations, LEAD_TIME_SCENARIOS)
        current_audits.append({**audit, "baseline_engine": current})
        signatures[pair] = stable_daily_signature(normalised)
        observed_metrics.extend(observed["simulations"])
        comparability.append({
            "ItemCode": pair[0], "Branch": pair[1],
            "daily_signature": signatures[pair],
            **audit_comparability(normalised, current, observed["simulations"][0]),
        })
        for level in SENSITIVITY_LEVELS:
            adjusted, meta = build_sensitivity_rows(normalised, episodes.get(pair, []), level)
            sensitivity_meta[level]["imputed_days"] += int(meta["imputed_days"])
            sensitivity_meta[level]["imputed_demand"] += float(meta["imputed_demand"])
            sensitivity_meta[level]["method"] = meta["method"]
            sensitivity_meta[level]["is_sales_fact"] = False
            sensitivity_meta[level]["is_lost_sales_claim"] = False
            sensitivity_meta[level]["eligibility_uses_post_episode_evidence"] = True
            sensitivity_meta[level]["amount_uses_future_demand"] = False
            sensitivity_current[level]["demand"] += sum(float(row["OBSERVED_DEMAND"]) for row in adjusted)
            sensitivity_current[level]["fulfilled"] += sum(
                float(row["OBSERVED_DEMAND"]) - float(row["SENSITIVITY_IMPUTED_DEMAND"]) for row in adjusted
            )
            sensitivity_rows.extend({
                "ItemCode": pair[0], "Branch": pair[1], "Date": row["Date"],
                "level": level, "observed_demand": row["OBSERVED_DEMAND"],
                "imputed_demand": row["SENSITIVITY_IMPUTED_DEMAND"],
                "eligible": row["SENSITIVITY_ELIGIBLE"],
                "estimate_base": row["SENSITIVITY_ESTIMATE_BASE"],
                "estimate_high": row["SENSITIVITY_ESTIMATE_HIGH"],
            } for row in adjusted)
            sensitivity_result = run_pair(pair[0], pair[1], adjusted, events.get(pair, []), configurations, LEAD_TIME_SCENARIOS)
            sensitivity_metrics.extend({**row, "sensitivity": level} for row in sensitivity_result["simulations"])
        guard.check(
            f"pair_{pair_index:02d}_{pair[1]}_{pair[0]}",
            len(normalised) + len(events.get(pair, [])) + len(episodes.get(pair, [])),
            len(observed["simulations"]) + 1,
            1,
        )

    current_path = output / "current_fill_rate_audit.jsonl"
    _write_jsonl(current_path, current_audits)
    _write_jsonl(output / "comparability.jsonl", comparability)
    _write_jsonl(output / "observed_policy_metrics.jsonl", observed_metrics)
    _write_jsonl(output / "sensitivity_rows.jsonl", sensitivity_rows)
    _write_jsonl(output / "sensitivity_policy_metrics.jsonl", sensitivity_metrics)
    sensitivity_comparison = []
    for level in SENSITIVITY_LEVELS:
        sensitivity_comparison.extend(_sensitivity_aggregate(
            level, [row for row in sensitivity_metrics if row["sensitivity"] == level], sensitivity_current[level]
        ))
    _write_jsonl(output / "sensitivity_comparison.jsonl", sensitivity_comparison)
    resource = guard.summary()
    affected = [row for row in current_audits if row["observed_demand_ceiling_risk"]]
    evidence_affected = [row for row in current_audits if row["observed_demand_ceiling_risk_with_evidence"]]
    all_comparable = all(row["pass"] for row in comparability)
    result = {
        "gate": "TELCHI_REPLENISHMENT_BACKTEST_GATE_5A_FILL_RATE_CENSORED_DEMAND_SANITY_CHECK",
        "verdict": "FILL_RATE_CEILING_EFFECT_DETECTED" if all_comparable and evidence_affected else "FILL_RATE_METRIC_VALID" if all_comparable else "DEGRADED",
        "context": {
            "ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION",
            "SOURCES": ["SAP_HANA", "DATA_LAKE"], "READ_ONLY": True, "SAP_WRITE_COUNT": 0,
            "PRIMARY_UNIVERSE": "ItemCode LIKE 'L%'", "NON_L_UNIVERSE": "EXCLUDED_FROM_PRIMARY_ANALYSIS",
            "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED",
        },
        "level": "A",
        "level_b_executed": False,
        "universe": {
            "branches": ["2A"], "combinations": len(pairs), "ItemCodes": sorted(item for item, _ in pairs),
            "date_start": min(min(stock[pair]) for pair in pairs), "date_end": max(max(stock[pair]) for pair in pairs),
            "daily_rows": sum(len(stock[pair]) for pair in pairs), "non_l_pairs_in_selected_analysis": 0,
        },
        "audit": {
            "products_with_stockout": sum(row["stockout_days"] > 0 for row in current_audits),
            "products_with_near_100_fill_and_stockout": len(affected),
            "products_with_observed_demand_ceiling_risk": len(affected),
            "products_with_possible_censored_demand_evidence": len(evidence_affected),
            "product_rows": "current_fill_rate_audit.jsonl",
            "service_basis": "OBSERVED_DEMAND_ONLY",
        },
        "comparability": {
            "status": "PASS" if all_comparable else "DEGRADED",
            "pairs_checked": len(comparability), "pairs_passed": sum(row["pass"] for row in comparability),
            "artifact": "comparability.jsonl",
            "contract": "same period + same daily observed demand + same initial stock reconstruction + same opening/arrivals/policy/demand/closing convention",
        },
        "policy_runs": {
            "configurations": len(configurations), "lead_time_scenarios": list(LEAD_TIME_SCENARIOS),
            "observed_simulations": len(observed_metrics), "sensitivity_simulations": len(sensitivity_metrics),
        },
        "sensitivity": {
            "levels": list(SENSITIVITY_LEVELS), "artifact": "sensitivity_comparison.jsonl",
            "metadata": list(sensitivity_meta.values()),
            "not_sales_fact": True, "not_lost_sales_confirmation": True,
            "policy_metrics": "sensitivity_policy_metrics.jsonl",
        },
        "materiality": {
            "current_observed_fill_rate_mean": _mean([float(row["current_fill_rate"]) for row in current_audits if row["current_fill_rate"] is not None]),
            "current_observed_stockout_days_mean": _mean([float(row["stockout_days"]) for row in current_audits]),
            "current_availability_rate_mean": _mean([float(row["availability_rate"]) for row in current_audits]),
            "current_average_inventory_mean": _mean([float(row["average_inventory"]) for row in current_audits]),
            "stockout_sales_observed_total": sum(float(row["sales_during_stockout_days"]) for row in current_audits),
            "possible_censored_days_total": sum(int(row["possible_censored_demand_days"]) for row in current_audits),
            "sensitivity_current_fill_rate": {
                level: (values["fulfilled"] / values["demand"] if values["demand"] else None)
                for level, values in sensitivity_current.items()
            },
            "sensitivity_current_demand": {level: values["demand"] for level, values in sensitivity_current.items()},
            "sensitivity_comparison_rows": len(sensitivity_comparison),
        },
        "decision": "DO_NOT_EXECUTE_LEVEL_B_100_PRODUCTS_UNTIL_GATE_5A_REVIEWED",
        "limitations": [
            "OBSERVED_DEMAND_IS_CENSORED_WHEN_STOCKOUT_SUPPRESSES_SALES",
            "POSSIBLE_CENSORED_DEMAND_IS_NOT_CONFIRMED_LOST_SALES",
            "SENSITIVITY_ELIGIBILITY_USES_POST_EPISODE_EVIDENCE_RETROSPECTIVELY",
            "SENSITIVITY_IMPUTATION_AMOUNT_USES_PRIOR_HISTORY_ONLY",
            "INTRADAY_SEQUENCE_UNKNOWN",
            "PHYSICAL_LEAD_TIME_NOT_OBSERVABLE",
        ],
        "resource_safety": {**resource, "elapsed_seconds": round(time.monotonic() - started, 4)},
        "artifacts": [
            "current_fill_rate_audit.jsonl", "comparability.jsonl", "observed_policy_metrics.jsonl",
            "sensitivity_rows.jsonl", "sensitivity_policy_metrics.jsonl", "sensitivity_comparison.jsonl",
            "resource_metrics.jsonl", "gate_result.json",
        ],
    }
    _dump_json(output / "gate_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI Gate 5A fill-rate sanity check")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.output)
    except ResourceGuardAbort as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        _dump_json(args.output / "gate_result.json", {
            "gate": "TELCHI_REPLENISHMENT_BACKTEST_GATE_5A_FILL_RATE_CENSORED_DEMAND_SANITY_CHECK",
            "verdict": "DEGRADED", "result": "RESOURCE_GUARD_ABORT", "MAX_WORKERS": 1,
            "RESOURCE_GUARD": "ENABLED", "SAP_WRITE_COUNT": 0, "error": str(exc),
            "snapshot": resource_snapshot(),
        })
        return 3
    print(json.dumps({
        "gate": result["gate"], "verdict": result["verdict"], "audit": result["audit"],
        "comparability": result["comparability"], "materiality": result["materiality"],
        "decision": result["decision"], "output": str(args.output),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
