"""Current replenishment policy baseline for TELCHI (investigation, read-only).

This module consumes the already reconciled daily stock projection and transfer
ledger.  It deliberately describes observed behaviour; it does not recommend
ROP, min/max, safety stock, or any other target policy.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable, Mapping


POLICY_CLASSES = (
    "MIN_MAX_LIKE", "REORDER_POINT_LIKE", "PERIODIC", "FIXED_QTY",
    "DEMAND_TRIGGERED", "PUSH_FROM_CENTRAL", "REACTIVE_TO_STOCKOUT",
    "MANUAL_IRREGULAR", "INSUFFICIENT_EVENTS", "NO_CLEAR_POLICY",
)
STOCKOUT_CONTEXTS = (
    "BEFORE_STOCKOUT", "AT_STOCKOUT", "AFTER_STOCKOUT",
    "NO_STOCKOUT_CONTEXT", "UNKNOWN",
)


def _f(value: Any) -> float:
    return float(value or 0)


def _d(value: Any) -> date:
    if isinstance(value, datetime):  # type: ignore[name-defined]
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _percentile(values: Iterable[float], p: float) -> float | None:
    values = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (rank - lo)


def summarize(values: Iterable[float]) -> dict[str, Any]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    mean = sum(vals) / len(vals) if vals else None
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) if vals and mean is not None else None
    return {
        "count": len(vals), "sum": sum(vals), "mean": mean,
        "median": median(vals) if vals else None,
        "p25": _percentile(vals, .25), "p75": _percentile(vals, .75),
        "p90": _percentile(vals, .90), "max": max(vals) if vals else None,
        "cv": (std / abs(mean)) if std is not None and mean not in (None, 0) else None,
    }


def _value(row: Any, field: str) -> Any:
    """Read either the JSON mapping shape or the compact (stock,demand,net) shape."""
    if isinstance(row, Mapping):
        return row.get(field)
    return {"StockEndOfDay": row[0], "NET_SALES_QTY": row[1], "OBSERVED_DEMAND": row[1], "NET_MOVEMENT_QTY": row[2]}.get(field)


def _history(rows: Mapping[date, Any], event_date: date, window: int) -> list[Any]:
    """Return only the complete preceding calendar window (never event/future)."""
    return [rows[d] for d in (event_date - timedelta(days=i) for i in range(window, 0, -1)) if d in rows]


def demand_coverage_before(rows: Mapping[date, Any], event_date: date) -> dict[str, Any]:
    """Calculate 7/30/60/90-day demand and DOS using data before the event."""
    result: dict[str, Any] = {}
    for window in (7, 30, 60, 90):
        history = _history(rows, event_date, window)
        values = [_f(_value(row, "NET_SALES_QTY") if _value(row, "NET_SALES_QTY") is not None else _value(row, "OBSERVED_DEMAND")) for row in history]
        positive_days = sum(value > 0 for value in values)
        result[f"SALES_{window}D_BEFORE"] = sum(values)
        key = f"{window}d"
        if not history or len(history) < window:
            result[f"AVG_DEMAND_{window}D"] = None
            result[f"DAYS_OF_SUPPLY_{window}D"] = None
            result[f"DEMAND_STATUS_{window}D"] = "INSUFFICIENT_HISTORY"
        elif sum(values) <= 0:
            result[f"AVG_DEMAND_{window}D"] = 0.0
            result[f"DAYS_OF_SUPPLY_{window}D"] = None
            result[f"DEMAND_STATUS_{window}D"] = "NO_DEMAND"
        else:
            average = sum(values) / window
            result[f"AVG_DEMAND_{window}D"] = average
            result[f"DAYS_OF_SUPPLY_{window}D"] = None  # stock is supplied by the caller
            result[f"DEMAND_STATUS_{window}D"] = "INTERMITTENT" if positive_days / window <= .25 else "SUFFICIENT_HISTORY"
        result.setdefault("DEMAND_POSITIVE_DAYS_90D", positive_days if window == 90 else None)
    # 30 days is the descriptive recent-demand denominator used by this gate.
    result["DAYS_OF_SUPPLY_BEFORE"] = result["DAYS_OF_SUPPLY_30D"]
    result["AVG_DEMAND_BEFORE"] = result["AVG_DEMAND_30D"]
    return result


def _episode_context(item: str, branch: str, event_date: date, episodes: Mapping[tuple[str, str], list[Mapping[str, Any]]]) -> tuple[str, int | None]:
    relevant = episodes.get((item, branch), [])
    for episode in relevant:
        start, end = _d(episode["StartDate"]), _d(episode["EndDate"])
        if start <= event_date <= end:
            return "AT_STOCKOUT", (event_date - start).days
        if event_date < start:
            return "BEFORE_STOCKOUT", (start - event_date).days
    previous = [_d(e["EndDate"]) for e in relevant if _d(e["EndDate"]) < event_date]
    if previous:
        return "AFTER_STOCKOUT", (event_date - max(previous)).days
    return "NO_STOCKOUT_CONTEXT", None


def enrich_replenishment_events(
    stock_rows: Iterable[Mapping[str, Any]],
    replenishment_events: Iterable[Mapping[str, Any]],
    episodes: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Add pre-event stock, demand, DOS, timing and stockout context.

    Stock rows are end-of-day.  Therefore same-day movement is explicitly
    retained as ``CONCURRENT_NET_MOVEMENT`` and sequence remains UNKNOWN.
    """
    if isinstance(stock_rows, Mapping):
        stock = stock_rows
    else:
        stock = defaultdict(dict)
        for row in stock_rows:
            item, branch, day = str(row["ItemCode"]), str(row["Branch"]), _d(row["Date"])
            stock[(item, branch)][day] = row
    episode_map: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for episode in episodes:
        episode_map[(str(episode["ItemCode"]), str(episode["Branch"]))].append(episode)
    ordered = sorted((dict(event) for event in replenishment_events), key=lambda e: (str(e["ItemCode"]), str(e["Branch"]), _d(e["Date"]), int(e.get("DocEntry") or 0), int(e.get("LineNum") or 0)))
    previous: dict[tuple[str, str], date] = {}
    enriched: list[dict[str, Any]] = []
    for event in ordered:
        item, branch, day = str(event["ItemCode"]), str(event["Branch"]), _d(event["Date"])
        daily = stock.get((item, branch), {})
        before_row = daily.get(day - timedelta(days=1))
        day_row = daily.get(day)
        before = _f(_value(before_row, "StockEndOfDay")) if before_row is not None else None
        qty = _f(event.get("ReplenishmentQty"))
        same_day_net = _f(_value(day_row, "NET_MOVEMENT_QTY")) if day_row is not None else None
        concurrent = same_day_net - qty if same_day_net is not None else None
        after = before + qty + concurrent if before is not None and concurrent is not None else None
        coverage = demand_coverage_before(daily, day)
        for window in (7, 30, 60, 90):
            average = coverage[f"AVG_DEMAND_{window}D"]
            coverage[f"DAYS_OF_SUPPLY_{window}D"] = before / average if before is not None and average and average > 0 else None
        stockout_context, stockout_days = _episode_context(item, branch, day, episode_map)
        prior = previous.get((item, branch))
        enriched.append({
            **event,
            "Date": day,
            "STOCK_BEFORE": before,
            "REPLENISHMENT_QTY": qty,
            "STOCK_AFTER": after,
            "CONCURRENT_NET_MOVEMENT": concurrent,
            "INTRADAY_SEQUENCE": "UNKNOWN",
            "STOCK_BEFORE_STATUS": "KNOWN" if before is not None else "UNKNOWN",
            "DAYS_SINCE_PREVIOUS_REPLENISHMENT": (day - prior).days if prior else None,
            "STOCKOUT_CONTEXT": stockout_context,
            "DAYS_FROM_STOCKOUT_START": stockout_days,
            "STOCKOUT_PREVIOUS": stockout_context == "AFTER_STOCKOUT",
            "REPLENISHMENT_QTY_OVER_RECENT_DEMAND_30D": (qty / coverage["AVG_DEMAND_30D"]) if coverage["AVG_DEMAND_30D"] else None,
            "REPLENISHMENT_QTY_OVER_RECENT_DEMAND": (qty / coverage["AVG_DEMAND_30D"]) if coverage["AVG_DEMAND_30D"] else None,
            **coverage,
        })
        # The interval is between observed event records, including same-day 0d.
        previous[(item, branch)] = day
    return enriched


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["ItemCode"]), str(row["Branch"])


def _cv(values: list[float]) -> float | None:
    stats = summarize(values)
    return stats["cv"]


def derive_policy_thresholds(group_metrics: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Use observed population distributions instead of fixed business cutoffs."""
    groups = list(group_metrics)
    def population(field: str) -> list[float]:
        return [float(g[field]) for g in groups if g.get(field) is not None and math.isfinite(float(g[field]))]
    medians = {field: median(population(field)) for field in ("interval_cv", "qty_cv", "trigger_cv") if population(field)}
    p75 = {f"{field}_p75": (_percentile(population(field), .75) or 0.0) for field in ("interval_cv", "qty_cv", "trigger_cv")}
    correlations = population("qty_demand_correlation")
    if correlations:
        p75["qty_demand_correlation_p75"] = _percentile(correlations, .75) or 0.0
    return {**medians, **p75}


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    den = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    return sum(x * y for x, y in zip(dx, dy)) / den if den else None


def classify_observed_policy(metrics: Mapping[str, Any], thresholds: Mapping[str, float]) -> tuple[str, str]:
    """Classify only repeatable signals; precedence is explicit and auditable."""
    n = int(metrics.get("replenishment_count") or 0)
    if n < 2:
        return "INSUFFICIENT_EVENTS", "LOW"
    interval_cv, qty_cv, trigger_cv = metrics.get("interval_cv"), metrics.get("qty_cv"), metrics.get("trigger_cv")
    interval_limit = thresholds.get("interval_cv", float("inf"))
    qty_limit = thresholds.get("qty_cv", float("inf"))
    trigger_limit = thresholds.get("trigger_cv", float("inf"))
    p75_interval = thresholds.get("interval_cv_p75", interval_limit)
    p75_qty = thresholds.get("qty_cv_p75", qty_limit)
    p75_trigger = thresholds.get("trigger_cv_p75", trigger_limit)
    reactive_rate = metrics.get("pct_replenishment_at_or_after_stockout", 0)
    if reactive_rate > 0 and reactive_rate >= metrics.get("reactive_population_threshold", 1.0):
        return "REACTIVE_TO_STOCKOUT", "HIGH" if n >= 5 else "MEDIUM"
    source = str(metrics.get("dominant_source_type") or "")
    if source == "TRANSFER_FROM_CENTRAL" and metrics.get("dominant_source_share", 0) >= .5:
        return "PUSH_FROM_CENTRAL", "HIGH" if n >= 5 else "MEDIUM"
    signals = sum(value is not None and value <= limit for value, limit in ((qty_cv, qty_limit), (interval_cv, interval_limit), (trigger_cv, trigger_limit)))
    if qty_cv is not None and trigger_cv is not None and qty_cv <= qty_limit and trigger_cv <= trigger_limit:
        return "MIN_MAX_LIKE", "HIGH" if n >= 5 else "MEDIUM"
    if qty_cv is not None and qty_cv <= qty_limit:
        return "FIXED_QTY", "HIGH" if signals >= 2 and n >= 5 else "MEDIUM"
    if trigger_cv is not None and trigger_cv <= trigger_limit:
        return "REORDER_POINT_LIKE", "HIGH" if n >= 5 else "MEDIUM"
    if interval_cv is not None and interval_cv <= interval_limit:
        return "PERIODIC", "HIGH" if n >= 5 else "MEDIUM"
    correlation = metrics.get("qty_demand_correlation")
    if correlation is not None and correlation >= thresholds.get("qty_demand_correlation_p75", 1.0):
        return "DEMAND_TRIGGERED", "MEDIUM" if n >= 3 else "LOW"
    if all(value is not None and value >= limit for value, limit in ((qty_cv, p75_qty), (interval_cv, p75_interval), (trigger_cv, p75_trigger))):
        return "MANUAL_IRREGULAR", "MEDIUM" if n >= 5 else "LOW"
    return "NO_CLEAR_POLICY", "LOW"


def _event_group_metrics(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    intervals = [_f(e["DAYS_SINCE_PREVIOUS_REPLENISHMENT"]) for e in events if e.get("DAYS_SINCE_PREVIOUS_REPLENISHMENT") is not None]
    quantities = [_f(e["REPLENISHMENT_QTY"]) for e in events]
    triggers = [_f(e["STOCK_BEFORE"]) for e in events if e.get("STOCK_BEFORE") is not None]
    doses = [_f(e["DAYS_OF_SUPPLY_30D"]) for e in events if e.get("DAYS_OF_SUPPLY_30D") is not None]
    trigger_values = triggers or doses
    source_counts: dict[str, int] = defaultdict(int)
    for event in events:
        source_counts[str(event.get("SourceType") or "UNKNOWN")] += 1
    dominant = max(source_counts, key=source_counts.get) if source_counts else None
    demand_pairs = [(e["REPLENISHMENT_QTY"], e.get("AVG_DEMAND_30D")) for e in events if e.get("AVG_DEMAND_30D") is not None]
    at_after = sum(e.get("STOCKOUT_CONTEXT") in {"AT_STOCKOUT", "AFTER_STOCKOUT"} for e in events)
    metrics = {
        "replenishment_count": len(events),
        "replenishment_qty_total": sum(quantities),
        "replenishment_qty_mean": summarize(quantities)["mean"],
        "replenishment_qty_median": summarize(quantities)["median"],
        "replenishment_qty_p25": summarize(quantities)["p25"],
        "replenishment_qty_p75": summarize(quantities)["p75"],
        "replenishment_qty_p90": summarize(quantities)["p90"],
        "replenishment_qty_max": summarize(quantities)["max"],
        "replenishment_qty_cv": _cv(quantities),
        "replenishment_interval_mean": summarize(intervals)["mean"],
        "replenishment_interval_median": summarize(intervals)["median"],
        "replenishment_interval_p25": summarize(intervals)["p25"],
        "replenishment_interval_p75": summarize(intervals)["p75"],
        "replenishment_interval_p90": summarize(intervals)["p90"],
        "replenishment_interval_max": summarize(intervals)["max"],
        "replenishment_interval_cv": _cv(intervals),
        "stock_before_mean": summarize(triggers)["mean"],
        "stock_before_median": summarize(triggers)["median"],
        "stock_before_cv": _cv(triggers),
        "days_supply_before_mean": summarize(doses)["mean"],
        "days_supply_before_median": summarize(doses)["median"],
        "days_supply_before_cv": _cv(doses),
        "pct_replenishment_before_stockout": sum(e.get("STOCKOUT_CONTEXT") == "BEFORE_STOCKOUT" for e in events) / len(events) if events else 0,
        "pct_replenishment_at_or_after_stockout": at_after / len(events) if events else 0,
        "stockout_context_counts": {context: sum(e.get("STOCKOUT_CONTEXT") == context for e in events) for context in STOCKOUT_CONTEXTS},
        "source_counts": dict(source_counts), "dominant_source_type": dominant,
        "dominant_source_share": source_counts[dominant] / len(events) if dominant else 0,
        "qty_demand_correlation": _correlation([_f(x[0]) for x in demand_pairs], [_f(x[1]) for x in demand_pairs]),
    }
    metrics["trigger_cv"] = metrics["stock_before_cv"] if triggers else metrics["days_supply_before_cv"]
    metrics["interval_cv"] = metrics["replenishment_interval_cv"]
    metrics["qty_cv"] = metrics["replenishment_qty_cv"]
    return metrics


def build_item_branch_baseline(events: Iterable[Mapping[str, Any]], all_keys: Iterable[tuple[str, str]] = ()) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[_key(event)].append(event)
    for key in all_keys:
        grouped.setdefault((str(key[0]), str(key[1])), [])
    raw = [{**_event_group_metrics(value), "ItemCode": key[0], "Branch": key[1]} for key, value in sorted(grouped.items())]
    thresholds = derive_policy_thresholds(raw)
    # Reactive threshold is also population-derived: the upper quartile of the
    # observed at/after-stockout rate, with no fabricated commercial threshold.
    reactive_values = [float(r["pct_replenishment_at_or_after_stockout"]) for r in raw]
    reactive_limit = _percentile(reactive_values, .75) if reactive_values else 1.0
    result = []
    for metrics in raw:
        metrics["reactive_population_threshold"] = reactive_limit if reactive_limit is not None else 1.0
        policy, confidence = classify_observed_policy(metrics, thresholds)
        metrics["policy_class"], metrics["policy_confidence"] = policy, confidence
        result.append(metrics)
    return result, {"thresholds": thresholds, "reactive_population_threshold": reactive_limit, "pairs": len(result)}


def branch_summary(item_branch: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in item_branch:
        groups[str(row["Branch"])].append(row)
    out = []
    for branch, rows in sorted(groups.items()):
        out.append({
            "Branch": branch,
            "active_products": len({str(r["ItemCode"]) for r in rows}),
            "products_replenished": sum(r["replenishment_count"] > 0 for r in rows),
            "events": sum(int(r["replenishment_count"]) for r in rows),
            "qty_total": sum(_f(r["replenishment_qty_total"]) for r in rows),
            "frequency_mean_days": (sum(_f(r["replenishment_interval_mean"]) for r in rows if r.get("replenishment_interval_mean") is not None) / sum(r.get("replenishment_interval_mean") is not None for r in rows)) if any(r.get("replenishment_interval_mean") is not None for r in rows) else None,
            "pct_reactive": sum(r["policy_class"] == "REACTIVE_TO_STOCKOUT" for r in rows) / len(rows) if rows else 0,
            "transfers_from_central": sum(_f(r.get("source_counts", {}).get("TRANSFER_FROM_CENTRAL")) for r in rows),
            "transfers_from_branch": sum(_f(r.get("source_counts", {}).get("TRANSFER_FROM_BRANCH")) for r in rows),
            "irregular_products": sum(r["policy_class"] == "MANUAL_IRREGULAR" for r in rows),
            "products_without_detectable_policy": sum(r["policy_class"] in {"NO_CLEAR_POLICY", "INSUFFICIENT_EVENTS"} for r in rows),
        })
    return out


def rankings(item_branch: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows = list(item_branch)
    def top(sort_key: str, reverse: bool = True) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda r: (_f(r.get(sort_key)), str(r.get("ItemCode"))), reverse=reverse)[:20]
    return {
        "TOP_REACTIVE_REPLENISHMENT": sorted(rows, key=lambda r: _f(r.get("pct_replenishment_at_or_after_stockout")), reverse=True)[:20],
        "TOP_IRREGULAR": [r for r in rows if r.get("policy_class") == "MANUAL_IRREGULAR"][:20],
        "TOP_FREQUENT_REPLENISHMENT": top("replenishment_count"),
        "TOP_LARGE_REPLENISHMENT": top("replenishment_qty_mean"),
        "TOP_LONG_INTERVAL": top("replenishment_interval_mean"),
        "TOP_POST_STOCKOUT_REPLENISHMENT": sorted(rows, key=lambda r: _f(r.get("pct_replenishment_at_or_after_stockout")), reverse=True)[:20],
        "TOP_MULTI_SOURCE": sorted(rows, key=lambda r: len(r.get("source_counts", {})), reverse=True)[:20],
    }


def trace_real_cases(events: Iterable[Mapping[str, Any]], item_branch: Iterable[Mapping[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    """Select deterministic, materially different traces for human review."""
    all_events = list(events)
    metrics = {(str(row["ItemCode"]), str(row["Branch"])): row for row in item_branch}
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for event in all_events:
        grouped[_key(event)].append(event)
    for values in grouped.values():
        values.sort(key=lambda e: (_d(e["Date"]), int(e.get("DocEntry") or 0), int(e.get("LineNum") or 0)))
    candidates: list[Mapping[str, Any]] = []
    selectors = (
        lambda e: _f(e.get("AVG_DEMAND_30D")),
        lambda e: -_f(e.get("AVG_DEMAND_30D")),
        lambda e: 1 if e.get("STOCKOUT_CONTEXT") == "AT_STOCKOUT" else 0,
        lambda e: 1 if e.get("STOCKOUT_CONTEXT") == "AFTER_STOCKOUT" else 0,
        lambda e: _f(e.get("REPLENISHMENT_QTY")),
        lambda e: _f(e.get("DAYS_SINCE_PREVIOUS_REPLENISHMENT")),
    )
    for selector in selectors:
        candidates.append(max(all_events, key=selector) if all_events else {})
    for policy in ("FIXED_QTY", "MIN_MAX_LIKE", "PERIODIC", "MANUAL_IRREGULAR", "REACTIVE_TO_STOCKOUT", "DEMAND_TRIGGERED"):
        pairs = [key for key, row in metrics.items() if row.get("policy_class") == policy]
        if pairs:
            candidates.append(grouped[pairs[0]][0])
    for key in sorted(grouped):
        if grouped[key]:
            candidates.append(grouped[key][0])
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for event in candidates:
        if not event:
            continue
        identity = (event.get("ItemCode"), event.get("Branch"), event.get("Date"), event.get("DocEntry"), event.get("LineNum"))
        if identity in seen:
            continue
        seen.add(identity)
        key = _key(event)
        later = [e for e in grouped[key] if _d(e["Date"]) > _d(event["Date"])]
        selected.append({"fecha": event.get("Date"), "item_code": key[0], "branch": key[1], "stock_before": event.get("STOCK_BEFORE"), "ventas_7d_previas": event.get("Sales7dBefore", event.get("SALES_7D_BEFORE")), "ventas_30d_previas": event.get("Sales30dBefore", event.get("SALES_30D_BEFORE")), "replenishment_qty": event.get("REPLENISHMENT_QTY"), "source": event.get("SourceType"), "stock_after": event.get("STOCK_AFTER"), "stockout_context": event.get("STOCKOUT_CONTEXT"), "next_replenishment": later[0].get("Date") if later else None, "intraday_sequence": event.get("INTRADAY_SEQUENCE", "UNKNOWN")})
        if len(selected) >= limit:
            break
    return selected


def build_current_policy_baseline(
    stock_rows: Iterable[Mapping[str, Any]],
    replenishment_events: Iterable[Mapping[str, Any]],
    episodes: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    if isinstance(stock_rows, Mapping):
        stock_source = stock_rows
        all_keys = stock_rows.keys()
    else:
        stock_source = list(stock_rows)
        all_keys = {_key(row) for row in stock_source}
    enriched = enrich_replenishment_events(stock_source, replenishment_events, episodes)
    item_branch, classification = build_item_branch_baseline(enriched, all_keys)
    return {
        "events": enriched,
        "item_branch": item_branch,
        "branch": branch_summary(item_branch),
        "rankings": rankings(item_branch),
        "real_cases": trace_real_cases(enriched, item_branch, limit=15),
        "classification": classification,
        "event_count": len(enriched),
        "item_branch_count": len(item_branch),
        "verdict": "DEGRADED",
    }


# Avoid importing datetime in the hot path; _d only needs it for DB adapters.
from datetime import datetime  # noqa: E402
