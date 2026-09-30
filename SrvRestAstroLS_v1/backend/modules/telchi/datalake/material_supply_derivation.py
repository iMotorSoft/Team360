"""TELCHI_DATALAKE_MATERIAL_SUPPLY_DERIVATION_V1 — deterministic business kernels.

This module owns the *pure* Material Supply derivations.  It never opens SAP.
Inputs are already captured source-native rows (Fact Capture V1 + Purchasing
Lineage V1) and Foundation component rows (OITW/Sales/Credit Memo).  Every
function is deterministic and unit-testable; the runner performs I/O.

Semantics deliberately kept conservative:

* Production consumption only counts ``BaseType=202`` issue lines; anything else
  is ``TRANSFER``/``OTHER``/``UNRESOLVED`` and is never treated as consumption.
* BOM equivalent demand walks parents upward with diamond summation and cycle
  protection; it never double counts a parent path.
* Origin uses only explicitly verified ``U_TIPOCOMPRA`` metadata
  (``IMP`` -> IMPORTED, ``LP``/``SAA`` -> LOCAL); undocumented codes stay
  ``UNKNOWN``.
* Coverage uses actual consumption first, then commercial equivalent demand.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Mapping

from .material_supply import (
    Density,
    Dimension,
    Unit,
    calculate_coverage,
    coverage_band,
    convert,
    DEFAULT_UNITS,
)
from .material_supply_foundation import (
    UNRESOLVED_SAAVEDRA_RELEVANCE,
    aggregate_warehouse_stock,
)

# ---------------------------------------------------------------------------
# Origin (metadata-verified UFD1 values for OPOR.CUFD FieldID=49 TIPOCOMPRA)
# ---------------------------------------------------------------------------

_ORIGIN_BY_CODE: Mapping[str, str] = {
    "IMP": "IMPORTED",           # UFD1: Importación
    "LP": "LOCAL",               # UFD1: Local Producción
    "SAA": "LOCAL",              # UFD1: Local Saavedra
    "MED": "UNKNOWN",            # UFD1: Medicamentos (no physical origin)
    "SERV": "UNKNOWN",           # UFD1: Servicios (not a material)
}


def classify_origin(code: Any) -> str:
    """Map only metadata-verified codes; every other value stays UNKNOWN."""
    value = str(code or "").strip().upper()
    return _ORIGIN_BY_CODE.get(value, "UNKNOWN")


def aggregate_origin_profile(origins: Iterable[str]) -> str:
    values = {str(v).upper() for v in origins if str(v).upper() in {"LOCAL", "IMPORTED"}}
    if values == {"LOCAL"}:
        return "LOCAL"
    if values == {"IMPORTED"}:
        return "IMPORTED"
    if values == {"LOCAL", "IMPORTED"}:
        return "MIXED"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Production consumption
# ---------------------------------------------------------------------------


def classify_issue_line(base_type: Any) -> str:
    try:
        value = int(float(base_type))
    except (TypeError, ValueError):
        return "UNKNOWN"
    if value == 202:
        return "PRODUCTION_CONSUMPTION"
    if value == 67:
        return "TRANSFER"
    return "OTHER"


def build_actual_consumption(
    issue_lines: Iterable[Mapping[str, Any]],
    *,
    window_start: date,
    window_end: date,
) -> list[dict[str, Any]]:
    """Sum 202 production consumption per item inside the business window."""
    totals: dict[str, float] = defaultdict(float)
    classifications: dict[str, set[str]] = defaultdict(set)
    for line in issue_lines:
        classification = classify_issue_line(line.get("BaseType"))
        if classification != "PRODUCTION_CONSUMPTION":
            continue
        try:
            doc_date = date.fromisoformat(str(line.get("DocDate"))[:10])
        except (TypeError, ValueError):
            continue
        if not (window_start <= doc_date <= window_end):
            continue
        item = str(line.get("ItemCode") or "")
        if not item:
            continue
        totals[item] += float(line.get("Quantity") or 0)
        classifications[item].add("PRODUCTION_CONSUMPTION")
    return [
        {
            "item_code": item,
            "actual_consumption_qty": round(qty, 6),
            "consumption_basis": "PRODUCTION_CONSUMPTION",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        }
        for item, qty in sorted(totals.items())
    ]


# ---------------------------------------------------------------------------
# BOM equivalent demand
# ---------------------------------------------------------------------------


def split_bom_raw_materials(
    lines: Iterable[Mapping[str, Any]], base_by_parent: Mapping[str, float]
) -> list[dict[str, Any]]:
    """Return BOM edges with a parent-unit factor, dropping unusable parents."""
    edges = []
    for line in lines:
        parent = str(line.get("Father") or "")
        child = str(line.get("Code") or "")
        if not parent or not child:
            continue
        base = float(base_by_parent.get(parent) or 0)
        if base <= 0:
            continue
        edges.append({
            "parent": parent,
            "child": child,
            "quantity": float(line.get("Quantity") or 0),
            "qty_per_parent_unit": float(line.get("Quantity") or 0) / base,
        })
    return edges


def build_parent_index(edges: Iterable[Mapping[str, Any]]) -> dict[str, list[tuple[str, float]]]:
    parents: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for edge in edges:
        parents[str(edge["child"])].append((str(edge["parent"]), float(edge["qty_per_parent_unit"])))
    return dict(parents)


def usage_per_unit(
    target: str,
    parents: Mapping[str, list[tuple[str, float]]],
    *,
    max_depth: int = 10,
) -> dict[str, float]:
    usage: dict[str, float] = defaultdict(float)
    stack: list[tuple[str, float, int]] = [(target, 1.0, 0)]
    while stack:
        node, factor, depth = stack.pop()
        if depth >= max_depth:
            continue
        for parent, parent_factor in parents.get(node, ()):
            if parent == target:
                continue  # cycle back to target: never self-amplify
            contribution = factor * parent_factor
            usage[parent] += contribution
            stack.append((parent, contribution, depth + 1))
    return dict(usage)


def build_equivalent_demand(
    *,
    raw_materials: Iterable[str],
    parents: Mapping[str, list[tuple[str, float]]],
    sales_by_item: Mapping[str, float],
    credit_by_item: Mapping[str, float],
    window_start: date,
    window_end: date,
    max_depth: int = 10,
) -> list[dict[str, Any]]:
    """DIRECT raw-material demand + DERIVED product-equivalent demand."""
    results: list[dict[str, Any]] = []
    for material in sorted(set(raw_materials)):
        direct = float(sales_by_item.get(material, 0.0))
        direct_credit = float(credit_by_item.get(material, 0.0))
        derived = 0.0
        contributors: dict[str, float] = {}
        for ancestor, factor in usage_per_unit(material, parents, max_depth=max_depth).items():
            qty = float(sales_by_item.get(ancestor, 0.0)) - float(credit_by_item.get(ancestor, 0.0))
            if qty == 0:
                continue
            equiv = qty * factor
            derived += equiv
            contributors[ancestor] = contributors.get(ancestor, 0.0) + equiv
        commercial = direct - direct_credit + derived
        top = sorted(contributors.items(), key=lambda kv: kv[1], reverse=True)[:3]
        results.append({
            "item_code": material,
            "direct_raw_material_demand": round(direct - direct_credit, 6),
            "derived_product_raw_material_equivalent": round(derived, 6),
            "commercial_daily_equivalent_basis_qty": round(commercial, 6),
            "demand_window_start": window_start.isoformat(),
            "demand_window_end": window_end.isoformat(),
            "top_contributors": [{"item_code": c, "equivalent_qty": round(q, 6)} for c, q in top],
        })
    return results


# ---------------------------------------------------------------------------
# Open purchase pipeline
# ---------------------------------------------------------------------------


def build_open_purchase_pipeline(
    po_lines: Iterable[Mapping[str, Any]],
    receipt_lineage_records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Per PO line: ordered/open (source-native), receipts and defensible lineage."""
    received: dict[tuple[str, str], float] = defaultdict(float)
    lineage_types: dict[tuple[str, str], set[str]] = defaultdict(set)
    first_receipt: dict[tuple[str, str], str] = {}
    for record in receipt_lineage_records:
        if record.get("po_docentry") is None:
            continue
        key = (str(record["po_docentry"]), str(record["po_linenum"]))
        try:
            received[key] += float(record.get("receipt_quantity") or 0)
        except (TypeError, ValueError):
            pass
        lineage_types[key].add(str(record.get("lineage_path_type")))
        doc_date = str(record.get("receipt_docdate") or "")[:10]
        if doc_date and (key not in first_receipt or doc_date < first_receipt[key]):
            first_receipt[key] = doc_date
    rows: list[dict[str, Any]] = []
    for line in po_lines:
        key = (str(line.get("DocEntry")), str(line.get("LineNum")))
        ordered = float(line.get("Quantity") or 0)
        open_qty = line.get("OpenQty")
        origin = classify_origin(line.get("U_TIPOCOMPRA"))
        lineage = sorted(lineage_types.get(key, set()))
        if "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE" in lineage:
            lineage_status = "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"
        elif "DIRECT_PO_RECEIPT" in lineage:
            lineage_status = "DIRECT_PO_RECEIPT"
        elif lineage:
            lineage_status = "OTHER_DOCUMENT_CHAIN"
        else:
            lineage_status = "NO_RECEIPT_LINK"
        rows.append({
            "po_docentry": key[0],
            "po_linenum": key[1],
            "po_docdate": str(line.get("DocDate"))[:10] if line.get("DocDate") else None,
            "item_code": line.get("ItemCode"),
            "supplier": line.get("CardCode"),
            "destination_warehouse": line.get("WhsCode"),
            "ordered_qty": ordered,
            "received_qty_supported": round(received.get(key, 0.0), 6),
            "open_qty_source": float(open_qty) if open_qty not in (None, "") else None,
            "expected_date": str(line.get("ShipDate"))[:10] if line.get("ShipDate") else None,
            "expected_arrival_source": "LINE_EXPLICIT" if line.get("ShipDate") else "UNKNOWN",
            "receipt_lineage_status": lineage_status,
            "receipt_lineage_confidence": "SOURCE_NATIVE" if lineage else "NONE",
            "procurement_origin": origin,
            "first_receipt_date": first_receipt.get(key),
            "doc_currency": line.get("DocCur"),
        })
    return rows


# ---------------------------------------------------------------------------
# Lead time profiles
# ---------------------------------------------------------------------------


def percentile(values: list[int], p: float) -> int:
    ordered = sorted(values)
    import math
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def build_lead_time_profiles(samples: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate defensible samples into ITEM+SUPPLIER+ORIGIN .. ORIGIN profiles."""
    groups: dict[tuple[str, ...], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for sample in samples:
        days = int(sample["order_to_receipt_days"])
        item = str(sample.get("itemcode") or "UNKNOWN")
        supplier = str(sample.get("supplier") or "UNKNOWN")
        origin = classify_origin(sample.get("origin_code"))
        groups[("ITEM+SUPPLIER+ORIGIN", item, supplier, origin)]["days"].append(days)
        groups[("ITEM+ORIGIN", item, "*", origin)]["days"].append(days)
        groups[("SUPPLIER+ORIGIN", "*", supplier, origin)]["days"].append(days)
        groups[("ORIGIN", "*", "*", origin)]["days"].append(days)
    rows: list[dict[str, Any]] = []
    for (basis, item, supplier, origin), bucket in groups.items():
        days = bucket["days"]
        rows.append({
            "lead_time_basis": basis,
            "item_code": item,
            "supplier": supplier,
            "procurement_origin": origin,
            "sample_count": len(days),
            "p50_days": percentile(days, 0.50),
            "p90_days": percentile(days, 0.90),
            "lineage_coverage": "DEFENSIBLE",
            "confidence": "HIGH" if len(days) >= 10 else ("MEDIUM" if len(days) >= 3 else "LOW"),
        })
    return rows


def select_lead_time(
    profiles: list[Mapping[str, Any]], item: str, supplier: str, origin: str
) -> dict[str, Any]:
    """Precedence lookup: ITEM+SUPPLIER+ORIGIN -> ITEM+ORIGIN -> SUPPLIER+ORIGIN -> ORIGIN."""
    wanted = [
        ("ITEM+SUPPLIER+ORIGIN", item, supplier, origin),
        ("ITEM+ORIGIN", item, "*", origin),
        ("SUPPLIER+ORIGIN", "*", supplier, origin),
        ("ORIGIN", "*", "*", origin),
    ]
    for basis, i, s, o in wanted:
        for row in profiles:
            if (row["lead_time_basis"], row["item_code"], row["supplier"], row["procurement_origin"]) == (basis, i, s, o):
                return {"lead_time_days": row["p50_days"], "lead_time_basis": basis,
                        "sample_count": row["sample_count"], "lead_time_confidence": row["confidence"]}
    return {"lead_time_days": None, "lead_time_basis": "UNAVAILABLE", "sample_count": 0,
            "lead_time_confidence": "UNAVAILABLE"}


# ---------------------------------------------------------------------------
# Material supply status
# ---------------------------------------------------------------------------


def build_supply_status(
    *,
    stock_rows: Iterable[Mapping[str, Any]],
    items: Mapping[str, Mapping[str, Any]],
    actual_consumption: Mapping[str, float],
    equivalent_demand: Mapping[str, float],
    open_pipeline: Iterable[Mapping[str, Any]],
    lead_profiles: list[Mapping[str, Any]],
    source_as_of: str,
    window_days: int,
    saavedra_evidence: Mapping[str, Mapping[str, Any]] | None = None,
    valid_warehouses: Iterable[str] | None = None,
    target_warehouse: str = "SAA-M1",
) -> list[dict[str, Any]]:
    """Combine stock, demand, open PO, relevance and independent stockouts."""
    stock_by_item: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    committed: dict[str, float] = defaultdict(float)
    on_order: dict[str, float] = defaultdict(float)
    for row in stock_rows:
        item = str(row.get("item_code") or "")
        stock_by_item[item].append(row)
        if str(row.get("whs_code") or "") == target_warehouse:
            committed[item] += float(row.get("is_commited") or 0)
            on_order[item] += float(row.get("on_order") or 0)
    po_by_item: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in open_pipeline:
        po_by_item[str(row.get("item_code") or "")].append(row)

    results: list[dict[str, Any]] = []
    for item in sorted(items):
        item_meta = items.get(item, {})
        uom_resolved = bool(item_meta.get("inventory_uom"))
        stock_summary = aggregate_warehouse_stock(
            stock_by_item.get(item, ()), target_warehouse=target_warehouse,
            valid_warehouses=valid_warehouses, inventory_uom_resolved=uom_resolved,
        )
        stock = stock_summary.target_usable_stock
        actual = float(actual_consumption.get(item, 0.0))
        commercial = float(equivalent_demand.get(item, 0.0))
        actual_daily = actual / window_days if window_days else 0.0
        commercial_daily = commercial / window_days if window_days else 0.0
        if actual_daily > 0:
            basis = "ACTUAL_PRODUCTION_CONSUMPTION"
            daily = actual_daily
        elif commercial_daily > 0:
            basis = "COMMERCIAL_EQUIVALENT_DEMAND"
            daily = commercial_daily
        else:
            basis = "UNRESOLVED"
            daily = 0.0
        if uom_resolved:
            coverage = calculate_coverage(
                stock,
                str(item_meta["inventory_uom"]),
                daily,
                str(item_meta["inventory_uom"]),
                units=_same_unit_units(item_meta.get("inventory_uom")),
            )
        else:
            from .material_supply import Coverage
            coverage = Coverage(None, "UNKNOWN_UOM", "UNRESOLVED", "UNRESOLVED")
        band = coverage_band(coverage.days) if coverage.days is not None else "UNRESOLVED"
        origin = aggregate_origin_profile(str(p.get("procurement_origin")) for p in po_by_item.get(item, []))
        open_lines = [p for p in po_by_item.get(item, []) if float(p.get("open_qty_source") or 0) > 0]
        open_po_qty = sum(float(p.get("open_qty_source") or 0) for p in open_lines)
        expected_dates = sorted(str(p.get("expected_date")) for p in open_lines if p.get("expected_date"))
        destinations = sorted({str(p.get("destination_warehouse")) for p in open_lines if p.get("destination_warehouse")})
        supplier = next((str(p.get("supplier")) for p in po_by_item.get(item, []) if p.get("supplier")), "UNKNOWN")
        lt = select_lead_time(list(lead_profiles), item, supplier, origin)
        replenishment_gap = None
        if coverage.days is not None and lt["lead_time_days"] is not None:
            replenishment_gap = round(coverage.days - lt["lead_time_days"], 3)
        eta_days = _days_until(source_as_of, expected_dates[0] if expected_dates else None)
        supply_risk = _supply_risk(
            band, coverage.days, lt["lead_time_days"], open_po_qty, destinations, origin, eta_days
        )
        relevance = dict((saavedra_evidence or {}).get(item, {}))
        results.append({
            "ItemCode": item,
            "material_name": item_meta.get("canonical_name") or item,
            "material_class": item_meta.get("material_class") or "UNKNOWN",
            "is_raw_material": item_meta.get("material_class") == "RAW_MATERIAL",
            "warehouse": item_meta.get("warehouse") or "SAA-M1",
            "production_site": "SAAVEDRA",
            "inventory_uom": item_meta.get("inventory_uom"),
            "current_stock": round(stock_summary.target_on_hand, 6),
            "committed": round(committed[item], 6),
            "target_warehouse_usable_stock": round(stock_summary.target_usable_stock, 6),
            "other_location_usable_stock": round(stock_summary.other_location_usable_stock, 6),
            "global_usable_stock": round(stock_summary.global_usable_stock, 6),
            "on_order": round(on_order[item], 6),
            "actual_daily_consumption": round(actual_daily, 6),
            "commercial_daily_equivalent_demand": round(commercial_daily, 6),
            "coverage_basis": basis,
            "coverage_days": round(coverage.days, 2) if coverage.days is not None else None,
            "coverage_confidence": coverage.confidence,
            "coverage_band": band,
            "procurement_profile": origin,
            "lead_time_days": lt["lead_time_days"],
            "lead_time_basis": lt["lead_time_basis"],
            "lead_time_confidence": lt["lead_time_confidence"],
            "open_po_qty": round(open_po_qty, 6),
            "open_po_expected_date": expected_dates[0] if expected_dates else None,
            "open_po_destination": destinations[0] if destinations else None,
            "open_po_origin": origin,
            # Backward-compatible alias; V2 consumers use the explicit usable field.
            "other_location_stock": round(stock_summary.other_location_usable_stock, 6),
            "local_stockout": stock_summary.local_stockout,
            "global_stockout": stock_summary.global_stockout,
            "global_stock_status": stock_summary.global_stock_status,
            "saavedra_relevance": relevance.get("saavedra_relevance", UNRESOLVED_SAAVEDRA_RELEVANCE),
            "saavedra_relevance_basis": relevance.get("saavedra_relevance_basis", "EVIDENCE_NOT_PROVIDED"),
            "saavedra_relevance_confidence": relevance.get("saavedra_relevance_confidence", "UNRESOLVED"),
            "item_activity_status": relevance.get("item_activity_status", "UNRESOLVED"),
            "saa_m1_history": bool(relevance.get("saa_m1_history", False)),
            "recent_saa_m1_movement": bool(relevance.get("recent_saa_m1_movement", False)),
            "recent_saa_consumption": bool(relevance.get("recent_saa_consumption", False)),
            "saa_production_link": bool(relevance.get("saa_production_link", False)),
            "saa_active_bom": bool(relevance.get("saa_active_bom", False)),
            "open_po_to_saa": bool(relevance.get("open_po_to_saa", False)),
            "replenishment_gap_days": replenishment_gap,
            "supply_risk": supply_risk,
            "source_as_of": source_as_of,
        })
    return results


def _same_unit_units(uom: Any) -> dict[str, Unit]:
    """Treat one item's own invariant inventory unit as a COUNT unit.

    Reference exposes canonical UoM ids (``unit_of_measure_<hash>``) rather than
    SAP codes.  Stock and demand for one item are always expressed in that same
    unit, so an identity conversion is dimensionally safe; this never performs a
    MASS<->VOLUME conversion (that still requires a validated density).
    """
    units = dict(DEFAULT_UNITS)
    code = str(uom or "").strip().upper()
    if code and code not in units:
        units[code] = Unit(code, Dimension.COUNT, 1.0)
    return units


def _days_until(reference: str | None, expected: str | None) -> int | None:
    from datetime import date
    if not expected:
        return None
    try:
        ref = date.fromisoformat(str(reference)[:10]) if reference else None
        exp = date.fromisoformat(str(expected)[:10])
    except ValueError:
        return None
    if ref is None:
        return None
    return (exp - ref).days


def _supply_risk(
    band: str,
    coverage_days: float | None,
    lead_time_days: float | None,
    open_po_qty: float,
    destinations: list[str],
    origin: str,
    eta_days: int | None = None,
) -> str:
    if coverage_days is None:
        return "UNKNOWN"
    if coverage_days <= 0:
        if open_po_qty <= 0:
            return "NO_INBOUND"
        if eta_days is not None and eta_days < 0:
            return "INBOUND_TOO_LATE"
        return "INBOUND_TOO_LATE"
    if lead_time_days is None:
        return "UNKNOWN"
    if coverage_days <= lead_time_days:
        if open_po_qty <= 0:
            return "NO_INBOUND"
        if not destinations:
            return "INBOUND_DESTINATION_UNCERTAIN"
        if eta_days is None:
            return "INBOUND_DESTINATION_UNCERTAIN"
        if eta_days < 0:
            return "PARTIALLY_MITIGATED"
        if eta_days <= coverage_days:
            return "MITIGATED"
        return "PARTIALLY_MITIGATED"
    return "MANAGEABLE"


__all__ = [
    "classify_origin",
    "aggregate_origin_profile",
    "classify_issue_line",
    "build_actual_consumption",
    "split_bom_raw_materials",
    "build_parent_index",
    "usage_per_unit",
    "build_equivalent_demand",
    "build_open_purchase_pipeline",
    "build_lead_time_profiles",
    "select_lead_time",
    "build_supply_status",
    "percentile",
    "_ORIGIN_BY_CODE",
]