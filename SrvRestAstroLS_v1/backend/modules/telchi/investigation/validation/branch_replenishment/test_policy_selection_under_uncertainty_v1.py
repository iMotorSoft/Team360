from modules.telchi.investigation.validation.branch_replenishment.policy_selection_under_uncertainty_v1 import (
    MATERIALITY,
    _material_inventory,
    _material_service,
    _regret_rows,
    _worst_case,
)


def _row(lt, availability, stockout, inventory, replenishments):
    return {
        "ItemCode": "L1",
        "Branch": "2A",
        "Policy": "DAYS_OF_SUPPLY",
        "policy_parameters": {"target_dos": 14},
        "LeadTimeScenario": lt,
        "policy_availability": availability,
        "policy_stockout_days": stockout,
        "policy_avg_inventory": inventory,
        "policy_replenishments": replenishments,
    }


def test_worst_case_uses_adverse_direction_for_each_metric():
    current = {"availability": .50, "stockout_days": 10, "average_inventory": 20, "replenishments": 5}
    result = _worst_case([
        _row(0, .90, 2, 30, 7),
        _row(7, .70, 6, 50, 9),
    ], current)
    assert result["WORST_CASE_AVAILABILITY"] == .70
    assert result["WORST_CASE_STOCKOUT_DAYS"] == 6
    assert result["WORST_CASE_AVG_INVENTORY"] == 50
    assert result["WORST_CASE_REPLENISHMENTS"] == 9


def test_materiality_does_not_count_microscopic_service_change():
    current = {"availability": .90, "stockout_days": 10, "average_inventory": 100, "replenishments": 10}
    assert not _material_service(_row(0, .911, 8, 100, 10), current)
    assert _material_service(_row(0, .90, 7, 100, 10), current)


def test_inventory_saving_requires_non_inferior_service():
    current = {"availability": .90, "stockout_days": 10, "average_inventory": 100, "replenishments": 10}
    assert _material_inventory(_row(0, .895, 12, 85, 10), current)
    assert not _material_inventory(_row(0, .80, 30, 50, 10), current)


def test_regret_is_zero_for_scenario_ideal():
    rows = [_row(0, .90, 4, 20, 3), _row(0, .80, 8, 40, 5)]
    regrets = _regret_rows(rows)
    ideal = next(row for row in regrets if row["Policy"] == "DAYS_OF_SUPPLY")
    # There are two candidate rows in the same LT; the first is ideal on all
    # dimensions and therefore has zero composite regret.
    assert ideal["REGRET"] == 0
    assert ideal["AVAILABILITY_REGRET"] == 0
    assert ideal["STOCKOUT_REGRET"] == 0


def test_thresholds_are_explicit_and_positive():
    assert MATERIALITY["availability_delta_min"] == .02
    assert MATERIALITY["inventory_reduction_pct_min"] == .10
