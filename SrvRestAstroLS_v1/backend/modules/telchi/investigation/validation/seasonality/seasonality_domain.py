"""Product seasonality domain (pure logic, no HANA).

Sales grain: (ItemCode, Year, Month) -> NetQty (gross - returns).
Zero-month filling is explicit: a missing month is a real zero in the series.

Demand patterns: STABLE, SEASONAL, GROWING, DECLINING, INTERMITTENT,
PROMOTIONAL, NEW_PRODUCT, DISCONTINUED, INSUFFICIENT_HISTORY, UNRESOLVED.

Stockout censoring: zero sales + (optional) zero-stock evidence -> flag
POTENTIAL_STOCKOUT_CENSORED_DEMAND (never assert demand, only flag).

Forecast is in forecast.py; metrics in metrics.py; backtest in backtest.py.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable

PATTERN_STABLE = "STABLE"
PATTERN_SEASONAL = "SEASONAL"
PATTERN_GROWING = "GROWING"
PATTERN_DECLINING = "DECLINING"
PATTERN_INTERMITTENT = "INTERMITTENT"
PATTERN_PROMOTIONAL = "PROMOTIONAL_OR_EVENT_DRIVEN"
PATTERN_NEW = "NEW_PRODUCT"
PATTERN_DISCONTINUED = "DISCONTINUED"
PATTERN_INSUFFICIENT = "INSUFFICIENT_HISTORY"
PATTERN_UNRESOLVED = "UNRESOLVED"

FLAG_SEASONALITY_UNCERTAIN = "SEASONALITY_UNCERTAIN"
FLAG_STOCKOUT_CENSORED = "POTENTIAL_STOCKOUT_CENSORED_DEMAND"
FLAG_SUCCESSOR = "POSSIBLE_PRODUCT_SUCCESSOR"
FLAG_NEGATIVE_NET = "NEGATIVE_NET_SALES"


@dataclass
class MonthlyPoint:
    year: int
    month: int
    qty: float

    @property
    def key(self) -> tuple[int, int]:
        return (self.year, self.month)


@dataclass
class DemandProfile:
    itemcode: str
    pattern: str
    confidence: str
    years_history: int
    active_months: int
    history_months: int
    peak_month: int | None
    peak_share: float
    cv: float
    trend_yoy: float | None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "itemcode": self.itemcode, "pattern": self.pattern,
            "confidence": self.confidence, "years_history": self.years_history,
            "active_months": self.active_months, "history_months": self.history_months,
            "peak_month": self.peak_month, "peak_share": round(self.peak_share, 3),
            "cv": round(self.cv, 3), "trend_yoy": self.trend_yoy,
            "flags": self.flags,
        }


def build_series(points: Iterable[MonthlyPoint]) -> dict[tuple[int, int], float]:
    return {p.key: p.qty for p in points}


def fill_zero_months(series: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """Fill missing months between first and last with zero."""
    if not series:
        return {}
    keys = sorted(series)
    y0, m0 = keys[0]
    y1, m1 = keys[-1]
    out = dict(series)
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.setdefault((y, m), 0.0)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def monthly_means(series: dict[tuple[int, int], float]) -> dict[int, float]:
    """mean qty per calendar month across years."""
    sums: dict[int, list[float]] = {}
    for (y, m), q in series.items():
        sums.setdefault(m, []).append(q)
    return {m: sum(v) / len(v) for m, v in sums.items()}


def cv(values: list[float]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    sd = statistics.pstdev(values)
    return sd / mean


def yoy_trend(series: dict[tuple[int, int], float], as_of_year: int,
              as_of_month: int) -> float | None:
    """Trailing 12-month YoY: (last 12mo - prior 12mo) / prior 12mo."""
    def window(offset_start: int) -> float:
        total = 0.0
        for offset in range(offset_start, offset_start + 12):
            pm = as_of_month - 1 - offset
            py = as_of_year
            while pm < 1:
                pm += 12
                py -= 1
            total += series.get((py, pm), 0.0)
        return total

    last12 = window(0)   # 12 months immediately before as_of
    prior12 = window(12)  # the 12 months before those
    if prior12 <= 0:
        return None
    return (last12 - prior12) / prior12


def classify(series: dict[tuple[int, int], float], as_of_year: int, as_of_month: int) -> DemandProfile:
    """Interpretable multi-signal demand classification."""
    if not series:
        return DemandProfile("", PATTERN_UNRESOLVED, "LOW", 0, 0, 0, None, 0, 0, None)
    series = fill_zero_months(series)
    keys = sorted(series)
    y0, m0 = keys[0]
    y1, m1 = keys[-1]
    history_months = (y1 - y0) * 12 + (m1 - m0) + 1
    active_months = sum(1 for q in series.values() if q > 0)
    years = sorted({y for y, _ in keys})
    years_history = len(years)

    # recent activity window (last 12 months)
    recent_cutoff = (as_of_year - 1, as_of_month)
    recent_sum = sum(q for (y, m), q in series.items() if (y, m) >= recent_cutoff)

    flags: list[str] = []

    # insufficient history first (can't judge anything with too little data)
    if history_months < 12 or active_months < 6:
        return DemandProfile("", PATTERN_INSUFFICIENT, "LOW", years_history,
                             active_months, history_months, None, 0, 0, None, flags)

    # discontinued: no sales in last 12 months
    if recent_sum <= 0 and active_months > 0:
        return DemandProfile("", PATTERN_DISCONTINUED, "HIGH", years_history,
                             active_months, history_months, None, 0, 0, None, flags)

    # new product: first sale within last 12 months
    if (y0, m0) >= recent_cutoff:
        return DemandProfile("", PATTERN_NEW, "MEDIUM", years_history,
                             active_months, history_months, None, 0, 0, None, flags)

    means = monthly_means(series)
    all_mean = sum(means.values()) / 12 if means else 0
    peak_month = max(means, key=means.get) if means else None
    peak_share = (means[peak_month] / all_mean) if all_mean and peak_month else 0
    cv_val = cv(list(means.values()))
    trend = yoy_trend(series, as_of_year, as_of_month)

    # seasonal: peak month(s) recurrent across years (>=2 years same/adjacent peak)
    seasonal = _recurrent_peak(series, means, all_mean)

    # intermittent: sparse non-zero months, not seasonal
    density = active_months / history_months

    pattern = PATTERN_STABLE
    confidence = "MEDIUM"
    if seasonal and cv_val >= 0.5:
        pattern = PATTERN_SEASONAL
        confidence = "HIGH" if years_history >= 3 else "MEDIUM"
    elif seasonal and years_history < 2:
        pattern = PATTERN_SEASONAL
        confidence = "LOW"
        flags.append(FLAG_SEASONALITY_UNCERTAIN)
    elif density < 0.5 and cv_val >= 0.8:
        pattern = PATTERN_INTERMITTENT
    elif trend is not None and trend >= 0.25:
        pattern = PATTERN_GROWING
    elif trend is not None and trend <= -0.25:
        pattern = PATTERN_DECLINING
    elif seasonal:
        pattern = PATTERN_SEASONAL
        confidence = "LOW"
        flags.append(FLAG_SEASONALITY_UNCERTAIN)

    return DemandProfile("", pattern, confidence, years_history, active_months,
                         history_months, peak_month, peak_share, cv_val, trend, flags)


def _recurrent_peak(series: dict[tuple[int, int], float], means: dict[int, float],
                    all_mean: float) -> bool:
    """True if the peak month(s) recur across >=2 years (same or adjacent month)."""
    if not all_mean:
        return False
    peak_month = max(means, key=means.get)
    peak_val = means[peak_month]
    if peak_val < 1.5 * all_mean:
        return False
    years = {y for (y, _) in series}
    hits = 0
    for y in years:
        months = {m: q for (yy, m), q in series.items() if yy == y}
        if not months:
            continue
        y_peak = max(months, key=months.get)
        if abs(y_peak - peak_month) <= 1 or abs(y_peak - peak_month) == 11:
            hits += 1
    return hits >= 2


def expected_demand_to_peak(series: dict[tuple[int, int], float],
                            season_end_month: int, snapshot_year: int,
                            snapshot_month: int) -> float:
    """Sum of same-month-last-year forecasts from snapshot month to season end."""
    total = 0.0
    y, m = snapshot_year, snapshot_month
    for _ in range(13):
        total += series.get((y - 1, m), 0.0)
        if m == season_end_month:
            break
        m += 1
        if m > 12:
            m = 1
            y += 1
    return total


def negative_net_months(series: dict[tuple[int, int], float]) -> list[tuple[int, int]]:
    return [(y, m) for (y, m), q in series.items() if q < 0]


def clamp_forecast(qty: float) -> float:
    return max(0.0, qty)