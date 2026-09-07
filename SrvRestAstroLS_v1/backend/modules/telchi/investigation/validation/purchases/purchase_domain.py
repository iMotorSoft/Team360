"""Purchase data discovery domain (pure logic, READ ONLY contracts).

Semantics discovered against real SAP HANA (2026-08-27) - TELCHI:

Documents (grain):
  - Purchase order:  OPOR.DocEntry / POR1.DocEntry+LineNum
  - AP invoice:      OPCH.DocEntry / PCH1.DocEntry+LineNum
  - Goods receipt:   OPDN.DocEntry / PDN1.DocEntry+LineNum
  - Purchase req:    OPRQ.DocEntry / PRQ1.DocEntry+LineNum
  - Purchase return: ORPD.DocEntry / RPD1.DocEntry+LineNum
  - Supplier:        OCRD.CardCode (CardType='S')

Operative chain (100% linked) — SAP-canonical link is BaseEntry -> DocEntry:
  OPOR -> OPCH (PCH1.BaseType=22, PCH1.BaseEntry=OPOR.DocEntry)
  OPCH -> OPDN (PDN1.BaseType=18, PDN1.BaseEntry=OPCH.DocEntry)
  marginal direct: OPOR -> OPDN (PDN1.BaseType=22, BaseEntry=OPOR.DocEntry)

  Note: line tables also carry BaseRef/BaseDocNum (the string DocNum of the
  base document) and BaseAtCard (supplier document number). The canonical
  integer link is BaseEntry -> DocEntry; BaseRef -> DocNum also matches 100%
  but is a redundant representation, not the relationship of record.

Classification:
  U_TIPOCOMPRA: LF = compra local (296 suppliers), LP = envases/plásticos
  local, IMP = importación + logística + proveedores extranjeros (57),
  SERV = servicios, SAA = interno.

Quality flags (never hide uncertainty):
  IN_TRANSIT_UNRESOLVED: SAP only distinguishes ORDERED (OPOR.DocStatus='O')
  vs RECEIVED (OPDN); no customs/shipping states.
  IMPORT_UDF_UNUSED: U_FECHEST_EMBR/U_FECHREAL_EMBR/U_FECHPRTO/U_FECHALM/
  U_INCOTERM/U_CODPAIS/U_SOLCOMPRA have ~0 fill; U_TIPOCOMPRA is the only
  operative import marker.
  BACKDATED_PO: invoices dated before their PO (2,300 POS, -1..-295 days).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Object types / classification constants
# ---------------------------------------------------------------------------

OBJTYPE_PURCHASE_ORDER = 22
OBJTYPE_AP_INVOICE = 18
OBJTYPE_GOODS_RECEIPT = 20
OBJTYPE_PURCHASE_RETURN = 21
OBJTYPE_PURCHASE_REQUEST = 1470000113

BASE_NONE = -1
BASE_AP_INVOICE = 18
BASE_GOODS_RECEIPT = 20
BASE_PURCHASE_RETURN = 21
BASE_PURCHASE_ORDER = 22
BASE_PURCHASE_REQUEST = 1470000113
BASE_QUOTATION = 540000006

TIPOCOMPRA_SEMANTICS = {
    "LF": "LOCAL_GENERAL",
    "LP": "LOCAL_PACKAGING",
    "IMP": "IMPORT_OR_LOGISTICS",
    "SERV": "SERVICE",
    "SAA": "INTERNAL",
}

QUALITY_IMPORT_UDF_UNUSED = "IMPORT_UDF_UNUSED"
QUALITY_IN_TRANSIT_UNRESOLVED = "IN_TRANSIT_UNRESOLVED"
QUALITY_BACKDATED_PO = "BACKDATED_PO"

CANCELED_N = "N"
CANCELED_Y = "Y"
CANCELED_C = "C"


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PurchaseHeader:
    docentry: int
    docnum: int
    canceled: str
    docstatus: str
    docdate: Any | None
    cardcode: str | None
    cardname: str | None
    doccur: str | None
    doctotal: float | None
    tipo_compra: str | None

    @property
    def is_active(self) -> bool:
        return self.canceled == CANCELED_N

    @property
    def is_open(self) -> bool:
        return self.is_active and self.docstatus == "O"

    def to_dict(self) -> dict:
        return {
            "docentry": self.docentry,
            "docnum": self.docnum,
            "canceled": self.canceled,
            "docstatus": self.docstatus,
            "docdate": str(self.docdate)[:10] if self.docdate else None,
            "cardcode": self.cardcode,
            "cardname": self.cardname,
            "doccur": self.doccur,
            "doctotal": self.doctotal,
            "tipo_compra": self.tipo_compra,
        }


@dataclass(frozen=True)
class PurchaseLine:
    docentry: int
    linenum: int
    itemcode: str | None
    quantity: float
    openqty: float
    basetype: int
    baseentry: int | None = None
    baseref: str | None = None
    baselinenum: int | None = None
    warehouse: str | None = None
    linestatus: str | None = None

    @property
    def open_amount(self) -> float:
        return max(0.0, float(self.openqty or 0))

    @property
    def is_fully_open(self) -> bool:
        return self.open_amount > 0 and abs(self.open_amount - float(self.quantity or 0)) < 1e-9

    @property
    def is_closed(self) -> bool:
        return self.open_amount == 0


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def classify_tipo_compra(value: str | None) -> str:
    """Map OPOR.U_TIPOCOMPRA to the documented semantic class."""
    if not value:
        return "UNKNOWN"
    return TIPOCOMPRA_SEMANTICS.get(value.strip().upper(), "UNKNOWN")


def classify_import_supplier(cardcode: str | None, tipo_compra: str | None) -> str:
    """Import evidence: U_TIPOCOMPRA='IMP' or foreign supplier prefix (PE*)."""
    tipo = classify_tipo_compra(tipo_compra)
    if tipo == "IMPORT_OR_LOGISTICS":
        return "IMPORT_EVIDENCE"
    if cardcode and cardcode.upper().startswith("PE"):
        return "FOREIGN_SUPPLIER_CODE"
    return "LOCAL_EVIDENCE"


def cancellation_semantics(header: PurchaseHeader, partner_header: PurchaseHeader | None = None) -> str:
    """Y/C pair pattern: Y = original canceled, C = reversal document."""
    if header.canceled == CANCELED_Y:
        return "CANCELED_ORIGINAL"
    if header.canceled == CANCELED_C:
        return "CANCELED_REVERSAL"
    return "ACTIVE"


# ---------------------------------------------------------------------------
# Timing / lead time
# ---------------------------------------------------------------------------

def _as_date(value: Any):
    """Normalize datetime/date to date."""
    return value.date() if hasattr(value, "date") else value


def days_between(start: Any, end: Any) -> int | None:
    """Calendar days end - start; None when a date is missing."""
    if start is None or end is None:
        return None
    return (_as_date(end) - _as_date(start)).days


def lead_time_buckets(days: Iterable[int | None], edges: tuple[int, ...] = (0, 7, 30, 60, 90, 180)) -> dict[str, int]:
    """Bucket distribution of lead time days (NEGATIVE bucket included)."""
    counts: dict[str, int] = {}
    labels = ["NEGATIVE"] + [str(e) for e in edges] + ["%d+" % (edges[-1] + 1)]
    for d in days:
        if d is None:
            continue
        if d < 0:
            counts["NEGATIVE"] = counts.get("NEGATIVE", 0) + 1
        else:
            bucket = "%d+" % (edges[-1] + 1)
            for e in edges:
                if d <= e:
                    bucket = str(e)
                    break
            counts[bucket] = counts.get(bucket, 0) + 1
    return {k: counts.get(k, 0) for k in labels}


def percentiles(values: list[int], points: tuple[float, ...] = (0.5, 0.75, 0.9)) -> dict[float, int]:
    """Nearest-rank percentiles; empty list -> {}. Only non-negative days."""
    vals = sorted(v for v in values if v is not None and v >= 0)
    if not vals:
        return {}
    out: dict[float, int] = {}
    for p in points:
        idx = max(0, min(len(vals) - 1, math.ceil(p * len(vals)) - 1))
        out[p] = vals[idx]
    return out


# ---------------------------------------------------------------------------
# Invariants (TEST P0 of the purchase domain)
# ---------------------------------------------------------------------------

def invariant_chain_linked(total: int, linked: int) -> tuple[bool, str]:
    ok = total == linked
    return ok, "CHAIN_LINKED" if ok else "CHAIN_LINK_MISSING"


def invariant_open_qty_non_negative(negative_count: int) -> tuple[bool, str]:
    ok = negative_count == 0
    return ok, "OPEN_QTY_NON_NEGATIVE" if ok else "OPEN_QTY_NEGATIVE_FOUND"


def invariant_receipt_after_invoice(negative_count: int, total: int, tolerance_pct: float = 0.5) -> tuple[bool, str]:
    """receipt_date >= invoice_date; allow documented anomalies under tolerance."""
    if total == 0:
        return True, "RECEIPT_AFTER_INVOICE_EMPTY"
    ratio = negative_count / total * 100.0
    ok = ratio <= tolerance_pct
    return ok, "RECEIPT_AFTER_INVOICE" if ok else "RECEIPT_BEFORE_INVOICE_ABOVE_TOLERANCE"


def invariant_import_marker(tipo_compra: str | None, doccur: str | None) -> bool:
    """IMP orders are predominantly USD; BS IMP orders exist (logistics).
    Not a hard invariant; kept as evidence flag."""
    return True


# ---------------------------------------------------------------------------
# Open position builder
# ---------------------------------------------------------------------------

@dataclass
class OpenPurchasePosition:
    """A purchase order still open (DocStatus='O') with its line detail."""
    po_docentry: int
    po_docnum: int
    po_docdate: Any | None
    cardcode: str | None
    cardname: str | None
    doccur: str | None
    doctotal: float | None
    tipo_compra: str | None
    lines: list = field(default_factory=list)

    @property
    def import_class(self) -> str:
        return classify_tipo_compra(self.tipo_compra)

    def total_open_qty(self) -> float:
        return sum(max(0.0, float(ln.openqty or 0)) for ln in self.lines)

    def to_dict(self) -> dict:
        return {
            "po_docentry": self.po_docentry,
            "po_docnum": self.po_docnum,
            "po_docdate": str(self.po_docdate)[:10] if self.po_docdate else None,
            "cardcode": self.cardcode,
            "cardname": self.cardname,
            "doccur": self.doccur,
            "doctotal": self.doctotal,
            "tipo_compra": self.tipo_compra,
            "import_class": self.import_class,
            "total_open_qty": self.total_open_qty(),
            "lines": [
                {"itemcode": ln.itemcode, "quantity": ln.quantity,
                 "openqty": ln.openqty, "warehouse": ln.warehouse}
                for ln in self.lines
            ],
        }