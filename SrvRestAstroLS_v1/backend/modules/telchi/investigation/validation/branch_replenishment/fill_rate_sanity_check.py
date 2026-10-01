"""Pure logic for TELCHI Gate 5A fill-rate and censored-demand sanity checks.

The check keeps ``OBSERVED_DEMAND`` as the primary, non-imputed measure.  LOW,
BASE and HIGH are explicitly sensitivity scenarios only; they never become
sales, lost-sales facts, or production recommendations.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from statistics import median
from typing import Any

EPSILON = 1e-9
NEAR_FULL_FILL_RATE = 0.999
SENSITIVITY_LEVELS = ("LOW", "BASE", "HIGH")


def _date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _demand(row: Mapping[str, Any]) -> float:
    # A present-but-null OBSERVED_DEMAND must still fall back to NET_SALES_QTY.
    value = row.get("OBSERVED_DEMAND")
    if value is None:
        value = row.get("NET_SALES_QTY", 0.0)
    return max(0.0, _float(value))


def normalise_daily_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        result.append({
            **row,
            "Date": _date(row["Date"]),
            "StockEndOfDay": _float(row.get("StockEndOfDay")),
            "OBSERVED_DEMAND": _demand(row),
            "NET_MOVEMENT_QTY": _float(row.get("NET_MOVEMENT_QTY")),
        })
    result.sort(key=lambda row: row["Date"])
    if len({row["Date"] for row in result}) != len(result):
        raise ValueError("daily rows must have one row per date")
    return result


def _episode_dates(episode: Mapping[str, Any]) -> tuple[date, date]:
    return _date(episode["StartDate"]), _date(episode["EndDate"])


def _episode_for_day(day: date, episodes: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for episode in episodes:
        start, end = _episode_dates(episode)
        if start <= day <= end:
            return episode
    return None


def _sum_demand(rows: Sequence[Mapping[str, Any]], start: date, end: date) -> float:
    return sum(row["OBSERVED_DEMAND"] for row in rows if start <= row["Date"] <= end)


def audit_current_pair(
    item_code: str,
    branch: str,
    daily_rows: Iterable[Mapping[str, Any]],
    episodes: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Audit observed CURRENT metrics and stockout context for one pair."""
    rows = normalise_daily_rows(daily_rows)
    if not rows:
        raise ValueError("sanity audit requires daily rows")
    episode_rows = sorted((dict(row) for row in episodes), key=lambda row: _episode_dates(row)[0])
    demand = sum(row["OBSERVED_DEMAND"] for row in rows)
    stockout_rows = [row for row in rows if row["StockEndOfDay"] <= EPSILON]
    zero_demand_stockout_rows = [row for row in stockout_rows if row["OBSERVED_DEMAND"] <= EPSILON]
    windows = []
    for episode in episode_rows:
        start, end = _episode_dates(episode)
        pre_start = start - timedelta(days=30)
        post_end = end + timedelta(days=30)
        pre_rows = [row for row in rows if pre_start <= row["Date"] < start]
        post_rows = [row for row in rows if end < row["Date"] <= post_end]
        episode_stockout = [row for row in stockout_rows if start <= row["Date"] <= end]
        possible = (
            episode.get("DemandClassification") == "POSSIBLE_CENSORED_DEMAND"
            and any(row["OBSERVED_DEMAND"] > EPSILON for row in pre_rows)
            and any(row["OBSERVED_DEMAND"] > EPSILON for row in post_rows)
            and _float(episode.get("ReplenishmentQty")) > EPSILON
        )
        windows.append({
            "start": start,
            "end": end,
            "duration_days": (end - start).days + 1,
            "stockout_days_in_window": len(episode_stockout),
            "observed_sales_during_stockout": sum(row["OBSERVED_DEMAND"] for row in episode_stockout),
            "zero_observed_demand_stockout_days": sum(row["OBSERVED_DEMAND"] <= EPSILON for row in episode_stockout),
            "sales_30d_before": _sum_demand(rows, pre_start, start - timedelta(days=1)),
            "sales_30d_after": _sum_demand(rows, end + timedelta(days=1), post_end),
            "pre_positive_days": sum(row["OBSERVED_DEMAND"] > EPSILON for row in pre_rows),
            "post_positive_days": sum(row["OBSERVED_DEMAND"] > EPSILON for row in post_rows),
            "replenishment_date": episode.get("ReplenishmentDate"),
            "replenishment_qty": _float(episode.get("ReplenishmentQty")),
            "confidence": episode.get("Confidence"),
            "demand_classification": episode.get("DemandClassification"),
            "possible_censored_demand": possible,
        })
    stockout_days = len(stockout_rows)
    durations = [int(window["stockout_days_in_window"]) for window in windows]
    observed_fill = 1.0 if demand > EPSILON else None
    possible_days = sum(
        int(window["zero_observed_demand_stockout_days"])
        for window in windows if window["possible_censored_demand"]
    )
    return {
        "ItemCode": item_code,
        "Branch": branch,
        "date_start": rows[0]["Date"],
        "date_end": rows[-1]["Date"],
        "days": len(rows),
        "observed_demand": demand,
        "fulfilled_observed_demand": demand,
        "current_fill_rate": observed_fill,
        "stockout_days": stockout_days,
        "stockout_episodes": len(episode_rows),
        "days_stock_leq_zero": stockout_days,
        "stockout_duration_days_total": sum(durations),
        "stockout_duration_mean": sum(durations) / len(durations) if durations else 0.0,
        "stockout_duration_median": median(durations) if durations else 0.0,
        "sales_during_stockout_days": sum(row["OBSERVED_DEMAND"] for row in stockout_rows),
        "sales_30d_before_stockout": sum(float(window["sales_30d_before"]) for window in windows),
        "sales_30d_after_stockout": sum(float(window["sales_30d_after"]) for window in windows),
        "zero_observed_demand_stockout_days": len(zero_demand_stockout_rows),
        "availability_days": len(rows) - stockout_days,
        "availability_rate": (len(rows) - stockout_days) / len(rows),
        "average_inventory": sum(max(0.0, row["StockEndOfDay"]) for row in rows) / len(rows),
        "near_100_fill_rate": observed_fill is not None and observed_fill >= NEAR_FULL_FILL_RATE,
        "observed_demand_ceiling_risk": bool(
            observed_fill is not None and observed_fill >= NEAR_FULL_FILL_RATE and stockout_days > 0
        ),
        "possible_censored_demand_days": possible_days,
        "observed_demand_ceiling_risk_with_evidence": bool(possible_days),
        "stockout_windows": windows,
        "service_basis": "OBSERVED_DEMAND_ONLY",
    }


def _historical_values(rows: Sequence[Mapping[str, Any]], day: date, window_days: int) -> list[float]:
    start = day - timedelta(days=window_days)
    return [row["OBSERVED_DEMAND"] for row in rows if start <= row["Date"] < day]


def _p90(values: Sequence[float]) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * 0.9
    low, high = int(position), min(int(position) + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def build_sensitivity_rows(
    daily_rows: Iterable[Mapping[str, Any]],
    episodes: Iterable[Mapping[str, Any]],
    level: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a reproducible non-sales sensitivity demand series.

    LOW is observed demand. BASE uses the prior 30-calendar-day mean and HIGH
    uses the larger of BASE and the prior-90-day positive-demand p90. Only zero
    demand days in a possible-censoring episode are adjusted. Episode
    eligibility uses pre/post evidence, but the amount imputed uses prior data
    only; this is a retrospective sensitivity, not a leakage-free forecast.
    """
    if level not in SENSITIVITY_LEVELS:
        raise ValueError(f"unknown sensitivity level: {level}")
    rows = normalise_daily_rows(daily_rows)
    episode_rows = list(episodes)
    output = []
    imputed_days = 0
    imputed_qty = 0.0
    for row in rows:
        value = dict(row)
        estimate_base = sum(_historical_values(rows, row["Date"], 30)) / 30.0
        positive_90 = [value for value in _historical_values(rows, row["Date"], 90) if value > EPSILON]
        estimate_high = max(estimate_base, _p90(positive_90))
        episode = _episode_for_day(row["Date"], episode_rows)
        eligible = bool(
            episode
            and episode.get("DemandClassification") == "POSSIBLE_CENSORED_DEMAND"
            and row["StockEndOfDay"] <= EPSILON
            and row["OBSERVED_DEMAND"] <= EPSILON
            and _float(episode.get("ReplenishmentQty")) > EPSILON
        )
        estimate = 0.0 if level == "LOW" else estimate_base if level == "BASE" else estimate_high
        added = estimate if eligible else 0.0
        value["OBSERVED_DEMAND"] = row["OBSERVED_DEMAND"] + added
        value["SENSITIVITY_LEVEL"] = level
        value["SENSITIVITY_ELIGIBLE"] = eligible
        value["SENSITIVITY_IMPUTED_DEMAND"] = added
        value["SENSITIVITY_ESTIMATE_BASE"] = estimate_base
        value["SENSITIVITY_ESTIMATE_HIGH"] = estimate_high
        output.append(value)
        if added > EPSILON:
            imputed_days += 1
            imputed_qty += added
    return output, {
        "level": level,
        "method": {
            "LOW": "OBSERVED_DEMAND_ONLY",
            "BASE": "PRIOR_30_CALENDAR_DAY_MEAN_ON_POSSIBLE_CENSORED_ZERO_DAYS",
            "HIGH": "MAX_BASE_PRIOR_90D_POSITIVE_DEMAND_P90_ON_POSSIBLE_CENSORED_ZERO_DAYS",
        }[level],
        "imputed_days": imputed_days,
        "imputed_demand": imputed_qty,
        "is_sales_fact": False,
        "is_lost_sales_claim": False,
        "eligibility_uses_post_episode_evidence": True,
        "amount_uses_future_demand": False,
    }


def audit_comparability(
    daily_rows: Iterable[Mapping[str, Any]],
    current: Mapping[str, Any],
    simulation: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove the shared period/demand/initial-stock contract for one run."""
    rows = normalise_daily_rows(daily_rows)
    demand = [row["OBSERVED_DEMAND"] for row in rows]
    stock = [row["StockEndOfDay"] for row in rows]
    movement = [row["NET_MOVEMENT_QTY"] for row in rows]
    inferred_opening = stock[0] - movement[0]
    simulation_opening = inferred_opening if simulation.get("initial_state_status") != "HISTORICAL_NEGATIVE_CLAMPED" else 0.0
    checks = {
        "same_period": current.get("date_start") == rows[0]["Date"] and current.get("date_end") == rows[-1]["Date"] and current.get("days") == len(rows),
        "same_observed_demand": current.get("observed_demand") == sum(demand),
        "same_simulation_demand": simulation.get("observed_demand") == sum(demand),
        "same_fulfillment_definition": current.get("service_basis") == "OBSERVED_DEMAND_ONLY" and current.get("fulfilled_observed_demand") == sum(demand) and simulation.get("service_basis") == "OBSERVED_DEMAND_ONLY",
        "same_initial_stock_reconstruction": abs((simulation_opening + movement[0]) - stock[0]) <= EPSILON,
        "same_intraday_convention": "opening -> scheduled arrivals -> policy -> observed demand -> closing",
    }
    passed = all(value is True for key, value in checks.items() if key != "same_intraday_convention")
    return {
        "checks": checks,
        "pass": passed,
        "period": {"start": rows[0]["Date"], "end": rows[-1]["Date"], "days": len(rows)},
        "initial_state": {
            "first_historical_stock_end_of_day": stock[0],
            "first_day_net_movement": movement[0],
            "inferred_opening_stock": inferred_opening,
            "simulation_opening_stock": simulation_opening,
            "simulation_initial_state_status": simulation.get("initial_state_status"),
        },
        "demand_basis": "same daily OBSERVED_DEMAND sequence; no imputation in LOW/observed comparison",
    }


def stable_daily_signature(rows: Iterable[Mapping[str, Any]]) -> str:
    values = normalise_daily_rows(rows)
    payload = [
        [row["Date"].isoformat(), row["StockEndOfDay"], row["OBSERVED_DEMAND"], row["NET_MOVEMENT_QTY"]]
        for row in values
    ]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=False).encode()).hexdigest()


def scenario_fill_rate(
    fulfilled: float, demand: float
) -> float | None:
    return fulfilled / demand if demand > EPSILON else None


def metric_summary(values: Iterable[float]) -> dict[str, Any]:
    values = [float(value) for value in values]
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "median": median(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }
