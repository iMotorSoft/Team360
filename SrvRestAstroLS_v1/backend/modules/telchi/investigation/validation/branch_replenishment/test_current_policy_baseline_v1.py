from datetime import date, timedelta

from modules.telchi.investigation.validation.branch_replenishment.current_policy_baseline_v1 import (
    build_current_policy_baseline,
    demand_coverage_before,
    enrich_replenishment_events,
)


def _daily(start=date(2024, 1, 1), days=100, stock=20, demand=2):
    return [
        {
            "ItemCode": "L1", "Branch": "2A", "Date": start + timedelta(days=i),
            "StockEndOfDay": stock - demand * i,
            "NET_SALES_QTY": demand, "NET_MOVEMENT_QTY": -demand,
        }
        for i in range(days)
    ]


def test_coverage_is_strictly_prior_and_marks_short_windows():
    rows = {r["Date"]: r for r in _daily(days=100)}
    result = demand_coverage_before(rows, date(2024, 4, 10))
    assert result["AVG_DEMAND_7D"] == 2
    assert result["AVG_DEMAND_30D"] == 2
    assert result["AVG_DEMAND_90D"] == 2
    # No row from the event date may enter the window.
    rows[date(2024, 4, 9)]["NET_SALES_QTY"] = 200
    assert demand_coverage_before(rows, date(2024, 4, 10))["AVG_DEMAND_7D"] == 2 + 198 / 7
    short = demand_coverage_before({r["Date"]: r for r in _daily(days=10)}, date(2024, 1, 10))
    assert short["DEMAND_STATUS_30D"] == "INSUFFICIENT_HISTORY"


def test_event_stock_is_adjusted_for_same_day_movement_and_sequence_unknown():
    rows = _daily(days=10, stock=100, demand=2)
    rows[7]["StockEndOfDay"] = 112
    rows[7]["NET_MOVEMENT_QTY"] = 12  # transfer 20 plus a concurrent -8 sale
    events = [{
        "ItemCode": "L1", "Branch": "2A", "Date": date(2024, 1, 8),
        "Warehouse": "2A-SAL", "SourceType": "TRANSFER_FROM_CENTRAL", "ReplenishmentQty": 20,
    }]
    enriched = enrich_replenishment_events(rows, events)
    assert enriched[0]["STOCK_BEFORE"] == 88
    assert enriched[0]["CONCURRENT_NET_MOVEMENT"] == -8
    assert enriched[0]["STOCK_AFTER"] == 100
    assert enriched[0]["INTRADAY_SEQUENCE"] == "UNKNOWN"
    assert enriched[0]["AVG_DEMAND_7D"] == 2


def test_stockout_context_and_replenishment_metrics_are_exposed():
    rows = _daily(days=100, stock=20, demand=2)
    events = [
        {"ItemCode": "L1", "Branch": "2A", "Date": date(2024, 2, 10), "SourceType": "TRANSFER_FROM_CENTRAL", "ReplenishmentQty": 10},
        {"ItemCode": "L1", "Branch": "2A", "Date": date(2024, 2, 20), "SourceType": "TRANSFER_FROM_CENTRAL", "ReplenishmentQty": 10},
    ]
    episodes = [{"ItemCode": "L1", "Branch": "2A", "StartDate": date(2024, 2, 15), "EndDate": date(2024, 2, 17)}]
    result = build_current_policy_baseline(rows, events, episodes)
    assert result["event_count"] == 2
    assert result["events"][0]["STOCKOUT_CONTEXT"] == "BEFORE_STOCKOUT"
    assert result["events"][1]["STOCKOUT_CONTEXT"] == "AFTER_STOCKOUT"
    pair = result["item_branch"][0]
    assert pair["replenishment_interval_median"] == 10
    assert pair["replenishment_qty_total"] == 20
    assert pair["source_counts"]["TRANSFER_FROM_CENTRAL"] == 2
    assert pair["policy_class"] != "MIN_MAX_LIKE"  # no intuition-based claim


def test_active_stock_pair_without_event_is_retained_as_insufficient():
    rows = _daily(days=10)
    rows += [{"ItemCode": "L2", "Branch": "2A", "Date": date(2024, 1, 1), "StockEndOfDay": 5, "NET_SALES_QTY": 0, "NET_MOVEMENT_QTY": 0}]
    result = build_current_policy_baseline(rows, [])
    missing = next(row for row in result["item_branch"] if row["ItemCode"] == "L2")
    assert missing["replenishment_count"] == 0
    assert missing["policy_class"] == "INSUFFICIENT_EVENTS"


def test_no_stockout_context_is_not_reactive():
    rows = _daily(days=100)
    events = [
        {"ItemCode": "L1", "Branch": "2A", "Date": date(2024, 2, 10), "SourceType": "TRANSFER_FROM_CENTRAL", "ReplenishmentQty": 10},
        {"ItemCode": "L1", "Branch": "2A", "Date": date(2024, 2, 20), "SourceType": "TRANSFER_FROM_CENTRAL", "ReplenishmentQty": 10},
    ]
    result = build_current_policy_baseline(rows, events)
    assert all(e["STOCKOUT_CONTEXT"] == "NO_STOCKOUT_CONTEXT" for e in result["events"])
    assert result["item_branch"][0]["pct_replenishment_at_or_after_stockout"] == 0
