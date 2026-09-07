"""Finished-goods -> material equivalence domain (pure logic, READ ONLY).

Semantics (TELCHI, 2026-08-27):
  - FG universe = produced items (OWOR.Type='S'), 896 items; 656 have OnHand>0.
    Every FG with stock has BOTH production history (IGN1 output) and a
    current BOM (ITT1.Father). 6 produced items have no current BOM (no stock).
  - Component qty per FG unit:
      HISTORICAL_PRODUCTION: SUM(IGE1.Quantity)/SUM(IGN1.Quantity) per
        (FG, component) over real orders (BaseEntry = OWOR.DocEntry,
        BaseType=202). Reflects actual consumed vs actual produced
        (yield/waste/drift included).
      CURRENT_BOM: ITT1.Quantity / OITT.Qauntity (batch-normalized).
  - UOM: ITT1.Uom is NULL; component qty is in the component's own inventory
    UOM (OITM.InvntryUom). Never sum across UOMs (guard invariant).
  - Multi-level BOM: 238 components are themselves produced (semi-finished).
    DIRECT equivalence keeps intermediate components; TERMINAL expansion
    replaces semi components with their raw components (cycle-guarded).
  - EXACT_PRODUCTION_LINEAGE: UNAVAILABLE. SAP keeps no unit-level lineage of
    current stock to specific production orders (only partial batch via
    U_LOTE/OBTN); degraded to HISTORICAL_PRODUCTION_EQUIVALENCE.

Conservation (no double counting):
  - physical raw stock and transformed-in-FG equivalent are distinct layers.
  - a FG transfer between warehouses does not change global equivalence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Equivalence levels / methods
# ---------------------------------------------------------------------------

LEVEL_EXACT_PRODUCTION_LINEAGE = "EXACT_PRODUCTION_LINEAGE"
LEVEL_HISTORICAL_PRODUCTION = "HISTORICAL_PRODUCTION_EQUIVALENCE"
LEVEL_HISTORICAL_BOM = "HISTORICAL_BOM_EQUIVALENCE"
LEVEL_CURRENT_BOM = "CURRENT_BOM_EQUIVALENCE"
LEVEL_UNRESOLVED = "UNRESOLVED"

FLAG_MISSING_BOM = "MISSING_BOM"
FLAG_MISSING_PRODUCTION_HISTORY = "MISSING_PRODUCTION_HISTORY"
FLAG_HISTORICAL_LOW_SAMPLE = "HISTORICAL_EQUIVALENCE_LOW_SAMPLE"
FLAG_UOM_UNRESOLVED = "UOM_UNRESOLVED"
FLAG_BOM_CYCLE = "BOM_CYCLE_DETECTED"
FLAG_MULTILEVEL_PARTIAL = "MULTILEVEL_EXPANSION_PARTIAL"


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FgStock:
    itemcode: str
    whscode: str
    onhand: float
    uom: str | None
    role: str | None


@dataclass
class ComponentRatio:
    fg: str
    component: str
    qty_per_fg: float
    method: str
    component_uom: str | None = None
    component_class: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.qty_per_fg is not None and self.qty_per_fg > 0


@dataclass
class EquivalenceLine:
    fg: str
    fg_whs: str
    fg_stock: float
    fg_uom: str | None
    component: str
    component_uom: str | None
    component_class: str | None
    qty_per_fg: float
    method: str
    equivalent_qty: float

    def to_dict(self) -> dict:
        return {
            "fg": self.fg, "fg_whs": self.fg_whs, "fg_stock": self.fg_stock,
            "fg_uom": self.fg_uom, "component": self.component,
            "component_uom": self.component_uom,
            "component_class": self.component_class,
            "qty_per_fg": self.qty_per_fg, "method": self.method,
            "equivalent_qty": self.equivalent_qty,
        }


# ---------------------------------------------------------------------------
# Ratio helpers
# ---------------------------------------------------------------------------

def historical_ratio(consumed: float, produced: float) -> float | None:
    """component qty per FG unit from actual production."""
    if not produced or produced <= 0:
        return None
    return float(consumed) / float(produced)


def current_bom_ratio(quantity: float, batch_qty: float) -> float | None:
    """component qty per FG unit from current BOM (batch-normalized)."""
    if not batch_qty or batch_qty <= 0:
        return None
    return float(quantity) / float(batch_qty)


def classify_equivalence(has_history: bool, has_bom: bool) -> str:
    if has_history:
        return LEVEL_HISTORICAL_PRODUCTION
    if has_bom:
        return LEVEL_CURRENT_BOM
    return LEVEL_UNRESOLVED


# ---------------------------------------------------------------------------
# Equivalence build
# ---------------------------------------------------------------------------

def build_equivalence(fg_stocks: Iterable[FgStock],
                      ratios: dict[tuple[str, str], ComponentRatio],
                      fallback_bom: dict[tuple[str, str], float]) -> list[EquivalenceLine]:
    """For each FG stock row, multiply by component qty-per-FG."""
    lines: list[EquivalenceLine] = []
    for fg in fg_stocks:
        if fg.onhand <= 0:
            continue
        # components: prefer historical ratio, then current BOM fallback
        comps: set[str] = set()
        comps.update(k[1] for k in ratios if k[0] == fg.itemcode)
        comps.update(k[1] for k in fallback_bom if k[0] == fg.itemcode)
        for comp in sorted(comps):
            r = ratios.get((fg.itemcode, comp))
            if r is not None and r.is_resolved:
                ratio, method = r.qty_per_fg, r.method
                comp_uom, comp_class = r.component_uom, r.component_class
            else:
                fb = fallback_bom.get((fg.itemcode, comp))
                if fb is not None and fb > 0:
                    ratio, method = fb, LEVEL_CURRENT_BOM
                    comp_uom = comp_class = None
                else:
                    continue
            lines.append(EquivalenceLine(
                fg=fg.itemcode, fg_whs=fg.whscode, fg_stock=fg.onhand,
                fg_uom=fg.uom, component=comp, component_uom=comp_uom,
                component_class=comp_class, qty_per_fg=ratio, method=method,
                equivalent_qty=fg.onhand * ratio))
    return lines


# ---------------------------------------------------------------------------
# Terminal expansion (multi-level)
# ---------------------------------------------------------------------------

def expand_terminal(component_equiv: dict[str, float],
                    ratios: dict[tuple[str, str], ComponentRatio],
                    produced: set[str],
                    max_depth: int = 4) -> tuple[dict[str, float], dict[str, str]]:
    """Replace produced (semi) components with their own raw components.

    Returns (terminal_equiv, flags). Direct component qty for a produced
    component is moved into its sub-components; the semi itself is not double
    counted (removed from terminal layer). Cycle-guarded by max_depth.
    """
    terminal: dict[str, float] = dict(component_equiv)
    flags: dict[str, str] = {}
    for _ in range(max_depth):
        changed = False
        for comp in list(terminal.keys()):
            if comp not in produced:
                continue
            qty = terminal.pop(comp, 0.0)
            subs = [(k[1], r) for k, r in ratios.items()
                    if k[0] == comp and r.is_resolved]
            if not subs:
                # produced component with no resolved recipe: keep as semi
                terminal[comp] = terminal.get(comp, 0.0) + qty
                flags.setdefault(comp, FLAG_MULTILEVEL_PARTIAL)
                continue
            for sub, r in subs:
                terminal[sub] = terminal.get(sub, 0.0) + qty * r.qty_per_fg
            changed = True
        if not changed:
            break
    return terminal, flags


# ---------------------------------------------------------------------------
# Conservation / invariants
# ---------------------------------------------------------------------------

def global_equivalent_total(lines: Iterable[EquivalenceLine]) -> dict[str, float]:
    """Sum equivalent qty per component (natural UOM per component)."""
    out: dict[str, float] = {}
    for ln in lines:
        out[ln.component] = out.get(ln.component, 0.0) + ln.equivalent_qty
    return out


def transfer_conservation(before: dict[str, float], after: dict[str, float],
                          tolerance: float = 1e-6) -> tuple[bool, str]:
    """A FG transfer (same item, different warehouse) must preserve the
    global equivalent total per component."""
    all_keys = set(before) | set(after)
    for k in all_keys:
        if abs(before.get(k, 0.0) - after.get(k, 0.0)) > tolerance:
            return False, "TRANSFER_NOT_CONSERVED"
    return True, "TRANSFER_CONSERVED"


def uom_compatible(uoms: Iterable[str | None]) -> bool:
    distinct = {u for u in uoms if u}
    return len(distinct) <= 1


def detect_cycle(adj: dict[str, set[str]], start: str) -> bool:
    """DFS cycle detection in the FG->component graph."""
    seen: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str) -> bool:
        seen.add(node)
        stack.add(node)
        for nxt in adj.get(node, ()):
            if nxt in stack:
                return True
            if nxt not in seen and dfs(nxt):
                return True
        stack.discard(node)
        return False

    return dfs(start) if start in adj else False