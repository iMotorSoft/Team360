from datetime import date, timedelta

from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    PolicyConfiguration,
    compare_to_current,
    current_policy_metrics,
    pareto_frontier,
    run_pair,
    simulate_pair,
)


def _rows(days=80, demand=2, opening=20):
    start = date(2025, 1, 1)
    return [
        {
            "Date": start + timedelta(days=i),
            "StockEndOfDay": max(0, opening - demand * (i + 1)),
            "NET_MOVEMENT_QTY": -demand,
            "OBSERVED_DEMAND": demand,
        }
        for i in range(days)
    ]


def test_comparison_uses_availability_not_observed_fill_rate():
    rows = _rows()
    current = current_policy_metrics("L1", "2A", rows)
    simulation = simulate_pair(
        "L1", "2A", rows,
        PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 30}), 3,
    )
    compared = compare_to_current(current, simulation)
    assert compared["current_availability"] == current["availability_rate"]
    assert compared["policy_availability"] == simulation["availability_rate"]
    assert compared["delta_availability"] != compared["delta_fill_rate"]
    assert compared["result_class"] in {
        "CLEAR_WIN", "AVAILABILITY_WIN_WITH_INVENTORY_COST",
        "INVENTORY_WIN_WITH_AVAILABILITY_COST", "LOGISTICS_COST", "DOMINATED", "INCONCLUSIVE",
    }


def test_pareto_frontier_dimensions_are_availability_inventory_replenishments():
    rows = [
        {"Policy": "A", "LeadTimeScenario": 0, "availability_rate": .90, "average_inventory": 10, "replenishment_count": 2},
        {"Policy": "B", "LeadTimeScenario": 0, "availability_rate": .95, "average_inventory": 12, "replenishment_count": 2},
        {"Policy": "C", "LeadTimeScenario": 0, "availability_rate": .90, "average_inventory": 10, "replenishment_count": 3},
    ]
    result = pareto_frontier(rows)
    assert [row["pareto_status"] for row in result] == ["PARETO_OPTIMAL", "PARETO_OPTIMAL", "DOMINATED"]


def test_primary_result_classes_cover_service_and_inventory_tradeoffs():
    current = {
        "fill_rate": 1.0, "availability_rate": .90, "stockout_days": 10,
        "historical_stockout_days_raw": 10, "average_inventory": 100,
        "replenishment_count": 2,
    }
    service = {
        "Policy": "P", "fill_rate": .7, "availability_rate": .95,
        "stockout_days": 5, "average_inventory": 100, "replenishment_count": 2,
    }
    inventory = {
        "Policy": "P", "fill_rate": .7, "availability_rate": .80,
        "stockout_days": 20, "average_inventory": 50, "replenishment_count": 2,
    }
    assert compare_to_current(current, service)["result_class"] == "CLEAR_WIN"
    assert compare_to_current(current, inventory)["result_class"] == "INVENTORY_WIN_WITH_AVAILABILITY_COST"


def test_gate_pair_exports_robust_lt_count_and_secondary_fill():
    result = run_pair(
        "L1", "2A", _rows(), [],
        configurations=[PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 14})],
        lead_times=[0, 3, 7],
    )
    assert len(result["simulations"]) == 3
    for row in result["simulations"]:
        assert "ROBUST_LT_COUNT" in row
        assert "observed_fill_rate_secondary" in row
        assert "delta_availability" in row
