"""Offline Reference closure semantics for warehouse location and source UoM.

This module is deliberately Data-Lake-only.  It contains no SAP adapter and no
name-based UoM inference.  Runtime location resolution is an exact crosswalk
lookup; the ``2A`` prefix is accepted only by discovery tooling outside the
resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

UNKNOWN = "UNKNOWN"
SEGUNDO_ANILLO = "SEGUNDO_ANILLO"

# Explicit rows approved by the business-confirmed statement and by the frozen
# almacenOficina source.  No runtime prefix rule exists.
SECOND_ANILLO_WAREHOUSE_CODES = (
    "2A-AMD", "2A-AMK", "2A-DAN", "2A-DEV", "2A-EXT", "2A-KIT",
    "2A-MAG", "2A-MEI", "2A-MKT", "2A-SAL", "2A-SMK", "2A-TRAN",
    "22", "23", "24", "29", "51", "63",
)

# Only symbols whose physical meaning is explicit in the captured source are
# assigned a dimension.  Every other source code remains dimension UNKNOWN.
EXPLICIT_DIMENSIONS = {"KG": "MASS", "LT": "VOLUME"}


@dataclass(frozen=True)
class WarehouseLocation:
    warehouse_code: str
    business_location_code: str
    business_location_name: str
    mapping_status: str
    mapping_source: str
    mapping_basis: str
    mapping_confidence: Decimal


@dataclass(frozen=True)
class UomSemantic:
    source_uom_code: str
    canonical_uom_code: str
    canonical_uom_label: str
    physical_dimension: str
    mapping_status: str = "VALIDATED"
    mapping_source: str = "SOURCE_NATIVE_LINE_UOM"
    conversion_factor: Decimal = Decimal("1")
    conversion_basis: str = "IDENTITY_SAME_UOM"


def normalize_source_uom(value: object) -> str | None:
    """Normalize an actual source identifier; never inspect ItemName."""
    code = str(value or "").strip()
    return code or None


def uom_semantic(source_uom: object) -> UomSemantic | None:
    source = normalize_source_uom(source_uom)
    if source is None:
        return None
    canonical = source.upper()
    return UomSemantic(
        source_uom_code=source,
        canonical_uom_code=canonical,
        canonical_uom_label=canonical,
        physical_dimension=EXPLICIT_DIMENSIONS.get(canonical, UNKNOWN),
    )


def resolve_warehouse_location(
    warehouse_code: object,
    mappings: Mapping[str, WarehouseLocation],
) -> WarehouseLocation | None:
    """Resolve exact explicit rows only; never infer from a code prefix."""
    return mappings.get(str(warehouse_code or "").strip())


def convert_quantity(
    quantity: Decimal,
    source: UomSemantic,
    target: UomSemantic,
    *,
    validated_factor: Decimal | None = None,
    validated_density: Decimal | None = None,
) -> Decimal:
    """Fail closed for conversions without explicit provenance.

    Identity is always safe.  A cross-dimension MASS/VOLUME conversion also
    requires an explicit density even when a factor was supplied.  No density
    is ever inferred by this module.
    """
    if source.canonical_uom_code == target.canonical_uom_code:
        return quantity
    dimensions = {source.physical_dimension, target.physical_dimension}
    if dimensions == {"MASS", "VOLUME"} and validated_density is None:
        raise ValueError("MASS_VOLUME_CONVERSION_REQUIRES_VALIDATED_DENSITY")
    if source.physical_dimension == UNKNOWN or target.physical_dimension == UNKNOWN:
        raise ValueError("UOM_DIMENSION_UNRESOLVED")
    if source.physical_dimension != target.physical_dimension:
        raise ValueError("INCOMPATIBLE_UOM_DIMENSIONS")
    if validated_factor is None:
        raise ValueError("UOM_CONVERSION_FACTOR_REQUIRES_PROVENANCE")
    return quantity * validated_factor


def multiple_sales_uom(items_and_uoms: Iterable[tuple[str, object]]) -> set[str]:
    observed: dict[str, set[str]] = {}
    for item, raw_uom in items_and_uoms:
        semantic = uom_semantic(raw_uom)
        if semantic is not None:
            observed.setdefault(item, set()).add(semantic.canonical_uom_code)
    return {item for item, codes in observed.items() if len(codes) > 1}


__all__ = [
    "UNKNOWN", "SEGUNDO_ANILLO", "SECOND_ANILLO_WAREHOUSE_CODES",
    "EXPLICIT_DIMENSIONS", "WarehouseLocation", "UomSemantic",
    "normalize_source_uom", "uom_semantic", "resolve_warehouse_location",
    "convert_quantity", "multiple_sales_uom",
]
