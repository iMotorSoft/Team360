"""Produced component dependency domain (pure logic + read-only SQL).

Semantics validated against real SAP (2026-08-26):
  - Flat independent recipes linked by ItemCode (Telchi does NOT store
    nested BOMs in SAP)
  - PRODUCED_COMPONENT = item with actual IGN1 output AND actual IGE1
    consumption as component (intersection: 255 items)
  - Dependency edge: parent product -> component item from WOR1/IGE1
    (EXACT_DOCUMENT_LINK downstream)
  - Component produced status: from OWOR/IGN1 (EXACT_ITEM_IDENTITY)
  - Derived graph (depth/expansion) is DERIVED, never presented as SAP BOM
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class ItemRole:
    """Production item role flags (non-mutually-exclusive)."""
    item_code: str
    is_current_bom_parent: bool
    is_historically_produced: bool
    has_actual_output: bool
    is_current_recipe_component: bool
    is_historical_recipe_component: bool
    has_actual_component_consumption: bool
    is_produced_component: bool
    first_produced_at: Any | None = None
    last_produced_at: Any | None = None
    first_consumed_at: Any | None = None
    last_consumed_at: Any | None = None

    @property
    def classification(self) -> str:
        produced = self.has_actual_output
        consumed = self.has_actual_component_consumption
        if produced and consumed:
            return "PRODUCED_AND_INTERMEDIATE"
        if produced:
            return "PRODUCED_FINAL_ONLY"
        if consumed and self.is_current_bom_parent:
            return "STRUCTURALLY_PRODUCIBLE_CONSUMED"
        if consumed:
            return "COMPONENT_ONLY"
        if self.is_current_bom_parent:
            return "BOM_PARENT_ONLY"
        return "UNKNOWN"

    def to_dict(self) -> dict:
        return {
            "item_code": self.item_code,
            "is_current_bom_parent": self.is_current_bom_parent,
            "is_historically_produced": self.is_historically_produced,
            "has_actual_output": self.has_actual_output,
            "is_current_recipe_component": self.is_current_recipe_component,
            "is_historical_recipe_component": self.is_historical_recipe_component,
            "has_actual_component_consumption": self.has_actual_component_consumption,
            "is_produced_component": self.is_produced_component,
            "classification": self.classification,
            "first_produced_at": str(self.first_produced_at)[:10] if self.first_produced_at else None,
            "last_produced_at": str(self.last_produced_at)[:10] if self.last_produced_at else None,
            "first_consumed_at": str(self.first_consumed_at)[:10] if self.first_consumed_at else None,
            "last_consumed_at": str(self.last_consumed_at)[:10] if self.last_consumed_at else None,
        }


@dataclass
class DependencyEdge:
    """parent product -> component item (canonical aggregated edge)."""
    parent_item: str
    component_item: str
    historical_order_count: int
    actual_consumption_order_count: int
    actual_consumption_qty: Decimal
    component_has_own_bom: bool
    component_has_actual_production: bool
    component_output_order_count: int
    first_seen: Any | None = None
    last_seen: Any | None = None
    dependency_depth: int = 1
    confirmation: str = "EXACT_DOCUMENT_LINK"

    def to_dict(self) -> dict:
        return {
            "parent_item": self.parent_item,
            "component_item": self.component_item,
            "historical_order_count": self.historical_order_count,
            "actual_consumption_order_count": self.actual_consumption_order_count,
            "actual_consumption_qty": str(self.actual_consumption_qty),
            "component_has_own_bom": self.component_has_own_bom,
            "component_has_actual_production": self.component_has_actual_production,
            "component_output_order_count": self.component_output_order_count,
            "first_seen": str(self.first_seen)[:10] if self.first_seen else None,
            "last_seen": str(self.last_seen)[:10] if self.last_seen else None,
            "dependency_depth": self.dependency_depth,
            "confirmation": self.confirmation,
        }


def derive_graph_depth(
    edges: dict[tuple[str, str], DependencyEdge],
    produced_components: set[str],
    max_depth: int = 10,
) -> dict[str, Any]:
    """Derive dependency depth via BFS with cycle protection.

    depth is the longest chain of produced components below a parent.
    Returns per-parent max depth and cycle/self-dependency counts.
    """
    # adjacency: parent -> components (only produced components expand further)
    adj: dict[str, set[str]] = {}
    for (parent, comp), edge in edges.items():
        adj.setdefault(parent, set()).add(comp)

    depths: dict[str, int] = {}
    cycle_count = 0
    self_count = 0
    for (parent, comp) in edges:
        if parent == comp:
            self_count += 1

    for parent in list(adj):
        # BFS for deepest chain
        visited: set[str] = set()
        queue = [(parent, 0)]
        max_d = 0
        while queue:
            node, d = queue.pop(0)
            if node in visited:
                cycle_count += 1
                continue
            visited.add(node)
            if d > max_d:
                max_d = d
            if d >= max_depth:
                continue
            for child in adj.get(node, set()):
                if child in produced_components:
                    queue.append((child, d + 1))
        depths[parent] = max_d

    return {"per_parent_depth": depths, "cycle_hits": cycle_count, "self_dependencies": self_count}