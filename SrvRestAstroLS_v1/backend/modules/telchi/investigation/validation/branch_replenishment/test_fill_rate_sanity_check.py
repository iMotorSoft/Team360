from datetime import date, timedelta

from modules.telchi.investigation.validation.branch_replenishment.backtest_engine_v1 import (
    PolicyConfiguration,
    simulate_pair,
)
from modules.telchi.investigation.validation.branch_replenishment.fill_rate_sanity_check import (
    audit_comparability,
    audit_current_pair,
    build_sensitivity_rows,
    normalise_daily_rows,
)


def _rows(days=70):
    start = date(2026, 1, 1)
    return [
        {
            "Date": start + timedelta(days=index),
            "StockEndOfDay": 10.0 if index != 35 else 0.0,
            "NET_MOVEMENT_QTY": 0.0,
            "OBSERVED_DEMAND": 2.0 if index % 3 == 0 and index != 35 else 0.0,
        }
        for index in range(days)
    ]


def _episode():
    return [{
        "StartDate": "2026-02-05", "EndDate": "2026-02-05",
        "ReplenishmentDate": "2026-02-06", "ReplenishmentQty": 10,
        "Confidence": "STRONG", "DemandClassification": "POSSIBLE_CENSORED_DEMAND",
    }]


def test_current_audit_marks_observed_ceiling_without_calling_sales_lost():
    audit = audit_current_pair("L1", "2A", _rows(), _episode())
    assert audit["current_fill_rate"] == 1.0
    assert audit["stockout_days"] == 1
    assert audit["observed_demand_ceiling_risk"] is True
    assert audit["possible_censored_demand_days"] == 1
    assert audit["sales_during_stockout_days"] == 0
    assert audit["service_basis"] == "OBSERVED_DEMAND_ONLY"


def test_sensitivity_uses_prior_history_and_not_future_demand_for_amount():
    rows = _rows()
    base, meta = build_sensitivity_rows(rows, _episode(), "BASE")
    changed = [dict(row) for row in rows]
    for row in changed[36:]:
        row["OBSERVED_DEMAND"] = 9000.0
    changed_base, changed_meta = build_sensitivity_rows(changed, _episode(), "BASE")
    target = next(row for row in base if row["Date"] == date(2026, 2, 5))
    changed_target = next(row for row in changed_base if row["Date"] == date(2026, 2, 5))
    assert target["SENSITIVITY_IMPUTED_DEMAND"] == changed_target["SENSITIVITY_IMPUTED_DEMAND"]
    assert meta["is_sales_fact"] is False
    assert changed_meta["amount_uses_future_demand"] is False


def test_low_is_observed_and_high_is_not_below_base():
    rows = normalise_daily_rows(_rows())
    low, low_meta = build_sensitivity_rows(rows, _episode(), "LOW")
    base, _ = build_sensitivity_rows(rows, _episode(), "BASE")
    high, _ = build_sensitivity_rows(rows, _episode(), "HIGH")
    index = next(index for index, row in enumerate(rows) if row["Date"] == date(2026, 2, 5))
    assert low[index]["OBSERVED_DEMAND"] == rows[index]["OBSERVED_DEMAND"]
    assert high[index]["OBSERVED_DEMAND"] >= base[index]["OBSERVED_DEMAND"]
    assert low_meta["imputed_days"] == 0


def test_comparability_checks_period_demand_and_initial_stock():
    rows = normalise_daily_rows(_rows())
    simulation = simulate_pair(
        "L1", "2A", rows,
        PolicyConfiguration("DAYS_OF_SUPPLY", {"target_dos": 14}), 3,
    )
    current = audit_current_pair("L1", "2A", rows, _episode())
    result = audit_comparability(rows, current, simulation)
    assert result["pass"] is True
    assert result["checks"]["same_period"] is True
    assert result["checks"]["same_observed_demand"] is True
    assert result["checks"]["same_initial_stock_reconstruction"] is True
