"""Forecast baselines (transparent, reproducible) and metrics."""

from __future__ import annotations

METHOD_NAIVE = "NAIVE_LAST_MONTH"
METHOD_MA3 = "MOVING_AVERAGE_3"
METHOD_SMLY = "SAME_MONTH_LAST_YEAR"
METHOD_SEASONAL_MA = "SEASONAL_MOVING_AVERAGE"
METHOD_YOY = "YOY_ADJUSTED_SEASONAL"


def clamp(v: float) -> float:
    return max(0.0, v)


def naive_last_month(series: dict[tuple[int, int], float], y: int, m: int) -> float:
    pm = (y, m - 1) if m > 1 else (y - 1, 12)
    return clamp(series.get(pm, 0.0))


def moving_average_3(series: dict[tuple[int, int], float], y: int, m: int) -> float:
    vals = []
    for k in range(3):
        km = m - k
        ky = y
        if km <= 0:
            km += 12
            ky -= 1
        vals.append(series.get((ky, km), 0.0))
    return clamp(sum(vals) / 3)


def same_month_last_year(series: dict[tuple[int, int], float], y: int, m: int) -> float:
    return clamp(series.get((y - 1, m), 0.0))


def seasonal_moving_average(series: dict[tuple[int, int], float], y: int, m: int) -> float:
    vals = [series.get((yy, m), 0.0) for yy in range(y - 3, y)]
    return clamp(sum(vals) / len(vals))


def yoy_adjusted_seasonal(series: dict[tuple[int, int], float], y: int, m: int) -> float:
    base = seasonal_moving_average(series, y, m)
    last12 = sum(q for (yy, mm), q in series.items() if (yy, mm) >= (y - 1, m))
    prior12 = sum(q for (yy, mm), q in series.items() if (y - 2, m) <= (yy, mm) < (y - 1, m))
    if prior12 <= 0:
        return clamp(base)
    growth = last12 / prior12
    return clamp(base * growth)


FORECAST_METHODS = {
    METHOD_NAIVE: naive_last_month,
    METHOD_MA3: moving_average_3,
    METHOD_SMLY: same_month_last_year,
    METHOD_SEASONAL_MA: seasonal_moving_average,
    METHOD_YOY: yoy_adjusted_seasonal,
}
