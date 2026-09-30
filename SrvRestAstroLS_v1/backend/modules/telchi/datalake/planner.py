"""Bounded planning primitives for the initial SAP -> Data Lake load.

The planner intentionally knows only the two V1 source grains. It does not
invent a global watermark or turn a stock snapshot into movement events.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class SegmentSpec:
    segment_id: str
    domain: str
    business_date_from: str | None
    business_date_to: str | None
    key_from: str
    key_to: str
    strategy: str
    scope: str
    estimated_rows: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "domain": self.domain,
            "business_date_from": self.business_date_from,
            "business_date_to": self.business_date_to,
            "source_key_from": self.key_from,
            "source_key_to": self.key_to,
            "strategy": self.strategy,
            "scope": self.scope,
            "estimated_rows": self.estimated_rows,
        }


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Return half-open calendar-month ranges intersecting ``[start, end)``."""
    if end <= start:
        raise ValueError("--to must be after --from")
    cursor = date(start.year, start.month, 1)
    result: list[tuple[date, date]] = []
    while cursor < end:
        next_month = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        result.append((max(start, cursor), min(end, next_month)))
        cursor = next_month
    return result


def sales_segments_from_bounds(
    bounds: Iterable[tuple[str, str, int, int]],
    *,
    max_docentries_per_segment: int,
    prefix: str = "sales",
) -> list[SegmentSpec]:
    """Split discovered DocEntry bounds into half-open, bounded ranges."""
    if max_docentries_per_segment <= 0:
        raise ValueError("max_docentries_per_segment must be positive")
    segments: list[SegmentSpec] = []
    for month_from, month_to, low, high in bounds:
        if high < low:
            raise ValueError("sales DocEntry bounds are inverted")
        # The upper bound is inclusive in the source discovery result and is
        # converted to half-open ranges for execution.
        end = high + 1
        cursor = low
        ordinal = 0
        while cursor < end:
            upper = min(cursor + max_docentries_per_segment, end)
            segment_id = f"{prefix}-{month_from}-{ordinal:04d}"
            segments.append(SegmentSpec(
                segment_id=segment_id,
                domain="sales",
                business_date_from=month_from,
                business_date_to=month_to,
                key_from=str(cursor),
                key_to=str(upper),
                strategy="DOCENTRY_RANGE",
                scope=f'DocEntry >= {cursor} AND DocEntry < {upper}; DocDate >= {month_from} AND DocDate < {month_to}',
            ))
            cursor, ordinal = upper, ordinal + 1
    return segments


def inventory_segments_from_keys(
    keys: Iterable[tuple[str, str]],
    *,
    max_pairs_per_segment: int,
    prefix: str = "inventory",
) -> list[SegmentSpec]:
    """Create bounded ItemCode x WhsCode groups without inventing events."""
    if max_pairs_per_segment <= 0:
        raise ValueError("max_pairs_per_segment must be positive")
    ordered = sorted((str(item), str(warehouse)) for item, warehouse in keys)
    result: list[SegmentSpec] = []
    for offset in range(0, len(ordered), max_pairs_per_segment):
        group = ordered[offset:offset + max_pairs_per_segment]
        first, last = group[0], group[-1]
        ordinal = offset // max_pairs_per_segment
        result.append(SegmentSpec(
            segment_id=f"{prefix}-{ordinal:04d}",
            domain="inventory",
            business_date_from=None,
            business_date_to=None,
            key_from=f"{first[0]}\x1f{first[1]}",
            key_to=f"{last[0]}\x1f{last[1]}",
            strategy="ITEMCODE_WHS_BOUNDED_GROUP",
            scope=f"ItemCode x WhsCode keys {first[0]} x {first[1]} .. {last[0]} x {last[1]}",
            estimated_rows=len(group),
        ))
    return result


def inventory_movement_segments_from_bounds(
    bounds: Iterable[tuple[str, str, int, int, int]],
    *,
    max_transnum_per_segment: int,
    prefix: str = "inventory-movement",
    domain: str = "inventory_movements",
) -> list[SegmentSpec]:
    """Split OINM monthly TransNum bounds into half-open execution ranges."""
    if max_transnum_per_segment <= 0:
        raise ValueError("max_transnum_per_segment must be positive")
    result: list[SegmentSpec] = []
    for month_from, month_to, low, high, row_count in bounds:
        if high < low:
            raise ValueError("inventory movement TransNum bounds are inverted")
        end = high + 1
        cursor = low
        ordinal = 0
        span = max(1, high - low + 1)
        while cursor < end:
            upper = min(cursor + max_transnum_per_segment, end)
            estimated = round(row_count * (upper - cursor) / span)
            result.append(SegmentSpec(
                segment_id=f"{prefix}-{month_from}-{ordinal:04d}",
                domain=domain,
                business_date_from=month_from,
                business_date_to=month_to,
                key_from=str(cursor),
                key_to=str(upper),
                strategy="TRANSNUM_DATE_BOUNDED",
                scope=f"TransNum >= {cursor} AND TransNum < {upper}; DocDate >= {month_from} AND DocDate < {month_to}",
                estimated_rows=estimated,
            ))
            cursor, ordinal = upper, ordinal + 1
    return result


def plan_only_placeholders(start: date, end: date, *, sales_count: int = 1, inventory_count: int = 1) -> list[SegmentSpec]:
    """Produce a safe plan without contacting SAP.

    A placeholder is deliberately not executable. The real runner replaces it
    with source-key ranges after bounded SAP discovery.
    """
    result: list[SegmentSpec] = []
    for index, (month_from, month_to) in enumerate(month_ranges(start, end)[:sales_count]):
        result.append(SegmentSpec(
            segment_id=f"sales-plan-{index:04d}", domain="sales",
            business_date_from=month_from.isoformat(), business_date_to=month_to.isoformat(),
            key_from="DISCOVERY_REQUIRED", key_to="DISCOVERY_REQUIRED",
            strategy="DOCENTRY_RANGE_DISCOVERY_REQUIRED",
            scope=f"DocDate >= {month_from.isoformat()} AND DocDate < {month_to.isoformat()}",
        ))
    for index in range(inventory_count):
        result.append(SegmentSpec(
            segment_id=f"inventory-plan-{index:04d}", domain="inventory",
            business_date_from=None, business_date_to=None,
            key_from="DISCOVERY_REQUIRED", key_to="DISCOVERY_REQUIRED",
            strategy="ITEMCODE_WHS_BOUNDED_DISCOVERY_REQUIRED",
            scope="bounded ItemCode x WhsCode discovery; OITW current state",
        ))
    return result
