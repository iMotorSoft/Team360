from datetime import date, timedelta

import pytest

from modules.telchi.investigation.validation.branch_replenishment.run_level_b_v1 import (
    MIN_HISTORY_DAYS,
    _problem_class,
    _robustness_class,
    select_stratified_products,
)


def _stock(item_count=25, days=MIN_HISTORY_DAYS):
    start = date(2025, 1, 1)
    result = {}
    for item_index in range(item_count):
        item = f"L{item_index:05d}"
        result[(item, "2A")] = {
            start + timedelta(days=day): (
                float(100 + item_index),
                float((item_index % 5) if day % (item_index % 5 + 1) == 0 else 0),
                1.0,
            )
            for day in range(days)
        }
    return result


def test_selector_is_l_only_deterministic_and_includes_control_when_available():
    stock = _stock()
    stock[("L02467", "2A")] = stock.pop(("L00000", "2A"))
    first, first_meta = select_stratified_products(stock, [], 25)
    second, second_meta = select_stratified_products(stock, [], 25)
    assert first == second
    assert first_meta["selected_item_codes"] == second_meta["selected_item_codes"]
    assert ("L02467", "2A") in first
    assert len(first) == 25
    assert all(item.startswith("L") and branch == "2A" for item, branch in first)
    assert first_meta["method"] == "DETERMINISTIC_STRATIFIED_ROUND_ROBIN"


def test_selector_rejects_non_level_b_counts():
    with pytest.raises(ValueError):
        select_stratified_products(_stock(), [], 10)


def test_problem_class_has_explicit_service_and_excess_definitions():
    current = {"CURRENT_STOCKOUT_DAYS": 10}
    excess = [{"pareto_status": "PARETO_OPTIMAL", "delta_availability": 0, "delta_stockout_days": 0, "delta_avg_inventory": -1}]
    assert _problem_class(current, excess, 365)[0] == "BOTH"
    assert _problem_class({"CURRENT_STOCKOUT_DAYS": 0}, excess, 365)[0] == "EXCESS_INVENTORY_PROBLEM"
    assert _problem_class(current, [], 365)[0] == "SERVICE_PROBLEM"
    assert _problem_class(current, [], 30)[0] == "INSUFFICIENT_HISTORY"


def test_robustness_bands_are_six_scenario_analytical_labels():
    assert _robustness_class(6) == "ROBUST_HIGH"
    assert _robustness_class(4) == "ROBUST_MEDIUM"
    assert _robustness_class(1) == "ROBUST_LOW"
    assert _robustness_class(0) == "NOT_ROBUST"
