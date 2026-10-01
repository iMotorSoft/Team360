"""Pure logic for the Saavedra raw-material coverage investigation.

Gate: TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1.

No SAP, no I/O. All functions are deterministic and unit-tested.

Semantics discovered against real SAP HANA (2026-09-24), TELCHI READ ONLY:

  Item classification is structural, not by name only:
    - produced     = appears in OWOR with Type='S'
    - bom_component= appears in ITT1.Code
    - bom_parent   = appears in ITT1.Father
    A BOM component that is not produced and is not packaging is a
    RAW_MATERIAL. Item-group membership (OITB) is corroborating evidence, never
    the sole discriminator (group 130 mixes packaging; group 129 mixes inputs).

  BOM quantity normalisation (validated in investigation/sql/current/equivalence):
    qty_per_parent_unit = ITT1.Quantity / OITT.Qauntity   (batch-normalised)
    ITT1.Uom is NULL -> the component quantity is expressed in the component's
    own inventory UoM (OITM.InvntryUom).

  Warehouse roles (investigation/sql/current/stock/warehouse_master_v1.sql and
    validation/stock/stock_domain.py) classify SAA-M1 as RAW_MATERIAL,
    SAA-P1 as PRODUCTION, SAA-T1 as FINISHED_GOOD, SAA-DAN as DAMAGED and
    SAA-T2/SAA-T3 as RECONDITIONED. Only RAW_MATERIAL warehouses count as
    Saavedra raw-material stock; damaged/reconditioned stock is never summed
    into available stock without an explicit operational rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Warehouse taxonomy (Saavedra subset, explicit evidence)
# ---------------------------------------------------------------------------

ROLE_RAW_MATERIAL = "RAW_MATERIAL"
ROLE_PRODUCTION = "PRODUCTION"
ROLE_FINISHED_GOOD = "FINISHED_PRODUCT"
ROLE_DAMAGED = "DAMAGED"
ROLE_RECONDITIONED = "RECONDITIONED"
ROLE_OTHER = "OTHER"

SAAVEDRA_WAREHOUSES: dict[str, tuple[str, str]] = {
    "SAA-DAN": (ROLE_DAMAGED, "Almacén Productos Dañados Saavedra"),
    "SAA-M1": (ROLE_RAW_MATERIAL, "Almacén Prod. a Granel Procesadora Saavedra"),
    "SAA-P1": (ROLE_PRODUCTION, "Almacén de Proceso Saavedra"),
    "SAA-T1": (ROLE_FINISHED_GOOD, "Almacén Producto Terminado Proc. Saavedra"),
    "SAA-T2": (ROLE_RECONDITIONED, "Almacén de Reacondicionado Saavedra"),
    "SAA-T3": (ROLE_RECONDITIONED, "Almacén de Reacondicionado Saavedra"),
}

# Saavedra production locations that consume raw material (OWOR.Warehouse).
SAAVEDRA_PRODUCTION_WAREHOUSES = ("SAA-P1", "SAA-T1", "SAA-M1", "SAA-T2", "SAA-T3")

# ---------------------------------------------------------------------------
# Item classification
# ---------------------------------------------------------------------------

CLASS_RAW_MATERIAL = "RAW_MATERIAL"
CLASS_PACKAGING_MATERIAL = "PACKAGING_MATERIAL"
CLASS_FINISHED_PRODUCT = "FINISHED_PRODUCT"
CLASS_FRACTIONATED_PRODUCT = "FRACTIONATED_PRODUCT"
CLASS_SEMI_FINISHED = "SEMI_FINISHED"
CLASS_OTHER_INPUT = "OTHER_INPUT"
CLASS_OTHER = "OTHER"
CLASS_UNKNOWN = "UNKNOWN"

# Item groups that mix raw inputs (see TELCHI OITB).
RAW_INPUT_GROUPS = {
    117,  # MAT. VIDRIO & LAB
    123,  # COMESTIBLES (colourants / flavour inputs)
    126,  # FRACCIONADO x Kg. (bulk, often intermediate)
    129,  # INSUMO
    131,  # MATERIAL LABORATORIO
    133,  # REACTIVO
}
FRACTIONATED_GROUPS = {125, 126, 127, 128}
PACKAGING_GROUP = 130

PACKAGING_RE = re.compile(
    r"FRASCO|TAPA|ETIQUETA|CAJA|ENVASE|BOLSA|PREFORM|CONTRA|GOTERO|SPRAY|"
    r"PULVERIZ|BOMBA|PRECINTA|PRECINTO|DOSIFIC|BIDON|TURRIL(?!\s*x)|BOTELLA|"
    r"CINTA|STICKER|TAPON|AMPOLLA|SACHET|BLISTER|POTE",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ItemFacts:
    itemcode: str
    itemname: str
    itms_grp: int | None
    group_name: str
    invnt_uom: str | None
    invnt_item: bool
    sell_item: bool
    prchse_item: bool
    is_produced: bool
    is_bom_component: bool
    is_bom_parent: bool
    has_saa_stock: bool = False


def looks_packaging(facts: ItemFacts) -> bool:
    """Structural packaging evidence: the dedicated group or the name pattern."""
    return facts.itms_grp == PACKAGING_GROUP or bool(PACKAGING_RE.search(facts.itemname or ""))


def classify_item(facts: ItemFacts) -> str:
    """Evidence-based, ordered classification. Never name-only for raw material."""
    # Produced items are finished / fractionated / semi.
    if facts.is_produced or facts.is_bom_parent:
        if facts.itms_grp in FRACTIONATED_GROUPS:
            return CLASS_FRACTIONATED_PRODUCT
        if facts.is_bom_parent:
            return CLASS_SEMI_FINISHED if not facts.sell_item else CLASS_FINISHED_PRODUCT
        return CLASS_FINISHED_PRODUCT if facts.sell_item else CLASS_SEMI_FINISHED

    # Non-produced BOM components are the raw-material / packaging backbone.
    if facts.is_bom_component:
        if looks_packaging(facts):
            return CLASS_PACKAGING_MATERIAL
        return CLASS_RAW_MATERIAL

    # Not a BOM component: classify residual inputs vs traded goods.
    if looks_packaging(facts):
        return CLASS_PACKAGING_MATERIAL
    if facts.itms_grp in RAW_INPUT_GROUPS:
        return CLASS_OTHER_INPUT
    if facts.invnt_item and (facts.sell_item or facts.prchse_item):
        return CLASS_OTHER
    return CLASS_UNKNOWN


# ---------------------------------------------------------------------------
# BOM normalisation + upward expansion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BomEdge:
    parent: str
    child: str
    quantity: float
    base_quantity: float

    @property
    def qty_per_parent_unit(self) -> float | None:
        if self.base_quantity:
            return self.quantity / self.base_quantity
        return None


def normalise_bom(edges: Iterable[BomEdge]) -> dict[str, dict[str, float]]:
    """Return children[parent][child] = qty of child per one parent unit.

    Multiple ITT1 rows for the same (parent, child) are summed. Parents whose
    OITT.Qauntity is missing/zero are recorded as unresolvable (no factor).
    """
    children: dict[str, dict[str, float]] = {}
    for edge in edges:
        factor = edge.qty_per_parent_unit
        if factor is None:
            continue
        bucket = children.setdefault(edge.parent, {})
        bucket[edge.child] = bucket.get(edge.child, 0.0) + factor
    return children


def build_parent_index(
    children: Mapping[str, Mapping[str, float]]
) -> dict[str, list[tuple[str, float]]]:
    """Invert children into parents[child] = [(parent, parent_qty_per_unit)]."""
    parents: dict[str, list[tuple[str, float]]] = {}
    for parent, comps in children.items():
        for child, factor in comps.items():
            parents.setdefault(child, []).append((parent, factor))
    return parents


def usage_per_unit(
    target: str,
    parents: Mapping[str, Sequence[tuple[str, float]]],
    max_depth: int = 8,
) -> dict[str, float]:
    """Return {ancestor: units of target consumed per one ancestor unit}.

    Walks the BOM upward from ``target`` through every parent path. Diamond
    convergence is summed (independent production events); cycles are bounded by
    ``max_depth`` and by never re-entering ``target``.
    """
    usage: dict[str, float] = {}
    # worklist of (node, accumulated_factor, depth)
    stack: list[tuple[str, float, int]] = [(target, 1.0, 0)]
    while stack:
        node, factor, depth = stack.pop()
        if depth >= max_depth:
            continue
        for parent, parent_factor in parents.get(node, ()):  # parent consumes node
            if parent == target:
                # cycle back to the target itself: do not self-amplify
                continue
            contribution = factor * parent_factor
            usage[parent] = usage.get(parent, 0.0) + contribution
            stack.append((parent, contribution, depth + 1))
    return usage


def derived_demand(
    target: str,
    parents: Mapping[str, Sequence[tuple[str, float]]],
    sales_by_item: Mapping[str, float],
    max_depth: int = 8,
) -> tuple[float, dict[str, float]]:
    """Commercial equivalent demand on ``target`` from all its ancestor sales."""
    usage = usage_per_unit(target, parents, max_depth=max_depth)
    per_product: dict[str, float] = {}
    total = 0.0
    for ancestor, factor in usage.items():
        qty = sales_by_item.get(ancestor)
        if not qty:
            continue
        equiv = qty * factor
        if equiv > 0:
            per_product[ancestor] = per_product.get(ancestor, 0.0) + equiv
            total += equiv
    return total, per_product


# ---------------------------------------------------------------------------
# Coverage and executive classification
# ---------------------------------------------------------------------------

RISK_QUIEBRE = "QUIEBRE"
RISK_CRITICO = "CRITICO"
RISK_ALTO = "ALTO"
RISK_ATENCION = "ATENCION"
RISK_OK = "OK"
RISK_NO_DEMAND = "NO_RECENT_DEMAND"

COVERAGE_THRESHOLD_DAYS = 60.0


def days_of_coverage(stock: float | None, avg_daily: float | None) -> float | None:
    """coverage = stock / avg_daily, only when the denominator is positive."""
    if stock is None or avg_daily is None:
        return None
    if avg_daily <= 0:
        return None
    return float(stock) / float(avg_daily)


def classify_coverage(coverage_days: float | None, stock: float) -> str:
    if stock <= 0:
        return RISK_QUIEBRE
    if coverage_days is None:
        return RISK_NO_DEMAND
    if coverage_days < 15:
        return RISK_CRITICO
    if coverage_days < 30:
        return RISK_ALTO
    if coverage_days < 60:
        return RISK_ATENCION
    return RISK_OK


def executive_basis(actual_consumption_qty: float, commercial_demand_qty: float) -> str:
    """Priority per prompt section 27: actual consumption first, then commercial."""
    if actual_consumption_qty > 0:
        return "ACTUAL_CONSUMPTION"
    if commercial_demand_qty > 0:
        return "COMMERCIAL_EQUIVALENT_DEMAND"
    return "NO_RECENT_DEMAND"


@dataclass
class CoverageResult:
    itemcode: str
    itemname: str
    item_class: str
    group_name: str
    uom: str | None
    stock: float
    committed: float
    on_order: float
    demand_window_days: int
    direct_sales_qty: float
    derived_demand_qty: float
    commercial_demand_qty: float
    actual_consumption_qty: float
    transfer_out_qty: float
    executive_basis: str
    coverage_days: float | None
    risk: str
    top_contributors: list[dict] = field(default_factory=list)

    @property
    def avg_daily_commercial(self) -> float:
        return self.commercial_demand_qty / self.demand_window_days if self.demand_window_days else 0.0

    @property
    def avg_daily_actual(self) -> float:
        return self.actual_consumption_qty / self.demand_window_days if self.demand_window_days else 0.0

    def to_dict(self) -> dict:
        return {
            "itemcode": self.itemcode,
            "itemname": self.itemname,
            "item_class": self.item_class,
            "group_name": self.group_name,
            "uom": self.uom,
            "stock": round(self.stock, 6),
            "committed": round(self.committed, 6),
            "on_order": round(self.on_order, 6),
            "available_after_commitments": round(self.stock - self.committed, 6),
            "demand_window_days": self.demand_window_days,
            "direct_sales_qty": round(self.direct_sales_qty, 6),
            "derived_demand_qty": round(self.derived_demand_qty, 6),
            "commercial_demand_qty": round(self.commercial_demand_qty, 6),
            "actual_consumption_qty": round(self.actual_consumption_qty, 6),
            "transfer_out_qty": round(self.transfer_out_qty, 6),
            "avg_daily_commercial": round(self.avg_daily_commercial, 6),
            "avg_daily_actual": round(self.avg_daily_actual, 6),
            "executive_basis": self.executive_basis,
            "coverage_days": round(self.coverage_days, 2) if self.coverage_days is not None else None,
            "risk": self.risk,
            "top_contributors": self.top_contributors,
        }


def build_result(
    facts: ItemFacts,
    item_class: str,
    stock: float,
    committed: float,
    on_order: float,
    demand_window_days: int,
    direct_sales_qty: float,
    derived_demand_qty: float,
    actual_consumption_qty: float,
    transfer_out_qty: float,
    contributors: Mapping[str, float],
    top_n: int = 3,
) -> CoverageResult:
    commercial = direct_sales_qty + derived_demand_qty
    basis = executive_basis(actual_consumption_qty, commercial)
    if basis == "ACTUAL_CONSUMPTION":
        avg_daily = actual_consumption_qty / demand_window_days if demand_window_days else 0.0
    else:
        avg_daily = commercial / demand_window_days if demand_window_days else 0.0
    coverage = days_of_coverage(stock, avg_daily)
    risk = classify_coverage(coverage, stock)

    total = sum(contributors.values()) or 1.0
    top = sorted(contributors.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    top_contributors = [
        {"itemcode": code, "equivalent_qty": round(qty, 6), "share_pct": round(100 * qty / total, 2)}
        for code, qty in top
    ]

    return CoverageResult(
        itemcode=facts.itemcode,
        itemname=facts.itemname,
        item_class=item_class,
        group_name=facts.group_name,
        uom=facts.invnt_uom,
        stock=stock,
        committed=committed,
        on_order=on_order,
        demand_window_days=demand_window_days,
        direct_sales_qty=direct_sales_qty,
        derived_demand_qty=derived_demand_qty,
        commercial_demand_qty=commercial,
        actual_consumption_qty=actual_consumption_qty,
        transfer_out_qty=transfer_out_qty,
        executive_basis=basis,
        coverage_days=coverage,
        risk=risk,
        top_contributors=top_contributors,
    )