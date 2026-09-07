"""Walk-forward backtest (anti-leakage)."""

from __future__ import annotations

from typing import Callable

from modules.telchi.investigation.validation.seasonality import forecast as fc
from modules.telchi.investigation.validation.seasonality import metrics as mt


def walk_forward(series: dict[tuple[int, int], float],
                 snapshot_months: list[tuple[int, int]],
                 horizon: int,
                 methods: list[str]) -> dict[str, dict]:
    """For each snapshot (y,m), train on series <= snapshot, forecast the next
    `horizon` months, compare to actual. No future leakage."""
    results: dict[str, dict] = {}
    for meth in methods:
        fn = fc.FORECAST_METHODS[meth]
        actual: list[float] = []
        pred: list[float] = []
        for (sy, sm) in snapshot_months:
            train = {k: v for k, v in series.items() if k <= (sy, sm)}
            for h in range(1, horizon + 1):
                hm = sm + h
                hy = sy
                if hm > 12:
                    hm -= 12
                    hy += 1
                actual.append(series.get((hy, hm), 0.0))
                pred.append(fn(train, hy, hm))
        results[meth] = {
            "n": len(actual),
            "mae": mt.mae(actual, pred),
            "wape": mt.wape(actual, pred),
            "bias": mt.bias(actual, pred),
        }
    return results


def choose_method(results: dict[str, dict], prefer_low_wape: bool = True) -> str:
    """Pick the method with lowest WAPE (ties -> lowest MAE)."""
    ranked = sorted(results.items(), key=lambda kv: (kv[1]["wape"], kv[1]["mae"]))
    return ranked[0][0]
