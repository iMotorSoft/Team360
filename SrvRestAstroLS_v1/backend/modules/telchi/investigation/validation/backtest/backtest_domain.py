"""Purchase decision backtest domain (pure, anti-leakage).

TELCHI_PURCHASE_DECISION_BACKTEST_V1 (Gate 9).

Reconstructs "what the engine knew" at a historical snapshot T (stock-as-of-T
and consumption history <= T), forecasts forward, and compares the predicted
stockout month against the ACTUAL consumption observed after T. Anti-leakage by
construction: the prediction only sees data <= T; the outcome only uses data > T.

Verdicts (no business causality asserted):
  POTENTIAL_EARLY_WARNING   predicted stockout AND actual consumption ran out
  POTENTIAL_MISSED_PURCHASE predicted safe (no stockout) AND actual ran out
  POTENTIAL_OVERBUY         predicted stockout AND actual did not run out
  CONSISTENT                predicted safe AND actual safe
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from modules.telchi.investigation.validation.coverage.coverage_domain import run_component_waterfall

VERDICT_EARLY_WARNING = "POTENTIAL_EARLY_WARNING"
VERDICT_MISSED = "POTENTIAL_MISSED_PURCHASE"
VERDICT_OVERBUY = "POTENTIAL_OVERBUY"
VERDICT_CONSISTENT = "CONSISTENT"


@dataclass
class BacktestResult:
    component: str
    snapshot: tuple[int, int]
    stock_at_t: float
    predicted_stockout_month: tuple[int, int] | None
    actual_stockout_month: tuple[int, int] | None
    verdict: str
    predicted_total_6mo: float = 0.0
    actual_total_6mo: float = 0.0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "snapshot": list(self.snapshot),
            "stock_at_t": round(self.stock_at_t, 2),
            "predicted_stockout_month": list(self.predicted_stockout_month) if self.predicted_stockout_month else None,
            "actual_stockout_month": list(self.actual_stockout_month) if self.actual_stockout_month else None,
            "verdict": self.verdict,
            "predicted_total_6mo": round(self.predicted_total_6mo, 2),
            "actual_total_6mo": round(self.actual_total_6mo, 2),
            "details": self.details,
        }


def fill_zero_months(series: dict[tuple[int, int], float],
                     start: tuple[int, int], end: tuple[int, int]) -> dict[tuple[int, int], float]:
    """Fill every month in [start, end] with zero where missing."""
    out = dict(series)
    y, m = start
    while (y, m) <= end:
        out.setdefault((y, m), 0.0)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def predict_stockout(component: str, stock_at_t: float,
                     forecast: dict[tuple[int, int], float]) -> tuple[int, int] | None:
    """Waterfall of physical stock against the forecast demand."""
    cc = run_component_waterfall(component, forecast, stock_at_t)
    return cc.stockout_month


def actual_stockout(component: str, stock_at_t: float,
                    actual: dict[tuple[int, int], float]) -> tuple[int, int] | None:
    """Waterfall of physical stock against the ACTUAL consumption."""
    cc = run_component_waterfall(component, actual, stock_at_t)
    return cc.stockout_month


def verdict_for(predicted: tuple[int, int] | None,
                actual: tuple[int, int] | None) -> str:
    """Map (predicted, actual) stockout presence to a verdict."""
    if predicted is not None and actual is not None:
        return VERDICT_EARLY_WARNING
    if predicted is None and actual is not None:
        return VERDICT_MISSED
    if predicted is not None and actual is None:
        return VERDICT_OVERBUY
    return VERDICT_CONSISTENT


def early_warning_accuracy(predicted: tuple[int, int] | None,
                           actual: tuple[int, int] | None,
                           tolerance_months: int = 1) -> bool:
    """Within an early warning, is the predicted month within tolerance of the
    actual exhaustion month? (Not required for the verdict, only for quality.)"""
    if predicted is None or actual is None:
        return False
    dp = predicted[0] * 12 + predicted[1]
    da = actual[0] * 12 + actual[1]
    return abs(dp - da) <= tolerance_months
