"""Purchase lead time domain (pure logic, READ ONLY contracts).

Semantics (TELCHI, 2026-08-27):
  - External procurement lead time = PO line -> goods receipt, through the
    invoice-first document chain (OPOR -> OPCH -> OPDN).
  - Order date = OPOR.DocDate (BACKDATED_PO anomaly documented: invoice can
    precede PO; negative lead times flagged, not silently normalized).
  - Receipt date = OPDN.DocDate.
  - first_receipt_lead_time = first receipt date - order date.
  - full_receipt_lead_time = date cumulative received >= ordered - order date.
  - Partial receipts supported (1 PO line -> N receipt lines).
  - Sample-size confidence: N=0 NO_HISTORY, 1 VERY_LOW, 2-4 LOW, >=5 USABLE.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

STATUS_FULL = "FULL_RECEIVED"
STATUS_PARTIAL = "PARTIAL_RECEIPT"
STATUS_OPEN = "OPEN_UNRECEIVED"
STATUS_CLOSED_NO_RECEIPT = "CLOSED_WITHOUT_FULL_RECEIPT"

FLAG_NEGATIVE_LEAD_TIME = "NEGATIVE_LEAD_TIME_ANOMALY"
FLAG_PARTIAL_RECEIPT = "PARTIAL_RECEIPT"
FLAG_CLOSED_NO_RECEIPT = "CLOSED_WITHOUT_FULL_RECEIPT"
FLAG_RECEIPT_WITHOUT_PO = "RECEIPT_WITHOUT_PO"
FLAG_OPEN_PO = "OPEN_PO"
FLAG_LOW_SAMPLE = "LOW_SAMPLE_SIZE"
FLAG_NO_HISTORY = "NO_PURCHASE_HISTORY"


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

def _as_date(value: Any):
    return value.date() if hasattr(value, "date") else value


@dataclass
class ReceiptEvent:
    rec_entry: int
    rec_line: int
    rec_qty: float
    rec_date: Any
    rec_whs: str | None


@dataclass
class LeadTimeEvent:
    po_entry: int
    po_line: int
    item_code: str | None
    ordered_qty: float
    order_date: Any
    card_code: str | None
    card_name: str | None
    tipo_compra: str | None
    doc_cur: str | None
    doc_status: str | None
    receipts: list[ReceiptEvent] = field(default_factory=list)

    @property
    def received_qty(self) -> float:
        return sum(r.rec_qty for r in self.receipts)

    @property
    def first_receipt_date(self) -> Any | None:
        if not self.receipts:
            return None
        return min(r.rec_date for r in self.receipts)

    @property
    def full_receipt_date(self) -> Any | None:
        """First date where cumulative received >= ordered."""
        if not self.receipts:
            return None
        cumulative = 0.0
        for r in sorted(self.receipts, key=lambda x: x.rec_date):
            cumulative += r.rec_qty
            if cumulative >= self.ordered_qty - 1e-9:
                return r.rec_date
        return None

    @property
    def first_lead_days(self) -> int | None:
        if self.first_receipt_date is None or self.order_date is None:
            return None
        return (_as_date(self.first_receipt_date) - _as_date(self.order_date)).days

    @property
    def full_lead_days(self) -> int | None:
        d = self.full_receipt_date
        if d is None or self.order_date is None:
            return None
        return (_as_date(d) - _as_date(self.order_date)).days

    @property
    def status(self) -> str:
        if not self.receipts:
            return STATUS_CLOSED_NO_RECEIPT if self.doc_status != "O" else STATUS_OPEN
        if self.received_qty >= self.ordered_qty - 1e-9:
            return STATUS_FULL
        return STATUS_PARTIAL


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def percentiles(values: list[int], points: tuple[float, ...] = (0.5, 0.75, 0.9)) -> dict[float, int]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {}
    out: dict[float, int] = {}
    for p in points:
        idx = max(0, min(len(vals) - 1, math.ceil(p * len(vals)) - 1))
        out[p] = vals[idx]
    return out


def summarize(days: Iterable[int | None]) -> dict:
    vals = [d for d in days if d is not None]
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    p = percentiles(vals)
    return {
        "n": len(vals),
        "min": s[0],
        "max": s[-1],
        "median": p.get(0.5),
        "p75": p.get(0.75),
        "p90": p.get(0.9),
        "mean": sum(vals) / len(vals),
    }


def sample_confidence(n: int) -> str:
    if n <= 0:
        return FLAG_NO_HISTORY
    if n == 1:
        return "VERY_LOW"
    if n <= 4:
        return "LOW"
    return "USABLE"


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def invariant_first_le_full(first: int | None, full: int | None) -> bool:
    """first_receipt_lead <= full_receipt_lead."""
    if first is None or full is None:
        return True
    return first <= full


def invariant_negative_controlled(events: Iterable[LeadTimeEvent]) -> list[LeadTimeEvent]:
    """Return events with negative first lead time (must be flagged, not fixed)."""
    return [e for e in events if e.first_lead_days is not None and e.first_lead_days < 0]


def classify_procurement_mode(has_purchase: bool, is_produced: bool) -> str:
    if has_purchase and is_produced:
        return "MIXED"
    if has_purchase:
        return "PURCHASED"
    if is_produced:
        return "PRODUCED"
    return "NO_PURCHASE_HISTORY"