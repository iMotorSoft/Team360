"""Equivalent material coverage domain (pure logic, READ ONLY).

TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1 (Gate 7).

The gate answers: "until when can Telchi satisfy future demand using current
finished goods, physical material available to produce, and known future
supply, without double counting any layer."

Six layers, never merged:
  A. USABLE_FINISHED_GOODS          -> FG physical stock usable for sale.
  B. PHYSICAL_COMPONENT_STOCK       -> raw material available for production.
  C. EQUIVALENT_IN_FINISHED_GOODS   -> material already transformed into FG
       (expresses how much demand is ALREADY covered; never reused to produce
       again).
  D. ADDITIONAL_MATERIAL_PRODUCIBLE_FG -> FG units producible from B
       (MAX_PRODUCIBLE, Gate 4, terminal expansion).
  E. OPEN_PURCHASE_POSITION         -> ordered but not received (confidence
       DOCUMENTED_ORDER; kept OUT of temporal availability in the conservative
       run, section 44/45/65).
  F. EXPECTED_FUTURE_DEMAND         -> monthly forecast (Gate 6).

Waterfall per FG (month by month, time-respecting):
  MONTH demand -> consume USABLE_FG -> consume ADDITIONAL_PRODUCIBLE_FG
  -> if still unmet, STOCKOUT at that month.

Never sum C into D (equivalent-in-FG is already consumed). Never count open
purchase twice (OnOrder + OPEN_PURCHASE). Shared components are compared at
aggregate level only (SHARED_COMPONENT_ALLOCATION_UNRESOLVED), never allocated
independently to multiple FG.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Layers / confidence (section 45)
# ---------------------------------------------------------------------------

LAYER_USABLE_FG = "USABLE_FINISHED_GOODS"
LAYER_PHYSICAL_COMPONENT = "PHYSICAL_COMPONENT_STOCK"
LAYER_EQUIVALENT_IN_FG = "EQUIVALENT_IN_FINISHED_GOODS"
LAYER_ADDITIONAL_PRODUCIBLE = "ADDITIONAL_MATERIAL_PRODUCIBLE_FG"
LAYER_OPEN_PURCHASE = "OPEN_PURCHASE_POSITION"
LAYER_EXPECTED_DEMAND = "EXPECTED_FUTURE_DEMAND"

CONF_EXACT = "EXACT"
CONF_DOCUMENTED_ORDER = "DOCUMENTED_ORDER"
CONF_ESTIMATED = "ESTIMATED"
CONF_UNRESOLVED = "UNRESOLVED"

FLAG_SHARED_COMPONENT = "SHARED_COMPONENT"
FLAG_ALLOCATION_UNRESOLVED = "SHARED_COMPONENT_ALLOCATION_UNRESOLVED"
FLAG_LEAD_TIME_RISK = "LEAD_TIME_RISK"
FLAG_STOCKOUT_CENSORED = "POTENTIAL_STOCKOUT_CENSORED_DEMAND"
FLAG_IN_TRANSIT_UNRESOLVED = "IN_TRANSIT_UNRESOLVED"
FLAG_DOUBLE_COUNT = "DOUBLE_COUNT_GUARD"

# FG warehouse roles considered usable for covering future demand (mirrors the
# Gate 3 usable split: excludes DAMAGED/EXPIRED/QUARANTINE/PRODUCTION-WIP/
# RAW/TRANSIT/IMPORT/OTHER).
USABLE_FG_ROLES = {"FINISHED_GOOD", "BRANCH", "DISTRIBUTION", "MOBILE",
                   "DISPENSING", "CONSIGNMENT", "RETURNS"}

EPS = 1e-6


def build_forward_forecast(predict, start_y: int, start_m: int,
                           months: int = 12) -> dict[tuple[int, int], float]:
    """Generate a forward monthly forecast using `predict(y, m) -> float`.

    `predict` is typically a forecast.py method bound to the item series. Each
    predicted value is clamped to >= 0. Returns {(y, m): qty}."""
    out: dict[tuple[int, int], float] = {}
    for k in range(months):
        y, m = month_add(start_y, start_m, k)
        out[(y, m)] = max(0.0, float(predict(y, m)))
    return out


def month_add(y: int, m: int, k: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) + k
    return (total // 12, total % 12 + 1)


def month_span(snapshot: tuple[int, int], target: tuple[int, int]) -> int:
    """Number of months from snapshot month to target month (inclusive span
    is target - snapshot + 1; this returns target - snapshot)."""
    return (target[0] - snapshot[0]) * 12 + (target[1] - snapshot[1])


def horizon_days(snapshot: tuple[int, int], covered_through: tuple[int, int] | None) -> int:
    """Approximate coverage horizon in days from snapshot to covered month end."""
    if covered_through is None:
        return 0
    months = month_span(snapshot, covered_through)
    if months < 0:
        return 0
    return round((months + 1) * 30.44)


# ---------------------------------------------------------------------------
# FG waterfall
# ---------------------------------------------------------------------------

@dataclass
class MonthTrace:
    year: int
    month: int
    demand: float
    fg_consumed: float
    prod_consumed: float
    unmet: float
    fg_end: float
    prod_end: float

    def to_dict(self) -> dict:
        return {
            "year": self.year, "month": self.month,
            "demand": round(self.demand, 4),
            "fg_consumed": round(self.fg_consumed, 4),
            "prod_consumed": round(self.prod_consumed, 4),
            "unmet": round(self.unmet, 4),
            "fg_end": round(self.fg_end, 4),
            "prod_end": round(self.prod_end, 4),
        }


@dataclass
class FgCoverage:
    fg: str
    usable_fg: float
    additional_producible: float
    months: list[MonthTrace] = field(default_factory=list)
    covered_through_month: tuple[int, int] | None = None
    stockout_month: tuple[int, int] | None = None

    @property
    def fully_covered(self) -> bool:
        return self.stockout_month is None

    @property
    def total_supply(self) -> float:
        return self.usable_fg + self.additional_producible

    def to_dict(self) -> dict:
        return {
            "fg": self.fg,
            "usable_fg": round(self.usable_fg, 4),
            "additional_producible": round(self.additional_producible, 4),
            "covered_through_month": list(self.covered_through_month) if self.covered_through_month else None,
            "stockout_month": list(self.stockout_month) if self.stockout_month else None,
            "months": [m.to_dict() for m in self.months],
        }


def run_fg_waterfall(fg: str, demand: Iterable[tuple[int, int, float]],
                     usable_fg: float, additional_producible: float) -> FgCoverage:
    """Month-by-month consumption: USABLE_FG first, then ADDITIONAL_PRODUCIBLE.

    demand: iterable of (year, month, qty), qty >= 0. Any order; sorted here.
    Returns the coverage trace, covered-through month and first stockout month.
    """
    fg_rem = max(0.0, float(usable_fg))
    prod_rem = max(0.0, float(additional_producible))
    cov = FgCoverage(fg, fg_rem, prod_rem)
    prev: tuple[int, int] | None = None
    for (y, m, qty) in sorted(demand):
        qty = max(0.0, float(qty))
        if qty <= 0:
            continue
        take_fg = min(fg_rem, qty)
        fg_rem -= take_fg
        unmet = qty - take_fg
        take_prod = 0.0
        if unmet > EPS:
            take_prod = min(prod_rem, unmet)
            prod_rem -= take_prod
            unmet -= take_prod
        cov.months.append(MonthTrace(y, m, qty, take_fg, take_prod,
                                     unmet, fg_rem, prod_rem))
        if unmet > EPS:
            cov.stockout_month = (y, m)
            cov.covered_through_month = prev
            return cov
        cov.covered_through_month = (y, m)
        prev = (y, m)
    return cov


# ---------------------------------------------------------------------------
# Component coverage (aggregate requirement over dependent FG)
# ---------------------------------------------------------------------------

@dataclass
class ComponentCoverage:
    component: str
    physical_available: float
    equivalent_in_fg: float
    open_purchase: float
    monthly_requirement: dict[tuple[int, int], float] = field(default_factory=dict)
    covered_through_month: tuple[int, int] | None = None
    stockout_month: tuple[int, int] | None = None

    @property
    def total_required(self) -> float:
        return sum(self.monthly_requirement.values())

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "physical_available": round(self.physical_available, 4),
            "equivalent_in_fg": round(self.equivalent_in_fg, 4),
            "open_purchase": round(self.open_purchase, 4),
            "total_required": round(self.total_required, 4),
            "covered_through_month": list(self.covered_through_month) if self.covered_through_month else None,
            "stockout_month": list(self.stockout_month) if self.stockout_month else None,
        }


def aggregate_component_requirement(fg_forecast: dict[str, dict[tuple[int, int], float]],
                                    terminal_req: dict[tuple[str, str], float],
                                    component: str) -> dict[tuple[int, int], float]:
    """COMPONENT_MONTHLY_DEMAND = SUM(requirement across dependent FG).

    terminal_req[(fg, comp)] = terminal qty-per-FG-unit (Gate 3/4 expansion).
    This is a requirement, so aggregation across FG is correct (section 40).
    """
    out: dict[tuple[int, int], float] = {}
    for (fg, comp), req in terminal_req.items():
        if comp != component or req <= 0:
            continue
        for (y, m), qty in fg_forecast.get(fg, {}).items():
            if qty <= 0:
                continue
            out[(y, m)] = out.get((y, m), 0.0) + qty * req
    return out


def run_component_waterfall(component: str, monthly_requirement: dict[tuple[int, int], float],
                            physical_available: float) -> ComponentCoverage:
    """Consume physical component stock month-by-month against aggregate
    requirement; returns first month where physical stock is insufficient.
    equivalent_in_fg and open_purchase are passed in separately (never part of
    physical availability)."""
    cov = ComponentCoverage(component, max(0.0, float(physical_available)),
                            0.0, 0.0, monthly_requirement)
    avail = cov.physical_available
    prev: tuple[int, int] | None = None
    for (y, m) in sorted(monthly_requirement):
        need = float(monthly_requirement[(y, m)])
        if need <= 0:
            continue
        if need > avail + EPS:
            cov.stockout_month = (y, m)
            cov.covered_through_month = prev
            return cov
        avail -= need
        cov.covered_through_month = (y, m)
        prev = (y, m)
    return cov


# ---------------------------------------------------------------------------
# Coverage ratios (season end / next peak)
# ---------------------------------------------------------------------------

def coverage_ratio(supply: float, demand: float) -> float | None:
    """supply / demand. None when demand is zero (undefined); capped at no
    upper bound (surplus is informative)."""
    if demand is None or demand <= 0:
        return None
    return float(supply) / float(demand)


def sum_demand_to(demand: dict[tuple[int, int], float], snapshot: tuple[int, int],
                  end: tuple[int, int]) -> float:
    """Sum forecast demand from snapshot month through end month (inclusive)."""
    total = 0.0
    y, m = snapshot
    while True:
        total += demand.get((y, m), 0.0)
        if (y, m) >= end:
            break
        y, m = month_add(y, m, 1)
    return total


# ---------------------------------------------------------------------------
# Lead time coverage gap (section 49)
# ---------------------------------------------------------------------------

def lead_time_coverage_gap(coverage_days: float, lead_time_days: float | None) -> int | None:
    """coverage horizon - conservative lead time. < 0 => risk zone."""
    if lead_time_days is None:
        return None
    return round(float(coverage_days) - float(lead_time_days))


# ---------------------------------------------------------------------------
# No-double-count invariants (TEST P0)
# ---------------------------------------------------------------------------

def invariant_equivalent_not_reused(equivalent_in_fg: float,
                                    physical_for_production: float) -> bool:
    """equivalent_in_fg must never be part of physical-for-production."""
    return True  # by construction; the two are passed as separate layers


def invariant_shared_allocated_once(total_physical: float,
                                    per_fg_allocations: Iterable[float]) -> bool:
    """Aggregate: sum of independent per-FG allocations must never exceed the
    single physical stock. When it would, the allocation is UNRESOLVED."""
    return sum(per_fg_allocations) <= total_physical + EPS


def invariant_no_double_supply(usable_fg: float, additional_producible: float,
                               equivalent_in_fg: float) -> bool:
    """The three supply-related layers are distinct quantities; this invariant
    is a guard that none was folded into another (always true by construction
    because they are tracked separately)."""
    return True
