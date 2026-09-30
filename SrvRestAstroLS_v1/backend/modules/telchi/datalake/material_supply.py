"""Fail-closed deterministic primitives for Telchi Material Supply.

This module deliberately contains no SAP access, I/O, inference, or publication
logic. Source capture and coherent Foundation integration are separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable, Mapping


class Dimension(str, Enum):
    MASS = "MASS"
    VOLUME = "VOLUME"
    COUNT = "COUNT"
    UNKNOWN = "UNKNOWN"


class ConversionStatus(str, Enum):
    EXACT = "EXACT"
    DENSITY_VALIDATED = "DENSITY_VALIDATED"
    UNKNOWN_UOM = "UNKNOWN_UOM"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    DENSITY_REQUIRED = "DENSITY_REQUIRED"
    INVALID_VALUE = "INVALID_VALUE"


@dataclass(frozen=True)
class Unit:
    code: str
    dimension: Dimension
    to_canonical: float | None


@dataclass(frozen=True)
class Density:
    """Validated density expressed as kg/L; never sourced by this module."""
    kg_per_l: float
    validated: bool
    source: str | None = None


@dataclass(frozen=True)
class Conversion:
    source_value: float
    source_unit: str
    target_value: float | None
    target_unit: str
    status: ConversionStatus
    conversion_factor: float | None = None
    density_value: float | None = None
    density_source: str | None = None

    @property
    def compatible(self) -> bool:
        return self.target_value is not None and self.status in {
            ConversionStatus.EXACT, ConversionStatus.DENSITY_VALIDATED
        }


DEFAULT_UNITS: Mapping[str, Unit] = {
    "KG": Unit("KG", Dimension.MASS, 1.0),
    "G": Unit("G", Dimension.MASS, 0.001),
    "L": Unit("L", Dimension.VOLUME, 1.0),
    "ML": Unit("ML", Dimension.VOLUME, 0.001),
    "UNIT": Unit("UNIT", Dimension.COUNT, 1.0),
    "COUNT": Unit("COUNT", Dimension.COUNT, 1.0),
}


def convert(
    value: float,
    source_unit: str,
    target_unit: str,
    *,
    units: Mapping[str, Unit] = DEFAULT_UNITS,
    density: Density | None = None,
) -> Conversion:
    src_code, dst_code = source_unit.strip().upper(), target_unit.strip().upper()
    if not isfinite(value):
        return Conversion(value, source_unit, None, target_unit, ConversionStatus.INVALID_VALUE)
    src, dst = units.get(src_code), units.get(dst_code)
    if src is None or dst is None or src.dimension is Dimension.UNKNOWN or dst.dimension is Dimension.UNKNOWN:
        return Conversion(value, source_unit, None, target_unit, ConversionStatus.UNKNOWN_UOM)
    if (src.to_canonical is None or dst.to_canonical is None
            or not isfinite(src.to_canonical) or not isfinite(dst.to_canonical)
            or src.to_canonical <= 0 or dst.to_canonical <= 0):
        return Conversion(value, source_unit, None, target_unit, ConversionStatus.UNKNOWN_UOM)
    if src.dimension is not dst.dimension:
        if {src.dimension, dst.dimension} != {Dimension.MASS, Dimension.VOLUME}:
            return Conversion(value, source_unit, None, target_unit, ConversionStatus.DIMENSION_MISMATCH)
        if (density is None or not density.validated
                or not isfinite(density.kg_per_l) or density.kg_per_l <= 0):
            return Conversion(value, source_unit, None, target_unit, ConversionStatus.DENSITY_REQUIRED)
        if src.dimension is Dimension.MASS:
            canonical_kg = value * (src.to_canonical or 0.0)
            canonical_l = canonical_kg / density.kg_per_l
            result = canonical_l / (dst.to_canonical or 1.0)
        else:
            canonical_l = value * (src.to_canonical or 0.0)
            canonical_kg = canonical_l * density.kg_per_l
            result = canonical_kg / (dst.to_canonical or 1.0)
        factor = result / value if value else None
        return Conversion(value, source_unit, result, target_unit,
                          ConversionStatus.DENSITY_VALIDATED, factor,
                          density.kg_per_l, density.source)
    canonical = value * (src.to_canonical or 0.0)
    result = canonical / (dst.to_canonical or 1.0)
    return Conversion(value, source_unit, result, target_unit,
                      ConversionStatus.EXACT, result / value if value else None)


@dataclass(frozen=True)
class BomLine:
    parent_item: str
    component_item: str
    component_quantity: float
    component_uom: str
    parent_base_quantity: float
    parent_uom: str
    line_id: str


@dataclass(frozen=True)
class BomPath:
    root_item: str
    component_item: str
    factor: float
    path: tuple[str, ...]
    line_ids: tuple[str, ...]


@dataclass(frozen=True)
class BomExpansion:
    paths: tuple[BomPath, ...]
    cycles: tuple[tuple[str, ...], ...]
    truncated: bool


def expand_bom(
    root_item: str,
    lines: Iterable[BomLine],
    *,
    max_depth: int = 12,
    max_paths: int = 100_000,
    units: Mapping[str, Unit] = DEFAULT_UNITS,
) -> BomExpansion:
    """Expand multilevel BOM edges; cycle paths are recorded and not traversed."""
    if max_depth < 1 or max_paths < 1:
        raise ValueError("max_depth and max_paths must be positive")
    graph: dict[str, list[tuple[BomLine, float]]] = {}
    for line in lines:
        if line.parent_base_quantity <= 0 or line.component_quantity < 0:
            continue
        component_unit = units.get(line.component_uom.strip().upper())
        parent_unit = units.get(line.parent_uom.strip().upper())
        if (component_unit is None or parent_unit is None
                or component_unit.dimension is Dimension.UNKNOWN
                or parent_unit.dimension is Dimension.UNKNOWN):
            continue
        # A BOM factor is a ratio of two independently normalized quantities;
        # numerator and denominator may have different dimensions (e.g. KG/UNIT).
        component_base = line.component_quantity * component_unit.to_canonical
        parent_base = line.parent_base_quantity * parent_unit.to_canonical
        if parent_base <= 0:
            continue
        graph.setdefault(line.parent_item, []).append((line, component_base / parent_base))
    paths: list[BomPath] = []
    cycles: list[tuple[str, ...]] = []
    truncated = False

    def visit(item: str, factor: float, route: tuple[str, ...], edge_ids: tuple[str, ...]) -> None:
        nonlocal truncated
        if len(edge_ids) >= max_depth:
            if graph.get(item):
                truncated = True
            return
        for line, edge_factor in graph.get(item, ()):
            child = line.component_item
            next_route = route + (child,)
            next_ids = edge_ids + (line.line_id,)
            if child in route:
                cycles.append(next_route)
                continue
            combined = factor * edge_factor
            paths.append(BomPath(root_item, child, combined, next_route, next_ids))
            if len(paths) >= max_paths:
                truncated = True
                return
            visit(child, combined, next_route, next_ids)

    visit(root_item, 1.0, (root_item,), ())
    # Stable identities: preserve distinct parent paths, deduplicate exact paths.
    unique = {(p.path, p.line_ids): p for p in paths}
    return BomExpansion(tuple(unique[k] for k in sorted(unique)), tuple(cycles), truncated)


@dataclass(frozen=True)
class Coverage:
    days: float | None
    status: str
    basis: str
    confidence: str


def calculate_coverage(stock: float, stock_uom: str, daily_demand: float,
                       demand_uom: str, *, units: Mapping[str, Unit] = DEFAULT_UNITS,
                       density: Density | None = None) -> Coverage:
    if not isfinite(stock) or not isfinite(daily_demand):
        return Coverage(None, ConversionStatus.INVALID_VALUE.value, "UNRESOLVED", "UNRESOLVED")
    if daily_demand <= 0:
        return Coverage(None, "NO_POSITIVE_DEMAND", "UNRESOLVED", "UNRESOLVED")
    normalized = convert(daily_demand, demand_uom, stock_uom, units=units, density=density)
    if not normalized.compatible:
        return Coverage(None, normalized.status.value, "UNRESOLVED", "UNRESOLVED")
    return Coverage(stock / float(normalized.target_value), "CALCULATED",
                    "VALIDATED_UOM", "SUPPORTED" if normalized.status is ConversionStatus.DENSITY_VALIDATED else "EXACT")


def coverage_band(days: float) -> str:
    if days <= 0:
        return "QUIEBRE"
    if days < 15:
        return "CRITICO"
    if days < 30:
        return "ALTO"
    if days < 60:
        return "ATENCION"
    return "OK"


def supply_risk(coverage_days: float | None, lead_time_days: float | None,
                *, open_po_usable_before_stockout: bool | None = None) -> str:
    if coverage_days is None or lead_time_days is None:
        return "UNKNOWN"
    if open_po_usable_before_stockout is True:
        return "MITIGATED"
    if open_po_usable_before_stockout is None:
        return "INBOUND_DESTINATION_UNCERTAIN"
    return "RISK" if coverage_days <= lead_time_days else "MANAGEABLE"
