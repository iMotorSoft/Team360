from datetime import date, timedelta

from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    LEAD_TIME_SCENARIOS,
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
    MAX_WORKERS,
    MIN_MEM_AVAILABLE_BYTES,
)


def _rows(days=100, demand=10, opening=100):
    start = date(2025, 1, 1)
    return [
        {
            "Date": start + timedelta(days=i),
            "StockEndOfDay": opening - demand * (i + 1),
            "NET_MOVEMENT_QTY": -demand,
            "OBSERVED_DEMAND": demand,
        }
        for i in range(days)
    ]


def test_inventory_conservation_and_lead_time_scheduling():
    result = simulate_pair(
        "L1", "2A", _rows(),
        PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 30, "trigger_dos": 7}),
        3,
        trace=True,
    )
    assert result["fill_rate"] >= 0
    assert result["unfulfilled_observed_demand"] >= 0
    trace = result["trace"]
    orders = {row["date"]: row for row in trace if row["order_qty"] > 0}
    assert orders
    for row in trace:
        assert abs(row["closing_stock"] - (row["opening_stock"] + row["arrival"] - row["fulfilled_demand"])) < 1e-9
    first_order = next(row for row in trace if row["order_qty"] > 0)
    assert first_order["scheduled_arrival_date"] == first_order["date"] + timedelta(days=3)
    arrival = next(row for row in trace if row["date"] == first_order["scheduled_arrival_date"])
    assert arrival["arrival"] >= first_order["order_qty"]
    assert all(row["closing_stock"] >= 0 for row in trace)


def test_no_lookahead_future_mutation_does_not_change_prior_decisions():
    original = _rows(days=100, demand=4)
    changed = [dict(row) for row in original]
    for row in changed[70:]:
        row["OBSERVED_DEMAND"] = 400
    a = simulate_pair("L1", "2A", original, PolicyConfiguration("REORDER_POINT", {"service_level": .98}), 3, trace=True)
    b = simulate_pair("L1", "2A", changed, PolicyConfiguration("REORDER_POINT", {"service_level": .98}), 3, trace=True)
    prior = original[70]["Date"]
    a_prior = [row for row in a["trace"] if row["date"] < prior]
    b_prior = [row for row in b["trace"] if row["date"] < prior]
    assert [(row["order_qty"], row["order_trigger"], row["inventory_position"]) for row in a_prior] == [
        (row["order_qty"], row["order_trigger"], row["inventory_position"]) for row in b_prior
    ]


def test_deterministic_simulation():
    config = PolicyConfiguration("DYNAMIC_TARGET", {"target_dos": 30, "service_level": .98})
    a = simulate_pair("L1", "2A", _rows(demand=7), config, 5)
    b = simulate_pair("L1", "2A", _rows(demand=7), config, 5)
    assert deterministic_signature(a) == deterministic_signature(b)


def test_zero_demand_does_not_order_forever():
    result = simulate_pair("L0", "2A", _rows(demand=0), PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 30}), 3)
    assert result["replenishment_count"] == 0
    assert result["observed_demand"] == 0


def test_constant_demand_has_explicit_policy_orders():
    result = simulate_pair("L1", "2A", _rows(demand=10), PolicyConfiguration("MIN_MAX", {"min_days": 7, "max_days": 30}), 3)
    assert result["replenishment_count"] > 0
    assert result["fill_rate"] <= 1


def test_intermitent_demand_is_not_imputed():
    rows = _rows(demand=0)
    for i in (35, 50, 90):
        rows[i]["OBSERVED_DEMAND"] = 5
    result = simulate_pair("LI", "2A", rows, PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 14}), 2)
    assert result["observed_demand"] == 15
    assert result["unfulfilled_observed_demand"] >= 0


def test_future_spike_is_not_anticipated():
    rows = _rows(days=100, demand=2)
    spike = [dict(row) for row in rows]
    spike[80]["OBSERVED_DEMAND"] = 1000
    config = PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 14, "trigger_dos": 7})
    normal = simulate_pair("L1", "2A", rows, config, 1, trace=True)
    changed = simulate_pair("L1", "2A", spike, config, 1, trace=True)
    assert [r["order_qty"] for r in normal["trace"][:80]] == [r["order_qty"] for r in changed["trace"][:80]]


def test_policy_trigger_and_current_comparison():
    rows = _rows(demand=5)
    current = current_policy_metrics("L1", "2A", rows, [])
    result = simulate_pair("L1", "2A", rows, PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 30}), 2)
    compared = compare_to_current(current, result)
    assert compared["current_fill_rate"] == 1.0
    assert "delta_fill_rate" in compared
    assert compared["Policy"] == "DAYS_OF_SUPPLY"


def test_pareto_and_robustness_classification():
    rows = [
        {"ItemCode": "L1", "Branch": "2A", "Policy": "A", "LeadTimeScenario": 0, "fill_rate": 1.0, "availability_rate": .95, "average_inventory": 10, "replenishment_count": 2, "delta_availability": .05, "delta_stockout_days": -1, "delta_avg_inventory": -1},
        {"ItemCode": "L1", "Branch": "2A", "Policy": "B", "LeadTimeScenario": 0, "fill_rate": .9, "availability_rate": .90, "average_inventory": 20, "replenishment_count": 3, "delta_availability": .01, "delta_stockout_days": -1, "delta_avg_inventory": 1},
    ]
    pareto = pareto_frontier(rows)
    assert pareto[0]["pareto_status"] == "PARETO_OPTIMAL"
    assert pareto[1]["pareto_status"] == "DOMINATED"
    robust = classify_robustness(pareto, minimum_scenarios=1)
    assert robust[0]["robust_policy"] is True


def test_policy_grid_is_bounded_and_lead_time_scenarios_are_explicit():
    configs = policy_configurations()
    assert len(configs) == 19
    assert LEAD_TIME_SCENARIOS == (0, 1, 2, 3, 5, 7)
    assert MAX_WORKERS == 1
    assert MIN_MEM_AVAILABLE_BYTES == 2 * 1024**3


def test_run_pair_returns_current_and_trace_without_future_state():
    result = run_pair(
        "L1", "2A", _rows(), [],
        configurations=[PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 14})],
        lead_times=[0, 3], trace_policy="DAYS_OF_SUPPLY",
    )
    assert result["current"]["Policy"] == "CURRENT_POLICY"
    assert len(result["simulations"]) == 2
    assert result["trace"]
