"""Forecast error metrics."""

from __future__ import annotations

from typing import Iterable


def mae(actual: Iterable[float], forecast: Iterable[float]) -> float:
    pairs = list(zip(actual, forecast))
    if not pairs:
        return 0.0
    return sum(abs(a - f) for a, f in pairs) / len(pairs)


def wape(actual: Iterable[float], forecast: Iterable[float]) -> float:
    a = list(actual)
    f = list(forecast)
    denom = sum(abs(x) for x in a)
    if denom == 0:
        return 0.0
    return sum(abs(x - y) for x, y in zip(a, f)) / denom


def bias(actual: Iterable[float], forecast: Iterable[float]) -> float:
    """mean(forecast - actual). Positive = overforecast, negative = underforecast."""
    pairs = list(zip(actual, forecast))
    if not pairs:
        return 0.0
    return sum(f - a for a, f in pairs) / len(pairs)
