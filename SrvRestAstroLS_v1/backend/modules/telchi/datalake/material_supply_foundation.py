"""Conservative business projections for Material Supply Foundation V1.

This module consumes already captured, source-native Foundation rows. It never
opens SAP connections and never infers physical units, procurement origin, or
receipt lineage from descriptions.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping


ACTIVE_SAAVEDRA_MATERIAL = "ACTIVE_SAAVEDRA_MATERIAL"
HISTORICAL_SAAVEDRA_MATERIAL = "HISTORICAL_SAAVEDRA_MATERIAL"
GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA = "GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA"
UNRESOLVED_SAAVEDRA_RELEVANCE = "UNRESOLVED_SAAVEDRA_RELEVANCE"

# Exact exclusions are based on the validated 82-warehouse role census.  The
# Reference V2 ``warehouse_roles`` dataset is empty, so it cannot safely drive
# this decision yet.  Everything else must still exist in Reference to be
# considered usable by the caller.
NON_USABLE_WAREHOUSES = frozenset({
    # DAMAGED
    "2A-DAN", "CM-DAN", "LAB-DAN", "LPZ-DAN", "SAA-DAN", "LAB-T7", "2A-EXT",
    # RECONDITIONED (not automatically usable for supply)
    "SAA-T2", "SAA-T3",
    # RETURNS / EXPIRED / QUARANTINE
    "2A-DEV", "DMS-DEV", "LAB-T6", "LAB-T8", "LAB-C1", "LAB-P5",
    # TRANSIT
    "01", "SAP-R1", "SAL-TRS", "LAB-TRAN", "2A-TRAN",
})


@dataclass(frozen=True)
class SaavedraRelevance:
    classification: str
    basis: tuple[str, ...]
    confidence: str


@dataclass(frozen=True)
class WarehouseStock:
    target_on_hand: float
    target_usable_stock: float
    other_location_usable_stock: float
    global_usable_stock: float
    local_stockout: bool
    global_stockout: bool | None
    global_stock_status: str
    included_warehouses: tuple[str, ...]
    excluded_warehouses: tuple[str, ...]


@dataclass(frozen=True)
class ReceiptSummary:
    ordered_qty: float
    received_qty: float
    open_qty: float
    first_receipt_date: date | None
    last_receipt_date: date | None
    completion_date: date | None
    receipt_count: int


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def classify_issue_line(base_type: Any) -> str:
    """Classify inventory issue lineage without treating generic outflow as use."""
    try:
        from decimal import Decimal, InvalidOperation
        numeric = Decimal(str(base_type).strip())
        if not numeric.is_finite() or numeric != numeric.to_integral_value():
            return "UNKNOWN"
        value = int(numeric)
    except (TypeError, ValueError, InvalidOperation):
        return "UNKNOWN"
    if value == 202:  # SAP Business One production order (OWOR)
        return "PRODUCTION_CONSUMPTION"
    if value == 67:  # inventory transfer; never production consumption
        return "TRANSFER"
    return "UNKNOWN"


def aggregate_purchase_receipts(
    ordered_qty: float,
    receipts: Iterable[Mapping[str, Any]],
    *,
    quantity_field: str = "Quantity",
    date_field: str = "DocDate",
) -> ReceiptSummary:
    """Aggregate receipts already joined by exact PO DocEntry + LineNum lineage."""
    ordered = float(ordered_qty)
    receipt_rows = list(receipts)
    quantities = [float(row.get(quantity_field) or 0) for row in receipt_rows]
    dates = sorted(filter(None, (_date(row.get(date_field)) for row in receipt_rows)))
    received = sum(quantities)
    open_qty = max(0.0, ordered - received)
    completion = max(dates) if ordered > 0 and received >= ordered and dates else None
    return ReceiptSummary(
        ordered_qty=ordered,
        received_qty=received,
        open_qty=open_qty,
        first_receipt_date=dates[0] if dates else None,
        last_receipt_date=dates[-1] if dates else None,
        completion_date=completion,
        receipt_count=len(receipt_rows),
    )


def explicit_purchase_origin(raw_value: Any, *, local_values: Iterable[str], imported_values: Iterable[str]) -> str:
    """Map only explicitly verified SAP codes; unknown codes remain UNKNOWN."""
    value = str(raw_value or "").strip().upper()
    if value and value in {str(item).strip().upper() for item in local_values}:
        return "LOCAL"
    if value and value in {str(item).strip().upper() for item in imported_values}:
        return "IMPORTED"
    return "UNKNOWN"


def expected_arrival(
    *, line_date: Any = None, header_date: Any = None,
    historical_date: date | None = None,
) -> tuple[date | None, str]:
    """Choose ETA strictly by explicit line, explicit header, then supplied estimate."""
    for value, basis in ((line_date, "LINE_EXPLICIT"), (header_date, "HEADER_EXPLICIT")):
        parsed = _date(value)
        if parsed is not None:
            return parsed, basis
    if historical_date is not None:
        return historical_date, "HISTORICAL_LEAD_TIME_ESTIMATE"
    return None, "UNKNOWN"


def lead_time_profile(days: Iterable[int]) -> dict[str, Any]:
    """Return nearest-rank p50/p90 and sample count; no profile for empty samples."""
    values = sorted(int(value) for value in days if int(value) >= 0)
    if not values:
        return {"sample_count": 0, "p50_days": None, "p90_days": None}

    def percentile(p: float) -> int:
        # Nearest-rank percentile, deterministic for small samples.
        import math
        return values[max(0, math.ceil(p * len(values)) - 1)]

    return {"sample_count": len(values), "p50_days": percentile(0.50), "p90_days": percentile(0.90)}


def choose_coverage_basis(
    *, production_consumption_available: bool,
    commercial_equivalent_demand_available: bool,
) -> str:
    if production_consumption_available:
        return "ACTUAL_PRODUCTION_CONSUMPTION"
    if commercial_equivalent_demand_available:
        return "COMMERCIAL_EQUIVALENT_DEMAND"
    return "UNRESOLVED"


def aggregate_origin_profile(origins: Iterable[str]) -> str:
    values = {str(value).upper() for value in origins if str(value).upper() in {"LOCAL", "IMPORTED"}}
    if values == {"LOCAL"}:
        return "LOCAL"
    if values == {"IMPORTED"}:
        return "IMPORTED"
    if values == {"LOCAL", "IMPORTED"}:
        return "MIXED"
    return "UNKNOWN"


def classify_saavedra_relevance(
    *,
    item_active: bool | None,
    current_target_stock: bool,
    recent_target_movement: bool,
    recent_linked_production_consumption: bool,
    recent_saavedra_bom_use: bool,
    open_po_to_target: bool,
    historical_target_movement: bool,
    historical_linked_production_consumption: bool,
    historical_saavedra_bom_use: bool,
) -> SaavedraRelevance:
    """Classify Saavedra relevance from exact operational evidence.

    ACTIVE always combines item activity with operational evidence.  An exact
    production issue linked by BaseType=202 to a Saavedra production order is
    authoritative by itself because it combines issue, order and site signals.
    Otherwise at least two current operational signals are required.  Unknown
    item status fails closed and inactive items can only be historical.
    """
    current_basis: list[str] = []
    if current_target_stock:
        current_basis.append("CURRENT_SAA_M1_STOCK")
    if recent_target_movement:
        current_basis.append("RECENT_SAA_M1_MOVEMENT")
    if recent_linked_production_consumption:
        current_basis.append("RECENT_LINKED_SAAVEDRA_PRODUCTION_CONSUMPTION")
    if recent_saavedra_bom_use:
        current_basis.append("RECENT_SAAVEDRA_PRODUCTION_BOM")
    if open_po_to_target:
        current_basis.append("OPEN_PO_TO_SAA_M1")

    historical_basis: list[str] = []
    if historical_target_movement:
        historical_basis.append("HISTORICAL_SAA_M1_MOVEMENT")
    if historical_linked_production_consumption:
        historical_basis.append("HISTORICAL_LINKED_SAAVEDRA_PRODUCTION_CONSUMPTION")
    if historical_saavedra_bom_use:
        historical_basis.append("HISTORICAL_SAAVEDRA_PRODUCTION_BOM")

    if item_active is True and (
        recent_linked_production_consumption or len(current_basis) >= 2
    ):
        confidence = "HIGH" if recent_linked_production_consumption else "SUPPORTED"
        return SaavedraRelevance(ACTIVE_SAAVEDRA_MATERIAL, tuple(current_basis), confidence)
    if current_basis and item_active is None:
        return SaavedraRelevance(
            UNRESOLVED_SAAVEDRA_RELEVANCE,
            tuple(current_basis + ["ITEM_ACTIVITY_STATUS_UNRESOLVED"]),
            "UNRESOLVED",
        )
    if historical_basis or current_basis:
        basis = historical_basis + current_basis
        if item_active is False:
            basis.append("ITEM_INACTIVE")
        return SaavedraRelevance(HISTORICAL_SAAVEDRA_MATERIAL, tuple(basis), "SUPPORTED")
    if item_active is not None:
        suffix = "ITEM_ACTIVE_NO_SAA_EVIDENCE" if item_active else "ITEM_INACTIVE_NO_SAA_EVIDENCE"
        return SaavedraRelevance(
            GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA, (suffix,), "HIGH"
        )
    return SaavedraRelevance(
        UNRESOLVED_SAAVEDRA_RELEVANCE, ("ITEM_AND_SAAVEDRA_EVIDENCE_UNRESOLVED",), "UNRESOLVED"
    )


def aggregate_warehouse_stock(
    rows: Iterable[Mapping[str, Any]],
    *,
    target_warehouse: str = "SAA-M1",
    valid_warehouses: Iterable[str] | None = None,
    inventory_uom_resolved: bool = True,
) -> WarehouseStock:
    """Aggregate usable stock without aliasing target and global semantics.

    OITW quantities for one ItemCode share its inventory UoM.  If that UoM is
    unresolved, the numeric diagnostic is retained but exact global stockout is
    deliberately UNKNOWN.
    """
    valid = {str(value) for value in valid_warehouses} if valid_warehouses is not None else None
    target_on_hand = 0.0
    target_usable = 0.0
    other_usable = 0.0
    included: set[str] = set()
    excluded: set[str] = set()
    for row in rows:
        warehouse = str(row.get("whs_code") or "")
        on_hand = float(row.get("on_hand") or 0)
        committed = float(row.get("is_commited") or 0)
        usable = max(0.0, on_hand - committed)
        if warehouse == target_warehouse:
            target_on_hand += on_hand
            target_usable += usable
            included.add(warehouse)
            continue
        if not warehouse or warehouse in NON_USABLE_WAREHOUSES or (valid is not None and warehouse not in valid):
            if warehouse:
                excluded.add(warehouse)
            continue
        other_usable += usable
        included.add(warehouse)
    global_usable = target_usable + other_usable
    return WarehouseStock(
        target_on_hand=target_on_hand,
        target_usable_stock=target_usable,
        other_location_usable_stock=other_usable,
        global_usable_stock=global_usable,
        local_stockout=target_usable <= 0,
        global_stockout=(global_usable <= 0) if inventory_uom_resolved else None,
        global_stock_status="CALCULATED" if inventory_uom_resolved else "UNRESOLVED",
        included_warehouses=tuple(sorted(included)),
        excluded_warehouses=tuple(sorted(excluded)),
    )


def group_receipts_by_po_line(
    receipts: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    """Group only fully identified PO-line lineage; incomplete lineage is omitted."""
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in receipts:
        if row.get("BaseEntry") is None or row.get("BaseLine") is None:
            continue
        if str(row.get("BaseType")) not in {"22", "22.0"}:
            continue
        grouped[(str(row["BaseEntry"]), str(row["BaseLine"]))].append(row)
    return dict(grouped)
