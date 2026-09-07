"""TELCHI_PRODUCED_COMPONENT_DEPENDENCY_V1 — validator (READ ONLY on HANA).

Executes the produced-component dependency gate against real SAP:
  1. Item roles (produced / consumed / intersection)
  2. Dependency edges (parent -> produced component, historical)
  3. Current vs historical dependency drift
  4. Derived graph depth (cycle safe)
  5. Top shared intermediates + dependent products
  6. Real SAP case samples
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.production.produced_component_dependency_domain import (
    ItemRole,
    DependencyEdge,
    derive_graph_depth,
)


def load_roles(cur: Any) -> dict[str, ItemRole]:
    """Build item roles from real SAP."""
    # produced items with dates
    cur.execute('''SELECT O."ItemCode", MIN(N."DocDate"), MAX(N."DocDate"), COUNT(DISTINCT O."DocEntry")
      FROM "TELCHI"."OWOR" O JOIN "TELCHI"."IGN1" N
        ON N."BaseType"=202 AND N."BaseEntry"=O."DocEntry"
      GROUP BY O."ItemCode"''')
    produced = {r[0]: r for r in cur.fetchall()}

    # consumed components with dates
    cur.execute('''SELECT W."ItemCode", MIN(I."DocDate"), MAX(I."DocDate"), COUNT(DISTINCT W."DocEntry")
      FROM "TELCHI"."WOR1" W JOIN "TELCHI"."IGE1" I
        ON I."BaseType"=202 AND I."BaseEntry"=W."DocEntry" AND I."BaseLine"=W."LineNum" AND I."ItemCode"=W."ItemCode"
      GROUP BY W."ItemCode"''')
    consumed = {r[0]: r for r in cur.fetchall()}

    # current BOM parents
    cur.execute('SELECT DISTINCT "Father" FROM "TELCHI"."ITT1"')
    bom_parents = {r[0] for r in cur.fetchall()}

    # current recipe components
    cur.execute('SELECT DISTINCT "Code" FROM "TELCHI"."ITT1"')
    bom_components = {r[0] for r in cur.fetchall()}

    # historical recipe components (WOR1)
    cur.execute('SELECT DISTINCT "ItemCode" FROM "TELCHI"."WOR1"')
    hist_components = {r[0] for r in cur.fetchall()}

    all_items = set(produced) | set(consumed) | bom_parents | bom_components | hist_components
    roles: dict[str, ItemRole] = {}
    for item in all_items:
        p = produced.get(item)
        c = consumed.get(item)
        has_output = p is not None
        has_cons = c is not None
        roles[item] = ItemRole(
            item_code=item,
            is_current_bom_parent=item in bom_parents,
            is_historically_produced=item in produced,
            has_actual_output=has_output,
            is_current_recipe_component=item in bom_components,
            is_historical_recipe_component=item in hist_components,
            has_actual_component_consumption=has_cons,
            is_produced_component=has_output and has_cons,
            first_produced_at=p[1] if p else None,
            last_produced_at=p[2] if p else None,
            first_consumed_at=c[1] if c else None,
            last_consumed_at=c[2] if c else None,
        )
    return roles


def load_edges(cur: Any, roles: dict[str, ItemRole]) -> dict[tuple[str, str], DependencyEdge]:
    """Build aggregated dependency edges parent -> component from WOR1+IGE1."""
    cur.execute('''SELECT W."DocEntry", W."ItemCode", I."ItemCode" AS comp,
                         SUM(I."Quantity"), COUNT(DISTINCT I."DocEntry"),
                         MIN(I."DocDate"), MAX(I."DocDate"), O."ItemCode" AS parent
      FROM "TELCHI"."WOR1" W
      JOIN "TELCHI"."IGE1" I ON I."BaseType"=202 AND I."BaseEntry"=W."DocEntry"
        AND I."BaseLine"=W."LineNum" AND I."ItemCode"=W."ItemCode"
      JOIN "TELCHI"."OWOR" O ON O."DocEntry"=W."DocEntry"
      GROUP BY W."DocEntry", W."ItemCode", I."ItemCode", O."ItemCode"''')
    rows = cur.fetchall()

    # production order count per item
    prod_orders: dict[str, int] = {}
    cur.execute('''SELECT O."ItemCode", COUNT(DISTINCT O."DocEntry")
      FROM "TELCHI"."OWOR" O JOIN "TELCHI"."IGN1" N ON N."BaseType"=202 AND N."BaseEntry"=O."DocEntry"
      GROUP BY O."ItemCode"''')
    for r in cur.fetchall():
        prod_orders[r[0]] = r[1]

    edges: dict[tuple[str, str], DependencyEdge] = {}
    for r in rows:
        # r: DocEntry, WOR1.ItemCode, IGE1.ItemCode, SUM qty, distinct docs, min date, max date, parent
        parent = r[7]
        comp = r[2]
        qty = Decimal(str(r[3]))
        order_count = 1  # this row is one order
        key = (parent, comp)
        if key in edges:
            e = edges[key]
            e.historical_order_count += order_count
            e.actual_consumption_order_count += order_count
            e.actual_consumption_qty += qty
            if r[5] and (e.first_seen is None or r[5] < e.first_seen):
                e.first_seen = r[5]
            if r[6] and (e.last_seen is None or r[6] > e.last_seen):
                e.last_seen = r[6]
        else:
            cr = roles.get(comp)
            edges[key] = DependencyEdge(
                parent_item=parent, component_item=comp,
                historical_order_count=order_count, actual_consumption_order_count=order_count,
                actual_consumption_qty=qty,
                component_has_own_bom=(cr.is_current_bom_parent if cr else False),
                component_has_actual_production=(cr.has_actual_output if cr else False),
                component_output_order_count=prod_orders.get(comp, 0),
                first_seen=r[5], last_seen=r[6],
            )
    return edges


def main() -> int:
    conn, cur = connect()
    try:
        roles = load_roles(cur)
        edges = load_edges(cur, roles)

        produced_components = {i for i, r in roles.items() if r.is_produced_component}
        # edges where component is a produced component (the gate's core)
        produced_edges = {k: v for k, v in edges.items() if k[1] in produced_components}

        # fan-out per produced component
        fanout: dict[str, int] = defaultdict(int)
        for (parent, comp) in produced_edges:
            fanout[comp] += 1

        # fan-in per parent
        fanin: dict[str, int] = defaultdict(int)
        for (parent, comp) in produced_edges:
            fanin[parent] += 1

        # graph depth
        graph = derive_graph_depth(produced_edges, produced_components)

        # classification distribution
        cls_counter = Counter(r.classification for r in roles.values())

        # top shared intermediates
        top_shared = sorted(fanout.items(), key=lambda x: -x[1])[:20]

        # top dependent products
        top_dep = sorted(fanin.items(), key=lambda x: -x[1])[:15]

        # drift: historically used component not in current recipe
        drift_hist_only = []
        for (parent, comp), e in edges.items():
            cr = roles.get(comp)
            if cr and cr.is_historical_recipe_component and not cr.is_current_recipe_component:
                drift_hist_only.append({"parent": parent, "component": comp,
                                        "orders": e.historical_order_count})
        drift_cur_only = []
        for item, r in roles.items():
            if r.is_current_recipe_component and not r.is_historical_recipe_component:
                drift_cur_only.append(item)

        result = {
            "gate": "TELCHI_PRODUCED_COMPONENT_DEPENDENCY_V1",
            "summary": {
                "total_unique_produced_items": sum(1 for r in roles.values() if r.has_actual_output),
                "total_unique_component_items": sum(1 for r in roles.values() if r.has_actual_component_consumption),
                "total_produced_component_items": len(produced_components),
                "total_dependency_edges": len(edges),
                "total_produced_dependency_edges": len(produced_edges),
                "produced_components_with_current_bom": sum(1 for i in produced_components if roles[i].is_current_bom_parent),
                "produced_components_without_current_bom": sum(1 for i in produced_components if not roles[i].is_current_bom_parent),
                "produced_components_one_parent": sum(1 for c, n in fanout.items() if n == 1),
                "produced_components_multi_parent": sum(1 for c, n in fanout.items() if n > 1),
                "max_parent_count": max(fanout.values()) if fanout else 0,
                "max_derived_depth": max(graph["per_parent_depth"].values()) if graph["per_parent_depth"] else 0,
                "cycle_hits": graph["cycle_hits"],
                "self_dependencies": graph["self_dependencies"],
            },
            "item_role_classification": dict(cls_counter),
            "top_shared_intermediates": top_shared,
            "top_dependent_products": top_dep,
            "dependency_drift_historical_only_count": len(drift_hist_only),
            "dependency_drift_current_only_count": len(drift_cur_only),
            "graph_depth": graph,
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*70}")
        print("TELCHI_PRODUCED_COMPONENT_DEPENDENCY_V1")
        print(f"{'='*70}")
        s = result["summary"]
        print(f"\nSUMMARY:")
        for k, v in s.items():
            print(f"  {k:<45} {v:,}" if isinstance(v, int) else f"  {k:<45} {v}")
        print(f"\nROLE CLASSIFICATION:")
        for k, v in sorted(cls_counter.items()):
            print(f"  {k:<40} {v:,}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())