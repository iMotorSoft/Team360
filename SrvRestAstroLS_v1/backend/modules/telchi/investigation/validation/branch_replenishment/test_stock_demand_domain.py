from datetime import date

from modules.telchi.investigation.validation.branch_replenishment.stock_demand_domain import (
    availability_state,
    build_stockout_episodes,
    classify_censoring,
    days_of_supply,
    demand_row,
    movement_category,
    reconcile_latest,
    reconstruct_forward,
    reconstruct_inverse,
    replenishment_intervals,
    trailing_mean,
    validate_continuity,
)


def test_inverse_reconstruction_uses_current_anchor_and_continuity():
    start, end = date(2024, 1, 1), date(2024, 1, 3)
    daily = {date(2024, 1, 1): 5, date(2024, 1, 3): -2}
    stock = reconstruct_inverse(13, daily, start, end)
    assert stock == {date(2024, 1, 1): 15, date(2024, 1, 2): 15, date(2024, 1, 3): 13}
    assert validate_continuity(stock, daily)["pass"]


def test_forward_and_inverse_agree_when_opening_is_known():
    daily = {date(2024, 1, 1): 5, date(2024, 1, 3): -2}
    forward = reconstruct_forward(5, daily, date(2024, 1, 1), date(2024, 1, 3))
    inverse = reconstruct_inverse(8, daily, date(2024, 1, 1), date(2024, 1, 3))
    assert forward == inverse


def test_latest_reconciliation_is_exact_and_reports_difference():
    key = ("L1", "BR-SAL")
    series = {key: {date(2024, 1, 1): 2}}
    assert reconcile_latest(series, {key: 2})["pass"]
    bad = reconcile_latest(series, {key: 3})
    assert bad["differences"] == 1
    assert bad["max_abs_difference"] == 1


def test_daily_gap_is_not_silently_accepted():
    stock = {date(2024, 1, 1): 1, date(2024, 1, 3): 1}
    result = validate_continuity(stock, {})
    assert result["gaps"] == 1
    assert not result["pass"]


def test_availability_states_keep_low_threshold_pending():
    assert availability_state(None) == "UNKNOWN"
    assert availability_state(-1) == "NEGATIVE_STOCK"
    assert availability_state(0) == "ZERO_STOCK"
    assert availability_state(3) == "PENDING_POLICY_THRESHOLD"
    assert availability_state(3, 5) == "LOW_STOCK"
    assert availability_state(6, 5) == "IN_STOCK"


def test_sales_returns_and_transfers_are_separate():
    assert movement_category(13) == "SALES"
    assert movement_category(15) == "SALES"
    assert movement_category(14) == "RETURNS"
    assert movement_category(67) == "TRANSFER"
    row = demand_row(10, 2)
    assert row["NET_SALES_QTY"] == 8


def test_no_lookahead_in_trailing_mean_and_dos():
    values = {date(2024, 1, 1): 2, date(2024, 1, 2): 4, date(2024, 1, 3): 999}
    assert trailing_mean(values, date(2024, 1, 3), 30) == 3
    assert days_of_supply(30, values, date(2024, 1, 3), 30)["value"] == 10
    changed_future = {**values, date(2024, 1, 4): 100000}
    assert trailing_mean(changed_future, date(2024, 1, 3), 30) == 3


def test_conservative_censoring_classification():
    assert classify_censoring(10, 0, False, False, False) == "NO_CENSORING_EVIDENCE"
    assert classify_censoring(0, 0, True, True, True) == "POSSIBLE_CENSORED_DEMAND"
    assert classify_censoring(0, 0, False, False, False) == "UNPROVEN_CENSORED_DEMAND"


def test_stockout_episode_does_not_impute_lost_sales():
    rows = [
        {"ItemCode": "L1", "Branch": "B1", "Date": date(2024, 1, 1), "StockEndOfDay": 2, "availability_state": "PENDING_POLICY_THRESHOLD", "NET_SALES_QTY": 3, "TRANSFER_IN_QTY": 0},
        {"ItemCode": "L1", "Branch": "B1", "Date": date(2024, 1, 2), "StockEndOfDay": 0, "availability_state": "ZERO_STOCK", "NET_SALES_QTY": 0, "TRANSFER_IN_QTY": 0},
        {"ItemCode": "L1", "Branch": "B1", "Date": date(2024, 1, 3), "StockEndOfDay": 4, "availability_state": "PENDING_POLICY_THRESHOLD", "NET_SALES_QTY": 2, "TRANSFER_IN_QTY": 4},
    ]
    episodes = build_stockout_episodes(rows)
    assert len(episodes) == 1
    assert episodes[0]["Confidence"] == "STRONG"
    assert "LostSales" not in episodes[0]


def test_replenishment_intervals_use_distinct_event_dates():
    result = replenishment_intervals([{"date": date(2024, 1, 1)}, {"date": date(2024, 1, 1)}, {"date": date(2024, 1, 4)}])
    assert result["event_dates"] == 2
    assert result["days_between_replenishments"]["median"] == 3
