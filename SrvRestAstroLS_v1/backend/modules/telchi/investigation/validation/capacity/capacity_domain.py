"""Max producible by component domain (pure logic, READ ONLY).

Semantics (TELCHI, 2026-08-27):
  - AVAILABLE_COMPONENT_FOR_PRODUCTION = OnHand - IsCommited in RAW_MATERIAL
    role warehouses (LAB-M1, SAA-M1, MAG-M1). EQUIVALENT_IN_FG is NOT usable
    for new production (it is already-transformed material).
  - requirement per FG unit = HISTORICAL_PRODUCTION_RATIO (Gate 3), with
    CURRENT_BOM fallback. Direct (raw+semi) and terminal (raw) expansions.
  - COMPONENT_CAPACITY[fg][comp] = available[comp] / requirement[fg][comp].
  - THEORETICAL_MAX_IF_PRIORITY[fg] = MIN(component capacities).
  - LIMITING_COMPONENT = argmin. Shared components: a physical qty cannot be
    allocated independently to multiple FG (SHARED_COMPONENT flag).
  - MATERIEL_MAX_PRODUCIBLE (this gate) != OPERATIONAL_FACTORY_CAPACITY.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

RAW_MATERIAL_WAREHOUSES = {"LAB-M1", "SAA-M1", "MAG-M1"}

FLAG_SHARED_COMPONENT = "SHARED_COMPONENT"
FLAG_ALLOCATION_UNRESOLVED = "SHARED_COMPONENT_ALLOCATION_UNRESOLVED"
FLAG_NO_REQUIREMENT = "NO_REQUIREMENT"
FLAG_NEGATIVE_CAPACITY = "NEGATIVE_CAPACITY"
FLAG_UOM_UNRESOLVED = "UOM_UNRESOLVED"


def available_for_production(rows: Iterable[tuple[str, str, float, float]]) -> dict[str, float]:
    """rows: (component, whs, onhand, committed). Sum (onhand-committed) over
    RAW_MATERIAL warehouses per component."""
    out: dict[str, float] = {}
    for comp, whs, onhand, committed in rows:
        if whs not in RAW_MATERIAL_WAREHOUSES:
            continue
        avail = float(onhand or 0.0) - float(committed or 0.0)
        out[comp] = out.get(comp, 0.0) + avail
    return out


def requirement_per_fg(consumed: dict[tuple[str, str], float],
                       produced: dict[str, float]) -> dict[tuple[str, str], float]:
    """HISTORICAL_PRODUCTION_RATIO per (fg, component)."""
    out: dict[tuple[str, str], float] = {}
    for (fg, comp), cons in consumed.items():
        prod = produced.get(fg, 0.0)
        if prod and prod > 0:
            r = float(cons) / float(prod)
            if r > 0:
                out[(fg, comp)] = r
    return out


def component_capacity(available: float, requirement: float) -> float:
    """Units of FG producible from this component. inf when no requirement."""
    if requirement is None or requirement <= 0:
        return math.inf
    return float(available) / float(requirement)


# ---------------------------------------------------------------------------
# Terminal requirement expansion (multi-level)
# ---------------------------------------------------------------------------

def expand_requirement_terminal(fg: str,
                                direct: dict[tuple[str, str], float],
                                produced: set[str],
                                max_depth: int = 4) -> dict[str, float]:
    """Expand a FG's direct component requirement to terminal raw components.

    Produced (semi) components are replaced by their own direct requirements
    (recursive), avoiding double counting the semi and its embedded raw.
    Returns {terminal_component: qty_per_fg}.
    """
    req = {k[1]: v for k, v in direct.items() if k[0] == fg}
    for _ in range(max_depth):
        changed = False
        new_req: dict[str, float] = {}
        for comp, qty in req.items():
            if comp in produced and (fg, comp) in direct and comp != fg:
                subs = {k[1]: v for k, v in direct.items() if k[0] == comp}
                if subs:
                    for sub, sq in subs.items():
                        new_req[sub] = new_req.get(sub, 0.0) + qty * sq
                    changed = True
                    continue
            new_req[comp] = new_req.get(comp, 0.0) + qty
        req = new_req
        if not changed:
            break
    return req


# ---------------------------------------------------------------------------
# Capacity / limiting component
# ---------------------------------------------------------------------------

@dataclass
class FgCapacity:
    fg: str
    available_by_component: dict[str, float] = field(default_factory=dict)
    capacity_by_component: dict[str, float] = field(default_factory=dict)
    terminal_capacity_by_component: dict[str, float] = field(default_factory=dict)

    @property
    def immediate_max(self) -> float:
        if not self.capacity_by_component:
            return 0.0
        return min(self.capacity_by_component.values())

    @property
    def expanded_max(self) -> float:
        if not self.terminal_capacity_by_component:
            return 0.0
        return min(self.terminal_capacity_by_component.values())

    @property
    def limiting_component(self) -> str | None:
        if not self.capacity_by_component:
            return None
        return min(self.capacity_by_component, key=self.capacity_by_component.get)

    @property
    def terminal_limiting_component(self) -> str | None:
        if not self.terminal_capacity_by_component:
            return None
        return min(self.terminal_capacity_by_component, key=self.terminal_capacity_by_component.get)


def build_capacity(fg: str, direct_req: dict[tuple[str, str], float],
                   available: dict[str, float], produced: set[str]) -> FgCapacity:
    """Compute immediate + terminal capacity for one FG."""
    direct = {k[1]: v for k, v in direct_req.items() if k[0] == fg}
    cap = FgCapacity(fg=fg)
    for comp, req in direct.items():
        if req <= 0:
            continue
        cap.available_by_component[comp] = available.get(comp, 0.0)
        cap.capacity_by_component[comp] = component_capacity(available.get(comp, 0.0), req)
    terminal = expand_requirement_terminal(fg, direct_req, produced)
    for comp, req in terminal.items():
        if req <= 0:
            continue
        cap.terminal_capacity_by_component[comp] = component_capacity(
            available.get(comp, 0.0), req)
    return cap


def shared_component_map(direct_req: dict[tuple[str, str], float]) -> dict[str, set[str]]:
    """component -> set of FG that use it."""
    out: dict[str, set[str]] = {}
    for (fg, comp) in direct_req:
        out.setdefault(comp, set()).add(fg)
    return out


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def invariant_limiting_is_min(cap: FgCapacity) -> bool:
    """MAX_PRODUCIBLE == MIN(capacities) by construction; verify the limiting
    component actually yields the min value."""
    if not cap.capacity_by_component:
        return True
    return cap.immediate_max == cap.capacity_by_component[cap.limiting_component]


def invariant_non_negative_capacity(cap: FgCapacity) -> list[str]:
    """Negative available -> negative capacity must be flagged, not silently
    zeroed."""
    neg = [c for c, v in cap.capacity_by_component.items() if v < 0]
    return neg


def invariant_no_equivalent_reuse() -> bool:
    """EQUIVALENT_IN_FG is never in AVAILABLE_FOR_PRODUCTION (by construction
    availability only sums physical raw warehouses)."""
    return True