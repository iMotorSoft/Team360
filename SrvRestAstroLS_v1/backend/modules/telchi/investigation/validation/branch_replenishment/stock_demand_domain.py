"""Pure, auditable logic for Telchi daily stock and demand reconstruction.

The module intentionally has no SAP or filesystem dependency.  HANA extraction is
kept in ``daily_stock_demand_v1.py``; these functions are the executable
contract used by unit tests and by the real runner.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable, Mapping


CATEGORY_BY_TRANSTYPE = {
    13: "SALES", 15: "SALES",
    14: "RETURNS", 16: "RETURNS",
    67: "TRANSFER",
    59: "PRODUCTION_IN", 60: "PRODUCTION_CONSUMPTION",
    18: "PURCHASE_IN", 20: "PURCHASE_IN",
    19: "PURCHASE_RETURN", 21: "PURCHASE_RETURN",
    162: "INVENTORY_ADJUSTMENT",
}


def movement_category(trans_type: int | str | None) -> str:
    return CATEGORY_BY_TRANSTYPE.get(int(trans_type), "OTHER")


def net_movement(row: Mapping[str, Any]) -> float:
    return float(row.get("in_qty") or 0) - float(row.get("out_qty") or 0)


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def reconstruct_inverse(
    current_on_hand: float,
    daily_net: Mapping[date, float],
    start: date,
    end: date,
) -> dict[date, float]:
    """Reconstruct end-of-day stock from the current balance, without zero seed.

    For day ``d`` this is ``current - sum(net movement after d)``.  The current
    balance is an anchor, not a historical value, and the returned series is
    continuous even when there is no movement on a day.
    """
    days = date_range(start, end)
    future = 0.0
    out: dict[date, float] = {}
    # Walk backward: stock at d = current - movements strictly after d.
    for day in reversed(days):
        out[day] = float(current_on_hand) - future
        future += float(daily_net.get(day, 0.0))
    return out


def reconstruct_forward(
    opening_stock: float,
    daily_net: Mapping[date, float],
    start: date,
    end: date,
) -> dict[date, float]:
    stock = float(opening_stock)
    out: dict[date, float] = {}
    for day in date_range(start, end):
        stock += float(daily_net.get(day, 0.0))
        out[day] = stock
    return out


def validate_continuity(stock: Mapping[date, float], daily_net: Mapping[date, float], tolerance: float = 1e-6) -> dict[str, Any]:
    days = sorted(stock)
    gaps = sum((b - a).days != 1 for a, b in zip(days, days[1:]))
    violations = []
    for previous, current in zip(days, days[1:]):
        expected = stock[previous] + float(daily_net.get(current, 0.0))
        if abs(float(stock[current]) - expected) > tolerance:
            violations.append({"date": current.isoformat(), "expected": expected, "actual": stock[current]})
    return {"days": len(days), "gaps": gaps, "movement_violations": violations, "pass": not gaps and not violations}


def reconcile_latest(reconstructed: Mapping[tuple[str, str], Mapping[date, float]], current: Mapping[tuple[str, str], float], tolerance: float = 1e-6) -> dict[str, Any]:
    exact = 0
    differences = []
    for key, onhand in current.items():
        series = reconstructed.get(key)
        if not series:
            differences.append({"item_code": key[0], "warehouse": key[1], "reason": "NO_HISTORY_SERIES", "current": onhand})
            continue
        latest = series[max(series)]
        diff = float(latest) - float(onhand)
        if abs(diff) <= tolerance:
            exact += 1
        else:
            differences.append({"item_code": key[0], "warehouse": key[1], "latest": latest, "current": onhand, "difference": diff})
    total = len(current)
    unknown = sum(1 for difference in differences if difference.get("reason") == "NO_HISTORY_SERIES")
    return {
        "total_combinations": total,
        "exact": exact,
        "differences": len(differences),
        "unknown": unknown,
        "exact_pct": (100.0 * exact / total) if total else 0.0,
        "max_abs_difference": max((abs(float(x.get("difference", 0))) for x in differences), default=0.0),
        "difference_samples": differences[:25],
        "tolerance": tolerance,
        "pass": not differences,
    }


def availability_state(stock: float | None, low_threshold: float | None = None, tolerance: float = 1e-6) -> str:
    if stock is None:
        return "UNKNOWN"
    if stock < -tolerance:
        return "NEGATIVE_STOCK"
    if abs(stock) <= tolerance:
        return "ZERO_STOCK"
    if low_threshold is None:
        return "PENDING_POLICY_THRESHOLD"
    return "LOW_STOCK" if stock <= low_threshold else "IN_STOCK"


def demand_row(gross_sales: float = 0.0, returns: float = 0.0, **extra: Any) -> dict[str, Any]:
    return {
        "GROSS_SALES_QTY": float(gross_sales),
        "RETURNS_QTY": float(returns),
        "NET_SALES_QTY": float(gross_sales) - float(returns),
        **extra,
    }


def trailing_mean(values_by_date: Mapping[date, float], as_of: date, window_days: int = 30) -> float | None:
    """Mean over [as_of-window, as_of), explicitly excluding as_of and future."""
    values = [float(v) for d, v in values_by_date.items() if as_of - timedelta(days=window_days) <= d < as_of]
    return (sum(values) / len(values)) if values else None


def days_of_supply(stock: float, demand_by_date: Mapping[date, float], as_of: date, window_days: int = 30) -> dict[str, Any]:
    avg = trailing_mean(demand_by_date, as_of, window_days)
    if avg is None:
        return {"value": None, "status": "INSUFFICIENT_HISTORY"}
    if avg <= 0:
        return {"value": None, "status": "ZERO_HISTORICAL_DEMAND"}
    return {"value": float(stock) / avg, "status": "KNOWN"}


def classify_censoring(stock: float | None, sales: float, has_pre_sales: bool, has_post_sales: bool, has_replenishment: bool) -> str:
    if stock is None:
        return "UNKNOWN"
    if stock > 0:
        return "NO_CENSORING_EVIDENCE"
    if sales != 0:
        return "NO_CENSORING_EVIDENCE"
    if has_pre_sales and has_post_sales and has_replenishment:
        return "POSSIBLE_CENSORED_DEMAND"
    return "UNPROVEN_CENSORED_DEMAND"


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * p
    lo, hi = int(rank), min(int(rank) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (rank - lo)


def summarize_values(values: Iterable[float]) -> dict[str, Any]:
    vals = [float(v) for v in values]
    return {
        "count": len(vals),
        "sum": sum(vals),
        "mean": (sum(vals) / len(vals)) if vals else None,
        "median": median(vals) if vals else None,
        "p25": _percentile(vals, 0.25), "p75": _percentile(vals, 0.75),
        "p90": _percentile(vals, 0.90), "max": max(vals) if vals else None,
    }


def replenishment_intervals(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    # Domain tests use ``date``; SAP-derived event rows use ``Date``.
    dates = sorted({e.get("date", e.get("Date")) for e in events})
    dates = [d for d in dates if d is not None]
    intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
    return {"event_dates": len(dates), "days_between_replenishments": summarize_values(intervals)}


def build_stockout_episodes(daily_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build episodes from consecutive ZERO/NEGATIVE branch-stock days.

    ``daily_rows`` must be sorted or is sorted here by item, branch, day.  The
    confidence is deliberately conservative: no lost-sales amount is imputed.
    """
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        groups[(str(row["ItemCode"]), str(row["Branch"]))].append(row)
    episodes = []
    for (item, branch), rows in groups.items():
        rows.sort(key=lambda r: r["Date"])
        current: list[Mapping[str, Any]] = []
        for row in rows + [{"Date": None, "availability_state": "SENTINEL"}]:
            is_stockout = row.get("availability_state") in {"ZERO_STOCK", "NEGATIVE_STOCK"}
            contiguous = bool(current) and row["Date"] == current[-1]["Date"] + timedelta(days=1)
            if is_stockout and (not current or contiguous):
                current.append(row)
                continue
            if current:
                before = [r for r in rows if r["Date"] < current[0]["Date"]]
                after = [r for r in rows if r["Date"] > current[-1]["Date"]]
                pre30 = sum(float(r.get("NET_SALES_QTY", 0) or 0) for r in before[-30:])
                post30 = sum(float(r.get("NET_SALES_QTY", 0) or 0) for r in after[:30])
                pre_sales = any(float(r.get("NET_SALES_QTY", 0) or 0) > 0 for r in before[-30:])
                post_sales = any(float(r.get("NET_SALES_QTY", 0) or 0) > 0 for r in after[:30])
                replenishment = next((r for r in after if float(r.get("TRANSFER_IN_QTY", 0) or 0) > 0), None)
                confidence = "STRONG" if pre_sales and post_sales and replenishment else "WEAK" if pre_sales or post_sales else "UNKNOWN"
                episodes.append({
                    "Branch": branch, "ItemCode": item,
                    "StartDate": current[0]["Date"], "EndDate": current[-1]["Date"],
                    "DurationDays": (current[-1]["Date"] - current[0]["Date"]).days + 1,
                    "StockBefore": before[-1].get("StockEndOfDay") if before else None,
                    "LastSaleBefore": next((r["Date"] for r in reversed(before) if float(r.get("NET_SALES_QTY", 0) or 0) > 0), None),
                    "ReplenishmentDate": replenishment.get("Date") if replenishment else None,
                    "ReplenishmentQty": replenishment.get("TRANSFER_IN_QTY", 0) if replenishment else 0,
                    "FirstSaleAfter": next((r["Date"] for r in after if float(r.get("NET_SALES_QTY", 0) or 0) > 0), None),
                    "PreDemand30d": pre30, "PostDemand30d": post30,
                    "Confidence": confidence,
                    "DemandClassification": "POSSIBLE_CENSORED_DEMAND" if confidence in {"STRONG", "WEAK"} and replenishment else "UNPROVEN_CENSORED_DEMAND",
                })
                current = []
            if is_stockout:
                current = [row]
    return episodes


def insufficient_history(observation_days: int, minimum_days: int = 90) -> str:
    return "NEW_PRODUCT" if observation_days <= 30 else "INSUFFICIENT_HISTORY" if observation_days < minimum_days else "SUFFICIENT_HISTORY"
