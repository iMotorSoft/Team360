"""TELCHI Financial Forecast / Liquidity / Scenarios V1 — pure domain logic.

Investigation-only, deterministic, SELECT-free module.  It contains the
auditable rules used by ``financial_forecast_liquidity_scenarios_v1.py``:

  * percentile / distribution summaries computed from a *delay histogram*
    (``{delay_days: count}``) so the runner can aggregate in HANA and never
    download millions of rows;
  * forward and overdue aging buckets;
  * expected collection / payment dates from empirical delay histograms;
  * survivorship-adjusted recovery curves for overdue AR / AP;
  * scenario parameter contracts;
  * direct cash-flow waterfalls, minimum treasury, first deficit and funding
    need;
  * backtest error metrics and deterministic model selection.

The module never calls SAP.  It preserves the separation required by the gate:
``CONTRACTUAL`` (document dates) / ``EXPECTED`` (behaviour-adjusted) /
``FORECAST`` (combined) / ``SCENARIO`` (deliberate assumption changes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

# ---------------------------------------------------------------------------
# Aging buckets
# ---------------------------------------------------------------------------
FORWARD_BUCKETS = ["OVERDUE", "0-7", "8-15", "16-30", "31-60", "61-90", ">90"]
OVERDUE_BUCKETS = ["1-30", "31-60", "61-90", "91-180", ">180"]

#: Minimum observations before a customer / supplier specific rule is trusted.
MIN_ENTITY_OBSERVATIONS = 5
#: Forecast horizons in days required by the gate.
HORIZONS = (7, 15, 30, 60, 90)
#: Long horizons included when materiality allows.
WEEKLY_HORIZONS = tuple(range(7, 91, 7))

CURRENCIES = ("BS", "USD")


# ---------------------------------------------------------------------------
# Distribution helpers (histograms)
# ---------------------------------------------------------------------------
def _sorted_items(hist: Mapping[Any, float]) -> list[tuple[float, float]]:
    items = [(float(k), float(v)) for k, v in hist.items() if v]
    items.sort(key=lambda pair: pair[0])
    return items


def histogram_total(hist: Mapping[Any, float]) -> float:
    return float(sum(v for _, v in _sorted_items(hist)))


def quantile_from_histogram(hist: Mapping[Any, float], p: float) -> float | None:
    """Nearest-rank quantile of a histogram (no raw rows required)."""
    items = _sorted_items(hist)
    total = sum(c for _, c in items)
    if total <= 0:
        return None
    target = p * total
    cumulative = 0.0
    for value, count in items:
        cumulative += count
        if cumulative >= target:
            return value
    return items[-1][0]


def mean_from_histogram(hist: Mapping[Any, float]) -> float | None:
    items = _sorted_items(hist)
    total = sum(c for _, c in items)
    if total <= 0:
        return None
    return sum(value * count for value, count in items) / total


def distribution_stats(hist: Mapping[Any, float], ps: Iterable[float] = (0.25, 0.5, 0.75, 0.9)) -> dict[str, Any]:
    """Return a serialisable summary of a (possibly amount-weighted) histogram."""
    return {
        "weighted_total": round(histogram_total(hist), 2),
        "mean": mean_from_histogram(hist),
        "percentiles": {f"p{int(p * 100)}": quantile_from_histogram(hist, p) for p in ps},
    }


def delay_bucket_shares(hist: Mapping[Any, float]) -> dict[str, float]:
    """Share of observations by payment/collection timing relative to due date."""
    total = histogram_total(hist)
    buckets = {
        "BEFORE_DUE": 0.0,
        "ON_DUE": 0.0,
        "1_7_LATE": 0.0,
        "8_30_LATE": 0.0,
        "31_60_LATE": 0.0,
        "OVER_60_LATE": 0.0,
    }
    if total <= 0:
        return buckets
    for value, count in _sorted_items(hist):
        if value < 0:
            buckets["BEFORE_DUE"] += count
        elif value == 0:
            buckets["ON_DUE"] += count
        elif value <= 7:
            buckets["1_7_LATE"] += count
        elif value <= 30:
            buckets["8_30_LATE"] += count
        elif value <= 60:
            buckets["31_60_LATE"] += count
        else:
            buckets["OVER_60_LATE"] += count
    return {key: round(100.0 * value / total, 4) for key, value in buckets.items()}


# ---------------------------------------------------------------------------
# Aging
# ---------------------------------------------------------------------------
def forward_bucket(due: date, as_of: date) -> str:
    """Bucket an open document by its contractual due date relative to as-of."""
    if due < as_of:
        return "OVERDUE"
    days = (due - as_of).days
    if days <= 7:
        return "0-7"
    if days <= 15:
        return "8-15"
    if days <= 30:
        return "16-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return ">90"


def overdue_bucket(days_overdue: int) -> str:
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    if days_overdue <= 180:
        return "91-180"
    return ">180"


# ---------------------------------------------------------------------------
# Conditional wait (used for documents already overdue at the cutoff)
# ---------------------------------------------------------------------------
def conditional_quantile(hist: Mapping[Any, float], x: float, p: float) -> float | None:
    """Quantile of ``(delay - x)`` restricted to observations with ``delay > x``."""
    items = [(value, count) for value, count in _sorted_items(hist) if value > x]
    if not items:
        return None
    return quantile_from_histogram({value - x: count for value, count in items}, p)


def conditional_recovery(curve: Mapping[int, float], x: float, horizon: int) -> float:
    """Probability of recovering within ``horizon`` given overdue by ``x`` days.

    ``curve`` maps an overdue age to the *cumulative* recovery probability
    observed on matured cohorts.  The conditional probability is
    ``(R(x+h) - R(x)) / (1 - R(x))`` and is bounded to ``[0, 1]``.
    """
    r0 = interpolate_recovery(curve, x)
    r1 = interpolate_recovery(curve, x + horizon)
    denominator = 1.0 - r0
    if denominator <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, (r1 - r0) / denominator))


def interpolate_recovery(curve: Mapping[int, float], x: float) -> float:
    points = sorted((float(k), float(v)) for k, v in curve.items())
    if not points:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


# ---------------------------------------------------------------------------
# Scenario contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioParameters:
    """Explicit, documented scenario assumptions.

    ``*_delay_percentile`` selects a percentile of the empirical delay
    histogram: higher means later (worse for collections, better for payments
    when delaying outflow).  ``overdue_recovery_factor`` scales the empirical
    conditional recovery probability (``<1`` more conservative).
    ``other_out_monthly`` is the going-concern operating outflow overlay.
    """

    name: str
    collection_delay_percentile: float
    payment_delay_percentile: float
    overdue_recovery_factor: float
    overdue_wait_percentile: float
    other_out_monthly: float
    other_in_monthly: float = 0.0
    fx_shock_pct: float = 0.0
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.name,
            "collection_delay_percentile": self.collection_delay_percentile,
            "payment_delay_percentile": self.payment_delay_percentile,
            "overdue_recovery_factor": self.overdue_recovery_factor,
            "overdue_wait_percentile": self.overdue_wait_percentile,
            "other_out_monthly": self.other_out_monthly,
            "other_in_monthly": self.other_in_monthly,
            "fx_shock_pct": self.fx_shock_pct,
            "description": self.description,
        }


def scenario_parameters(base_other_out: float, base_other_in: float = 0.0) -> dict[str, ScenarioParameters]:
    """Deterministic scenario grid derived from historical percentiles.

    The going-concern operating overlay is scaled by scenario: BASE uses the
    historical median, CONSERVATIVE/STRESS use the p75/p90 of the monthly
    operating outflow, UPSIDE uses p25.
    """
    return {
        "BASE": ScenarioParameters(
            name="BASE",
            collection_delay_percentile=0.50,
            payment_delay_percentile=0.50,
            overdue_recovery_factor=1.00,
            overdue_wait_percentile=0.50,
            other_out_monthly=base_other_out,
            other_in_monthly=base_other_in,
            description="Historic median collection and payment delay; empirical overdue recovery.",
        ),
        "CONSERVATIVE": ScenarioParameters(
            name="CONSERVATIVE",
            collection_delay_percentile=0.75,
            payment_delay_percentile=0.25,
            overdue_recovery_factor=0.60,
            overdue_wait_percentile=0.75,
            other_out_monthly=base_other_out * 1.25,
            other_in_monthly=base_other_in * 0.75,
            description="Collections at p75 delay, lower overdue recovery, payments accelerate to p25.",
        ),
        "UPSIDE": ScenarioParameters(
            name="UPSIDE",
            collection_delay_percentile=0.25,
            payment_delay_percentile=0.75,
            overdue_recovery_factor=1.00,
            overdue_wait_percentile=0.25,
            other_out_monthly=base_other_out * 0.75,
            other_in_monthly=base_other_in * 1.25,
            description="Collections near p25 delay, payments settle at p75 delay.",
        ),
        "STRESS_COLLECTION_DELAY": ScenarioParameters(
            name="STRESS_COLLECTION_DELAY",
            collection_delay_percentile=0.90,
            payment_delay_percentile=0.10,
            overdue_recovery_factor=0.30,
            overdue_wait_percentile=0.90,
            other_out_monthly=base_other_out * 1.50,
            other_in_monthly=base_other_in * 0.50,
            description="Top customers delay to p90, overdue recovery collapses, payments at contractual/p10.",
        ),
        "STRESS_SUPPLIER_ACCELERATION": ScenarioParameters(
            name="STRESS_SUPPLIER_ACCELERATION",
            collection_delay_percentile=0.50,
            payment_delay_percentile=0.05,
            overdue_recovery_factor=1.00,
            overdue_wait_percentile=0.50,
            other_out_monthly=base_other_out,
            other_in_monthly=base_other_in,
            description="Critical suppliers demand immediate payment (p05) while collections stay at median.",
        ),
    }


# ---------------------------------------------------------------------------
# Direct cash-flow waterfall
# ---------------------------------------------------------------------------
@dataclass
class CashEvent:
    day_offset: int
    currency: str
    amount: float  # signed: positive = inflow, negative = outflow
    source: str
    item: dict[str, Any] = field(default_factory=dict)


def daily_buckets(events: Iterable[CashEvent], horizon: int) -> list[dict[str, Any]]:
    """Aggregate signed events into daily buckets covering ``0..horizon``."""
    per_day: dict[int, list[CashEvent]] = {}
    for event in events:
        if 0 <= event.day_offset <= horizon:
            per_day.setdefault(event.day_offset, []).append(event)
    rows = []
    for offset in range(horizon + 1):
        day_events = per_day.get(offset, [])
        cash_in = sum(e.amount for e in day_events if e.amount > 0)
        cash_out = sum(-e.amount for e in day_events if e.amount < 0)
        rows.append(
            {
                "day_offset": offset,
                "cash_in": round(cash_in, 2),
                "cash_out": round(cash_out, 2),
                "net": round(cash_in - cash_out, 2),
                "events": len(day_events),
            }
        )
    return rows


def treasury_projection(start: float, daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cumulative treasury projection from a signed daily ladder."""
    balance = start
    projected = []
    for row in daily:
        balance += row["net"]
        projected.append({**row, "closing": round(balance, 2)})
    return projected


def weekly_buckets(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weeks: list[dict[str, Any]] = []
    for index in range(0, len(daily), 7):
        chunk = daily[index:index + 7]
        if not chunk:
            continue
        weeks.append(
            {
                "week": index // 7 + 1,
                "day_start": chunk[0]["day_offset"],
                "day_end": chunk[-1]["day_offset"],
                "cash_in": round(sum(r["cash_in"] for r in chunk), 2),
                "cash_out": round(sum(r["cash_out"] for r in chunk), 2),
                "net": round(sum(r["net"] for r in chunk), 2),
                "closing": chunk[-1]["closing"],
            }
        )
    return weeks


def coverage_metrics(projected: list[dict[str, Any]], start: float) -> dict[str, Any]:
    """Cash-in/out coverage and liquidity buffer/coverage by horizon."""
    out = {}
    for horizon in HORIZONS:
        rows = [r for r in projected if r["day_offset"] <= horizon]
        cash_in = sum(r["cash_in"] for r in rows)
        cash_out = sum(r["cash_out"] for r in rows)
        net = cash_in - cash_out
        closing = rows[-1]["closing"] if rows else start
        minimum = min((r["closing"] for r in projected[: horizon + 1]), default=start)
        out[str(horizon)] = {
            "cash_in": round(cash_in, 2),
            "cash_out": round(cash_out, 2),
            "net_liquidity_gap": round(net, 2),
            "projected_treasury": round(closing, 2),
            "liquidity_buffer": round(closing - cash_out, 2),
            "cash_coverage_ratio": round(start / cash_out, 4) if cash_out > 0 else None,
            "ar_collection_coverage": round(cash_in / cash_out, 4) if cash_out > 0 else None,
            "minimum_treasury": round(minimum, 2),
        }
    return out


def minimum_treasury(projected: list[dict[str, Any]]) -> dict[str, Any]:
    if not projected:
        return {"minimum_treasury": None, "date_offset": None}
    row = min(projected, key=lambda r: r["closing"])
    return {"minimum_treasury": row["closing"], "date_offset": row["day_offset"], "net": row["net"]}


def first_deficit(projected: list[dict[str, Any]]) -> int | None:
    for row in projected:
        if row["closing"] < 0:
            return row["day_offset"]
    return None


def max_funding_need(projected: list[dict[str, Any]]) -> float:
    deficit = min((row["closing"] for row in projected), default=0.0)
    return round(-deficit, 2) if deficit < 0 else 0.0


def max_surplus(projected: list[dict[str, Any]]) -> float:
    return round(max((row["closing"] for row in projected), default=0.0), 2)


def liquidity_risk_flag(projected: list[dict[str, Any]], start: float) -> str:
    """Descriptive classification with explicit numeric rules."""
    minimum = min((row["closing"] for row in projected), default=start)
    if minimum < 0:
        return "DEFICIT"
    # 7-day expected net outflow vs remaining treasury.
    next7 = sum(row["net"] for row in projected[:8])
    if minimum < 0.02 * max(start, 1.0) or (start > 0 and next7 < -start):
        return "PRESSURE"
    if start > 0 and minimum < 0.10 * start:
        return "WATCH"
    return "NORMAL"


# ---------------------------------------------------------------------------
# Concentration
# ---------------------------------------------------------------------------
def concentration(items: Iterable[tuple[str, float]]) -> dict[str, Any]:
    positive = sorted(((key, value) for key, value in items if value > 0), key=lambda pair: pair[1], reverse=True)
    total = sum(value for _, value in positive)
    if total <= 0:
        return {"top_1": 0.0, "top_5": 0.0, "top_10": 0.0, "total": 0.0, "entities": 0}
    return {
        "top_1": round(100.0 * sum(v for _, v in positive[:1]) / total, 4),
        "top_5": round(100.0 * sum(v for _, v in positive[:5]) / total, 4),
        "top_10": round(100.0 * sum(v for _, v in positive[:10]) / total, 4),
        "total": round(total, 2),
        "entities": len(positive),
    }


# ---------------------------------------------------------------------------
# Backtest metrics / model selection
# ---------------------------------------------------------------------------
def date_error_metrics(pairs: Iterable[tuple[date | None, date | None]]) -> dict[str, Any]:
    errors = []
    for predicted, actual in pairs:
        if predicted is None or actual is None:
            continue
        errors.append((actual - predicted).days)
    if not errors:
        return {"observations": 0, "mae_days": None, "bias_days": None, "within_7d_pct": None}
    absolute = [abs(e) for e in errors]
    return {
        "observations": len(errors),
        "mae_days": round(sum(absolute) / len(absolute), 4),
        "bias_days": round(sum(errors) / len(errors), 4),
        "within_7d_pct": round(100.0 * sum(1 for e in absolute if e <= 7) / len(errors), 4),
    }


def treasury_error_metrics(pairs: Iterable[tuple[float, float]]) -> dict[str, Any]:
    rows = [(p, a) for p, a in pairs]
    if not rows:
        return {"observations": 0, "mae": None, "bias": None, "mae_pct": None}
    errors = [a - p for p, a in rows]
    absolute = [abs(e) for e in errors]
    pct = [
        abs(a - p) / abs(a) * 100.0
        for p, a in rows
        if abs(a) > 1e-6
    ]
    return {
        "observations": len(rows),
        "mae": round(sum(absolute) / len(absolute), 2),
        "bias": round(sum(errors) / len(errors), 2),
        "mae_pct": round(sum(pct) / len(pct), 4) if pct else None,
    }


def directional_accuracy(pairs: Iterable[tuple[float, float]]) -> float | None:
    correct = 0
    total = 0
    for predicted_delta, actual_delta in pairs:
        if abs(predicted_delta) < 1e-9 or abs(actual_delta) < 1e-9:
            continue
        total += 1
        if (predicted_delta > 0) == (actual_delta > 0):
            correct += 1
    if total == 0:
        return None
    return round(100.0 * correct / total, 4)


def select_best_model(models: Mapping[str, Mapping[str, Any]], max_mae: float | None = None) -> str | None:
    """Choose the baseline with lowest treasury MAE among eligible models."""
    eligible = []
    for name, metrics in models.items():
        mae = metrics.get("treasury_mae")
        if mae is None:
            continue
        if max_mae is not None and mae > max_mae:
            continue
        eligible.append((mae, name))
    if not eligible:
        return None
    return min(eligible)[1]


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------
def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    if hasattr(value, "date"):
        return value.date()
    raise TypeError(f"unsupported date value: {value!r}")


def add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
