"""Deterministic, no-look-ahead replenishment backtest for TELCHI.

This module is deliberately independent from HANA and the filesystem.  A caller
provides one ``ItemCode x Branch`` daily history and the engine simulates only
that pair.  The runner can therefore partition by branch/item and persist
summaries without retaining trajectories for the whole universe.

Semantics V1
------------
* end-of-day historical rows are used only as observations;
* the simulated intraday order is ``opening -> scheduled arrivals -> policy ->
  demand -> closing``;
* an order emitted on T with lead time N is due on T+N.  LT=0 is available for
  the same day's demand after the decision;
* observed demand is never imputed during stockout;
* simulated stock is never negative and shortage is explicit;
* every parameter estimate uses dates strictly before the decision date.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

POLICIES = (
    "CURRENT_POLICY",
    "MIN_MAX",
    "REORDER_POINT",
    "DAYS_OF_SUPPLY",
    "PERIODIC_REVIEW",
    "DYNAMIC_TARGET",
    "HYBRID",
)
LEAD_TIME_SCENARIOS = (0, 1, 2, 3, 5, 7)
DOS_TARGETS = (7, 14, 21, 30, 45, 60)
PERIODIC_REVIEW_DAYS = (1, 3, 7, 14)
SERVICE_LEVELS = (0.95, 0.97, 0.98, 0.99)
Z_BY_SERVICE = {0.95: 1.644853626951, 0.97: 1.880793608151, 0.98: 2.05374891, 0.99: 2.326347874}
EPSILON = 1e-9
METRIC_TOLERANCE = 0.001
LOGISTICS_REPLENISHMENT_MULTIPLIER = 2.0
LOGISTICS_REPLENISHMENT_MARGIN = 3


@dataclass(frozen=True)
class PolicyConfiguration:
    name: str
    parameters: Mapping[str, Any]
    warmup_days: int = 30


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _row_value(row: Any, field: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(field, default)
    # Compact source shape: (stock_end, observed_demand, net_movement).
    return {
        "StockEndOfDay": row[0] if len(row) > 0 else default,
        "NET_SALES_QTY": row[1] if len(row) > 1 else default,
        "OBSERVED_DEMAND": row[1] if len(row) > 1 else default,
        "NET_MOVEMENT_QTY": row[2] if len(row) > 2 else default,
    }.get(field, default)


def _normalise_rows(rows: Iterable[Mapping[str, Any] | Sequence[Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            day = _as_date(row["Date"])
        else:
            raise TypeError("daily rows must expose Date and stock/demand fields")
        demand = _number(row.get("OBSERVED_DEMAND", row.get("NET_SALES_QTY", 0)))
        result.append({
            **row,
            "Date": day,
            "StockEndOfDay": _number(row.get("StockEndOfDay")),
            "OBSERVED_DEMAND": max(0.0, demand),
            "NET_MOVEMENT_QTY": _number(row.get("NET_MOVEMENT_QTY")),
        })
    result.sort(key=lambda item: item["Date"])
    return result


def _daily_from_compact(
    daily: Mapping[date, Sequence[float]] | Mapping[date, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_day, value in daily.items():
        day = _as_date(raw_day)
        if isinstance(value, Mapping):
            rows.append({"Date": day, **value})
        else:
            rows.append({
                "Date": day,
                "StockEndOfDay": _row_value(value, "StockEndOfDay", 0),
                "OBSERVED_DEMAND": _row_value(value, "OBSERVED_DEMAND", 0),
                "NET_MOVEMENT_QTY": _row_value(value, "NET_MOVEMENT_QTY", 0),
            })
    return _normalise_rows(rows)


def _history_values(rows: list[dict[str, Any]], index: int, window: int) -> list[float]:
    """Return calendar observations strictly before index, never T or future."""
    start = max(0, index - window)
    values = [float(row["OBSERVED_DEMAND"]) for row in rows[start:index]]
    return values


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _percentile(values: Iterable[float], p: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _z(service_level: float) -> float:
    key = min(Z_BY_SERVICE, key=lambda candidate: abs(candidate - service_level))
    return Z_BY_SERVICE[key]


def policy_configurations() -> list[PolicyConfiguration]:
    """Small, explicit V1 grid; no brute-force parameter search."""
    configurations: list[PolicyConfiguration] = []
    configurations.extend(
        PolicyConfiguration("MIN_MAX", {"min_days": minimum, "max_days": maximum})
        for minimum, maximum in ((7, 30), (14, 45))
    )
    configurations.extend(
        PolicyConfiguration("REORDER_POINT", {"service_level": level, "review_days": 7})
        for level in SERVICE_LEVELS
    )
    configurations.extend(
        PolicyConfiguration(
            "DAYS_OF_SUPPLY",
            {"target_dos": target, "trigger_dos": max(1, target // 2)},
        )
        for target in DOS_TARGETS
    )
    configurations.extend(
        PolicyConfiguration(
            "PERIODIC_REVIEW",
            {"review_period_days": period, "target_dos": 30},
        )
        for period in PERIODIC_REVIEW_DAYS
    )
    configurations.extend(
        PolicyConfiguration("DYNAMIC_TARGET", {"target_dos": target, "service_level": 0.98})
        for target in (21, 30)
    )
    configurations.append(PolicyConfiguration("HYBRID", {"target_dos": 30, "service_level": 0.98}))
    return configurations


def _hybrid_policy(history: Sequence[float]) -> str:
    if not history or sum(value > 0 for value in history) / len(history) <= 0.25:
        return "PERIODIC_REVIEW"
    if _mean(history) and _std(history) / _mean(history) > 1.0:
        return "DYNAMIC_TARGET"
    return "REORDER_POINT"


def _decision(
    policy: str,
    parameters: Mapping[str, Any],
    day: date,
    first_day: date,
    lead_time_days: int,
    inventory_position: float,
    history: Sequence[float],
) -> dict[str, Any]:
    """Return an explainable decision using only ``history`` (strictly prior)."""
    warmup = 30
    if len(history) < warmup:
        return {"trigger": False, "order_qty": 0.0, "reason": "WARMUP", "expected_daily_demand": None}
    window = min(30, len(history))
    recent = list(history[-window:])
    average = _mean(recent)
    deviation = _std(recent)
    if average <= EPSILON:
        return {"trigger": False, "order_qty": 0.0, "reason": "NO_DEMAND", "expected_daily_demand": 0.0}

    effective_policy = _hybrid_policy(history) if policy == "HYBRID" else policy
    target_days = float(parameters.get("target_dos", 30))
    service_level = float(parameters.get("service_level", 0.98))
    safety = _z(service_level) * deviation * math.sqrt(max(1, lead_time_days))
    if effective_policy == "MIN_MAX":
        minimum = average * float(parameters.get("min_days", 7))
        target = average * float(parameters.get("max_days", 30))
        trigger = inventory_position <= minimum + EPSILON
        order = max(0.0, target - inventory_position) if trigger else 0.0
        reason = "INVENTORY_POSITION_AT_OR_BELOW_MIN"
    elif effective_policy == "REORDER_POINT":
        reorder_point = average * lead_time_days + safety
        target = average * (lead_time_days + float(parameters.get("review_days", 7))) + safety
        trigger = inventory_position <= reorder_point + EPSILON
        order = max(0.0, target - inventory_position) if trigger else 0.0
        reason = "INVENTORY_POSITION_AT_OR_BELOW_ROP"
    elif effective_policy == "DAYS_OF_SUPPLY":
        trigger_level = average * float(parameters.get("trigger_dos", max(1, target_days / 2)))
        target = average * (lead_time_days + target_days)
        trigger = inventory_position <= trigger_level + EPSILON
        order = max(0.0, target - inventory_position) if trigger else 0.0
        reason = "DOS_AT_OR_BELOW_TRIGGER"
    elif effective_policy == "PERIODIC_REVIEW":
        period = int(parameters.get("review_period_days", 7))
        review = (day - first_day).days % max(1, period) == 0
        target = average * (lead_time_days + target_days)
        trigger = review and inventory_position < target - EPSILON
        order = max(0.0, target - inventory_position) if trigger else 0.0
        reason = "PERIODIC_REVIEW" if review else "NOT_REVIEW_DATE"
    elif effective_policy == "DYNAMIC_TARGET":
        short = _mean(history[-7:])
        long = _mean(history[-30:])
        trend = max(0.0, short - long)
        expected = max(0.0, long + trend / 2)
        safety_dynamic = _z(service_level) * deviation * math.sqrt(max(1, lead_time_days))
        reorder_point = expected * lead_time_days + safety_dynamic
        target = expected * (lead_time_days + target_days) + safety_dynamic
        trigger = inventory_position <= reorder_point + EPSILON
        order = max(0.0, target - inventory_position) if trigger else 0.0
        average = expected
        safety = safety_dynamic
        reason = "DYNAMIC_TARGET_AT_OR_BELOW_TRIGGER"
    else:
        raise ValueError(f"unsupported policy: {policy}")
    return {
        "trigger": bool(trigger and order > EPSILON),
        "order_qty": order,
        "reason": reason if trigger else "NO_TRIGGER",
        "effective_policy": effective_policy,
        "expected_daily_demand": average,
        "demand_stddev": deviation,
        "safety_stock": safety,
        "inventory_position": inventory_position,
    }


def _episode_metrics(flags: Sequence[bool]) -> dict[str, Any]:
    durations: list[int] = []
    current = 0
    for flag in list(flags) + [False]:
        if flag:
            current += 1
        elif current:
            durations.append(current)
            current = 0
    return {
        "stockout_days": sum(durations),
        "stockout_episodes": len(durations),
        "stockout_duration_mean": _mean(durations) if durations else 0.0,
        "stockout_duration_median": median(durations) if durations else 0.0,
        "stockout_duration_p90": _percentile(durations, 0.9) or 0.0,
        "stockout_duration_max": max(durations, default=0),
    }


def _base_metrics(
    item_code: str,
    branch: str,
    rows: list[dict[str, Any]],
    policy: str,
    parameters: Mapping[str, Any],
    lead_time_days: int | None,
    *,
    stock: Sequence[float],
    demand: Sequence[float],
    fulfilled: Sequence[float],
    unfulfilled: Sequence[float],
    orders: Sequence[float],
    order_dates: Sequence[date],
    dos_values: Sequence[float],
    warmup_days: int,
    initial_state_status: str,
    source_constrained: bool = False,
) -> dict[str, Any]:
    total_demand = sum(demand)
    intervals = [(b - a).days for a, b in zip(order_dates, order_dates[1:])]
    episode = _episode_metrics([value <= EPSILON for value in stock])
    return {
        "ItemCode": item_code,
        "Branch": branch,
        "Policy": policy,
        "policy_name": policy,
        "policy_parameters": dict(parameters),
        "LeadTimeScenario": lead_time_days,
        "assumed_lead_time_days": lead_time_days,
        "source_mode": "SOURCE_CONSTRAINED" if source_constrained else "UNCONSTRAINED",
        "warmup_days": warmup_days,
        "initial_state_status": initial_state_status,
        "date_start": rows[0]["Date"],
        "date_end": rows[-1]["Date"],
        "days": len(rows),
        "observed_demand": total_demand,
        "fulfilled_observed_demand": sum(fulfilled),
        "unfulfilled_observed_demand": sum(unfulfilled),
        "fill_rate": (sum(fulfilled) / total_demand) if total_demand > EPSILON else None,
        "average_inventory": _mean(stock),
        "median_inventory": median(stock) if stock else 0.0,
        "max_inventory": max(stock, default=0.0),
        "inventory_days": sum(stock),
        "availability_days": sum(value > EPSILON for value in stock),
        "availability_rate": (sum(value > EPSILON for value in stock) / len(stock)) if stock else None,
        "average_days_of_supply": _mean(dos_values) if dos_values else None,
        "max_days_of_supply": max(dos_values, default=None),
        **episode,
        "replenishment_count": sum(value > EPSILON for value in orders),
        "replenishment_quantity": sum(orders),
        "average_order_quantity": _mean([value for value in orders if value > EPSILON]),
        "median_order_quantity": median([value for value in orders if value > EPSILON]) if any(value > EPSILON for value in orders) else 0.0,
        "replenishment_interval_mean": _mean(intervals) if intervals else None,
        "replenishment_interval_median": median(intervals) if intervals else None,
        "emergency_like_replenishment_count": sum(
            value > EPSILON and (available <= EPSILON)
            for value, available in zip(orders, stock)
        ),
        "historical_negative_stock_days": sum(value < -EPSILON for value in stock),
        "service_basis": "OBSERVED_DEMAND_ONLY",
    }


def current_policy_metrics(
    item_code: str,
    branch: str,
    daily_rows: Iterable[Mapping[str, Any]],
    replenishment_events: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Describe the observed operation; never fit a formula to reproduce it."""
    rows = _normalise_rows(daily_rows)
    if not rows:
        raise ValueError("current baseline requires at least one daily row")
    stock = [max(0.0, row["StockEndOfDay"]) for row in rows]
    raw_stock = [row["StockEndOfDay"] for row in rows]
    demand = [row["OBSERVED_DEMAND"] for row in rows]
    event_days: dict[date, float] = defaultdict(float)
    for event in replenishment_events:
        event_days[_as_date(event["Date"])] += max(0.0, _number(event.get("ReplenishmentQty", event.get("REPLENISHMENT_QTY", 0))))
    order_dates = sorted(event_days)
    orders = [event_days[day] for day in order_dates]
    result = _base_metrics(
        item_code, branch, rows, "CURRENT_POLICY", {}, None,
        stock=stock, demand=demand, fulfilled=demand, unfulfilled=[0.0] * len(rows),
        orders=orders, order_dates=order_dates,
        dos_values=[stock_value / _mean(demand[max(0, index - 30):index]) for index, stock_value in enumerate(stock) if _mean(demand[max(0, index - 30):index]) > EPSILON],
        warmup_days=0,
        initial_state_status="OBSERVED_HISTORICAL_STATE",
    )
    result["historical_average_inventory_raw_nonnegative"] = _mean(stock)
    result["historical_min_stock_raw"] = min(raw_stock, default=0.0)
    result["historical_stockout_days_raw"] = sum(value <= EPSILON for value in raw_stock)
    result["historical_stockout_episodes_raw"] = _episode_metrics([value <= EPSILON for value in raw_stock])["stockout_episodes"]
    stock_by_day = {row["Date"]: row["StockEndOfDay"] for row in rows}
    result["emergency_like_replenishment_count"] = sum(
        quantity > EPSILON and stock_by_day.get(day, 0.0) <= EPSILON
        for day, quantity in event_days.items()
    )
    return result


def simulate_pair(
    item_code: str,
    branch: str,
    daily_rows: Iterable[Mapping[str, Any]],
    policy: str | PolicyConfiguration,
    lead_time_days: int,
    *,
    source_capacity_by_date: Mapping[date, float] | None = None,
    trace: bool = False,
) -> dict[str, Any]:
    """Run one deterministic pair/policy/lead-time simulation."""
    if lead_time_days not in LEAD_TIME_SCENARIOS and lead_time_days < 0:
        raise ValueError("lead time must be a non-negative integer")
    rows = _normalise_rows(daily_rows)
    if not rows:
        raise ValueError("simulation requires at least one daily row")
    config = policy if isinstance(policy, PolicyConfiguration) else PolicyConfiguration(str(policy), {})
    parameters = dict(config.parameters)
    demand = [row["OBSERVED_DEMAND"] for row in rows]
    first = rows[0]["Date"]
    inferred_opening = rows[0]["StockEndOfDay"] - rows[0]["NET_MOVEMENT_QTY"]
    if inferred_opening < -EPSILON:
        initial_state_status = "HISTORICAL_NEGATIVE_CLAMPED"
        opening_stock = 0.0
    else:
        initial_state_status = "RECONCILED_INITIAL_STATE"
        opening_stock = max(0.0, inferred_opening)

    arrivals: dict[date, float] = defaultdict(float)
    outstanding: list[tuple[date, float]] = []
    closing: list[float] = []
    fulfilled: list[float] = []
    unfulfilled: list[float] = []
    orders: list[float] = []
    order_dates: list[date] = []
    dos_values: list[float] = []
    decisions: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    source_shortage_total = 0.0

    for index, row in enumerate(rows):
        day = row["Date"]
        due = arrivals.pop(day, 0.0)
        future_incoming = sum(quantity for arrival, quantity in outstanding if arrival > day)
        inventory_position = opening_stock + due + future_incoming
        history = _history_values(rows, index, 30)
        decision = _decision(config.name, parameters, day, first, lead_time_days, inventory_position, history)
        requested = max(0.0, float(decision.get("order_qty", 0.0)))
        capacity = float("inf")
        if source_capacity_by_date is not None:
            capacity = max(0.0, float(source_capacity_by_date.get(day, 0.0)))
        order = min(requested, capacity)
        source_shortage_total += max(0.0, requested - order) if math.isfinite(capacity) else 0.0
        arrival_day = day + timedelta(days=lead_time_days)
        same_day_arrival = order if lead_time_days == 0 else 0.0
        if order > EPSILON:
            orders.append(order)
            order_dates.append(day)
            if lead_time_days == 0:
                due += order
            else:
                arrivals[arrival_day] += order
                outstanding.append((arrival_day, order))
        available = opening_stock + due
        observed = demand[index]
        served = min(max(0.0, available), observed)
        shortage = max(0.0, observed - served)
        end_stock = max(0.0, available - served)
        average_demand = _mean(history[-30:])
        dos = end_stock / average_demand if average_demand > EPSILON else None
        if dos is not None:
            dos_values.append(dos)
        fulfilled.append(served)
        unfulfilled.append(shortage)
        closing.append(end_stock)
        decision_row = {
            "date": day,
            "opening_stock": opening_stock,
            "scheduled_incoming": due - same_day_arrival,
            "inventory_position": inventory_position,
            "observed_demand": observed,
            "fulfilled_demand": served,
            "unfulfilled_demand": shortage,
            "order_trigger": bool(decision.get("trigger")),
            "order_qty_requested": requested,
            "order_qty": order,
            "scheduled_arrival_date": arrival_day,
            "arrival": due,
            "closing_stock": end_stock,
            "policy_name": config.name,
            "policy_parameters": parameters,
            "decision_reason": decision.get("reason"),
            "effective_policy": decision.get("effective_policy", config.name),
            "expected_daily_demand": decision.get("expected_daily_demand"),
            "safety_stock": decision.get("safety_stock"),
            "source_capacity": None if not math.isfinite(capacity) else capacity,
            "source_shortage": max(0.0, requested - order) if math.isfinite(capacity) else 0.0,
        }
        decisions.append(decision_row)
        if trace:
            trace_rows.append(decision_row)
        opening_stock = end_stock
        # Retain only future orders; same-day arrival has already been consumed.
        outstanding = [(arrival, quantity) for arrival, quantity in outstanding if arrival > day]

    result = _base_metrics(
        item_code, branch, rows, config.name, parameters, lead_time_days,
        stock=closing, demand=demand, fulfilled=fulfilled, unfulfilled=unfulfilled,
        orders=orders, order_dates=order_dates, dos_values=dos_values,
        warmup_days=config.warmup_days, initial_state_status=initial_state_status,
        source_constrained=source_capacity_by_date is not None,
    )
    result["source_shortage_quantity"] = source_shortage_total
    result["order_trigger_count"] = sum(bool(row["order_trigger"]) for row in decisions)
    result["emergency_like_replenishment_count"] = sum(
        row["order_qty"] > EPSILON and row["opening_stock"] + row["arrival"] <= EPSILON
        for row in decisions
    )
    result["trace"] = trace_rows if trace else None
    return result


def compare_to_current(current: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    fill = result.get("fill_rate")
    current_fill = current.get("fill_rate")
    avg_inventory = float(result.get("average_inventory") or 0)
    current_inventory = float(current.get("average_inventory") or 0)
    stockout = int(result.get("stockout_days") or 0)
    current_stockout = int(current.get("historical_stockout_days_raw") or current.get("stockout_days") or 0)
    replenishments = int(result.get("replenishment_count") or 0)
    current_replenishments = int(current.get("replenishment_count") or 0)
    result = dict(result)
    result.update({
        "current_fill_rate": current_fill,
        "policy_fill_rate": fill,
        "delta_fill_rate": (fill - current_fill) if fill is not None and current_fill is not None else None,
        "current_avg_inventory": current_inventory,
        "policy_avg_inventory": avg_inventory,
        "delta_avg_inventory": avg_inventory - current_inventory,
        "current_stockout_days": current_stockout,
        "policy_stockout_days": stockout,
        "delta_stockout_days": stockout - current_stockout,
        "current_replenishments": current_replenishments,
        "policy_replenishments": replenishments,
        "delta_replenishments": replenishments - current_replenishments,
    })
    current_availability = float(current.get("availability_rate") or 0.0)
    policy_availability = float(result.get("availability_rate") or 0.0)
    availability_delta = policy_availability - current_availability
    stockout_delta = stockout - current_stockout
    service_improves = availability_delta > METRIC_TOLERANCE and stockout_delta < 0
    service_comparable = abs(availability_delta) <= METRIC_TOLERANCE and stockout_delta == 0
    service_cost = availability_delta < -METRIC_TOLERANCE or stockout_delta > 0
    inventory_reduced = avg_inventory < current_inventory - EPSILON
    inventory_cost = avg_inventory > current_inventory + EPSILON
    replenishment_limit = max(
        current_replenishments * LOGISTICS_REPLENISHMENT_MULTIPLIER,
        current_replenishments + LOGISTICS_REPLENISHMENT_MARGIN,
    )
    excessive_replenishment = replenishments > replenishment_limit

    result.update({
        "current_availability": current_availability,
        "policy_availability": policy_availability,
        "delta_availability": availability_delta,
        "current_stockout_days": current_stockout,
        "policy_stockout_days": stockout,
        "delta_stockout_days": stockout_delta,
        "current_avg_inventory": current_inventory,
        "policy_avg_inventory": avg_inventory,
        "delta_avg_inventory": avg_inventory - current_inventory,
        "current_replenishments": current_replenishments,
        "policy_replenishments": replenishments,
        "delta_replenishments": replenishments - current_replenishments,
        # Upper-case aliases are the Gate 5B export contract.  Lower-case
        # fields remain for backwards compatibility with Gate 5A artifacts.
        "CURRENT_AVAILABILITY": current_availability,
        "POLICY_AVAILABILITY": policy_availability,
        "DELTA_AVAILABILITY": availability_delta,
        "CURRENT_STOCKOUT_DAYS": current_stockout,
        "POLICY_STOCKOUT_DAYS": stockout,
        "DELTA_STOCKOUT_DAYS": stockout_delta,
        "CURRENT_AVG_INVENTORY": current_inventory,
        "POLICY_AVG_INVENTORY": avg_inventory,
        "DELTA_AVG_INVENTORY": avg_inventory - current_inventory,
        "CURRENT_REPLENISHMENTS": current_replenishments,
        "POLICY_REPLENISHMENTS": replenishments,
        "DELTA_REPLENISHMENTS": replenishments - current_replenishments,
        "excessive_replenishment": excessive_replenishment,
        "observed_fill_rate_secondary": fill,
        "current_observed_fill_rate_secondary": current_fill,
    })
    if result.get("initial_state_status") == "HISTORICAL_NEGATIVE_CLAMPED":
        result["result_class"] = "INCONCLUSIVE"
    elif result.get("pareto_status") == "DOMINATED":
        result["result_class"] = "DOMINATED"
    elif excessive_replenishment and (service_improves or (service_comparable and inventory_reduced)):
        result["result_class"] = "LOGISTICS_COST"
    elif service_improves and not inventory_cost:
        result["result_class"] = "CLEAR_WIN"
    elif service_improves and inventory_cost:
        result["result_class"] = "AVAILABILITY_WIN_WITH_INVENTORY_COST"
    elif service_comparable and inventory_reduced:
        result["result_class"] = "CLEAR_WIN"
    elif service_cost and inventory_reduced:
        result["result_class"] = "INVENTORY_WIN_WITH_AVAILABILITY_COST"
    else:
        result["result_class"] = "INCONCLUSIVE"
    return result


def pareto_frontier(results: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in results]
    for row in rows:
        row["pareto_status"] = "PARETO_OPTIMAL"
    for index, candidate in enumerate(rows):
        candidate_availability = float(candidate.get("availability_rate") or 0)
        candidate_inventory = float(candidate.get("average_inventory") or 0)
        candidate_orders = float(candidate.get("replenishment_count") or 0)
        for other_index, other in enumerate(rows):
            if index == other_index:
                continue
            other_availability = float(other.get("availability_rate") or 0)
            other_inventory = float(other.get("average_inventory") or 0)
            other_orders = float(other.get("replenishment_count") or 0)
            no_worse = other_availability >= candidate_availability - METRIC_TOLERANCE and other_inventory <= candidate_inventory + EPSILON and other_orders <= candidate_orders
            strictly_better = other_availability > candidate_availability + METRIC_TOLERANCE or other_inventory < candidate_inventory - EPSILON or other_orders < candidate_orders
            if no_worse and strictly_better:
                candidate["pareto_status"] = "DOMINATED"
                break
    return rows


def classify_robustness(results: Iterable[Mapping[str, Any]], minimum_scenarios: int = 4) -> list[dict[str, Any]]:
    rows = [dict(row) for row in results]
    by_policy: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        parameters = json.dumps(row.get("policy_parameters", {}), sort_keys=True, default=str)
        key = (str(row.get("ItemCode")), str(row.get("Branch")), str(row.get("Policy")), parameters)
        by_policy[key].append(row)
    for key, policy_rows in by_policy.items():
        pareto_count = sum(row.get("pareto_status") == "PARETO_OPTIMAL" for row in policy_rows)
        advantage_count = sum(
            row.get("pareto_status") == "PARETO_OPTIMAL"
            and (
                float(row.get("delta_availability") or 0.0) > METRIC_TOLERANCE
                or int(row.get("delta_stockout_days") or 0) < 0
                or (
                    abs(float(row.get("delta_availability") or 0.0)) <= METRIC_TOLERANCE
                    and int(row.get("delta_stockout_days") or 0) == 0
                    and float(row.get("delta_avg_inventory") or 0.0) < -EPSILON
                )
            )
            for row in policy_rows
        )
        robust = advantage_count >= minimum_scenarios
        for row in policy_rows:
            row["pareto_lt_count"] = pareto_count
            row["ROBUST_LT_COUNT"] = advantage_count
            row["robust_policy"] = robust
            row["robust_scenarios"] = advantage_count
            row["robustness_definition"] = (
                "PARETO_OPTIMAL with service improvement or lower inventory under "
                f">= {minimum_scenarios} lead-time scenarios"
            )
    return rows


def run_pair(
    item_code: str,
    branch: str,
    daily_rows: Iterable[Mapping[str, Any]],
    replenishment_events: Iterable[Mapping[str, Any]] = (),
    configurations: Iterable[PolicyConfiguration] | None = None,
    lead_times: Iterable[int] = LEAD_TIME_SCENARIOS,
    *,
    source_capacity_by_date: Mapping[date, float] | None = None,
    trace_policy: str | None = None,
) -> dict[str, Any]:
    rows = _normalise_rows(daily_rows)
    event_rows = list(replenishment_events)
    current = current_policy_metrics(item_code, branch, rows, event_rows)
    simulations: list[dict[str, Any]] = []
    configs = list(configurations or policy_configurations())
    for config in configs:
        for lead_time in lead_times:
            simulated = simulate_pair(
                item_code, branch, rows, config, int(lead_time),
                source_capacity_by_date=source_capacity_by_date,
                trace=(trace_policy == config.name),
            )
            simulations.append(compare_to_current(current, simulated))
    frontier = pareto_frontier([current, *simulations])
    current = frontier[0]
    simulations = classify_robustness(frontier[1:])
    # Pareto status is known only after all scenarios are compared.  Re-run the
    # primary classification so DOMINATED is an actual result class rather than
    # a status that can be missed during the initial pair comparison.
    simulations = [compare_to_current(current, row) for row in simulations]
    return {
        "current": current,
        "simulations": simulations,
        "trace": next((row.get("trace") for row in simulations if row.get("trace")), None),
    }


def deterministic_signature(value: Mapping[str, Any]) -> tuple[Any, ...]:
    """Stable compact signature used by tests and runner reproducibility checks."""
    return tuple(
        value.get(key)
        for key in (
            "Policy", "LeadTimeScenario", "fill_rate", "average_inventory",
            "stockout_days", "replenishment_count", "replenishment_quantity",
            "unfulfilled_observed_demand", "result_class", "pareto_status",
        )
    )
