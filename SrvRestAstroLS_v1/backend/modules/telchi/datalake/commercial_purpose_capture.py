"""READ-ONLY SAP capture of Telchi commercial documentation (quotations + trace).

Captures quotations issued in October 2026 (OQUT/QUT1) and the documental trace
needed to measure their conversion into orders (ORDR/RDR1), deliveries
(ODLN/DLN1) and invoices (OINV/INV1) through the real SAP relations
BaseType / BaseEntry / BaseLine.

Reuses the existing bounded :class:`modules.telchi.datalake.full_refresh_capture.CaptureSession`
(one SQL statement / server cursor per segment, checkpointed, idempotent, read-only).
This module never publishes to Foundation and never writes to SAP.

Stage: TELCHI / COMERCIAL_Y_TRAZABILIDAD_DOCUMENTAL / INVESTIGATION.
Source: SAP_HANA (read only, SAP_WRITE_COUNT=0). Output: DATA_ROOT raw segments.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ducklake import DATA_ROOT
from .full_refresh_capture import CaptureSession, DomainBudget
from .source import HanaReadOnlySource, HanaTransportLimits

CONTRACT = "commercial-purpose-capture-v1"
OCTOBER_FROM = "2026-10-01"
OCTOBER_TO = "2026-11-01"
QUOTATION_OBJ_TYPE = "23"
ORDER_OBJ_TYPE = "17"
DELIVERY_OBJ_TYPE = "15"
INVOICE_OBJ_TYPE = "13"

RAW_ROOT = DATA_ROOT / "raw" / "sap" / "commercial_purpose_v1"

# --------------------------------------------------------------------------- budget


@dataclass(frozen=True)
class CommercialBudget:
    max_selects: int
    total_seconds: int
    max_rows_per_statement: int
    statement_seconds: int = 60
    operation_seconds: int = 900
    batch_rows: int = 5000

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in self.__dict__.values()):
            raise ValueError("finite positive budgets required")
        if self.batch_rows > 10000:
            raise ValueError("batch exceeds memory contract")

    def transport(self) -> HanaTransportLimits:
        return HanaTransportLimits(
            query_seconds=self.statement_seconds,
            operation_seconds=self.operation_seconds,
            max_rows=self.max_rows_per_statement,
            communication_ms=30000,
        )


DEFAULT_BUDGET = CommercialBudget(
    max_selects=120,
    total_seconds=900,
    max_rows_per_statement=50000,
)

# --------------------------------------------------------------------------- SQL fields (source-native, READ ONLY)

OQUT_FIELDS = (
    "DocEntry", "DocNum", "DocType", "CANCELED", "DocStatus", "ObjType", "DocDate",
    "DocDueDate", "TaxDate", "CreateDate", "UpdateDate", "FromDate", "ToDate",
    "CardCode", "CardName", "Address", "NumAtCard", "SlpCode", "Comments", "JrnlMemo",
    "DocCur", "DocRate", "DocTotal", "DocTotalFC", "VatSum", "VatSumFC", "DiscPrcnt",
    "DiscSum", "PaidToDate", "Series", "GroupNum", "DataSource",
)

QUT1_FIELDS = (
    "DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "OpenQty", "Price",
    "Currency", "Rate", "DiscPrcnt", "LineTotal", "TotalFrgn", "OpenSum", "OpenSumFC",
    "DocDate", "ShipDate", "WhsCode", "SlpCode", "LineStatus", "BaseType", "BaseEntry",
    "BaseLine", "BaseRef", "BaseCard", "BaseDocNum", "BaseAtCard", "VatPrcnt", "VatGroup",
    "PriceAfVAT", "VatSum", "VatSumFrgn", "unitMsr", "NumPerMsr", "UomCode", "UomEntry",
    "PackQty", "ObjType", "TreeType", "AcctCode", "TaxStatus",
)

ORDER_HEADER_FIELDS = (
    "DocEntry", "DocNum", "DocType", "CANCELED", "DocStatus", "ObjType", "DocDate",
    "DocDueDate", "CardCode", "CardName", "SlpCode", "DocCur", "DocRate", "DocTotal",
    "PaidToDate", "CreateDate", "UpdateDate", "Series",
)
ORDER_LINE_FIELDS = (
    "DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "OpenQty", "Price",
    "Currency", "LineTotal", "DocDate", "LineStatus", "BaseType", "BaseEntry",
    "BaseLine", "VatPrcnt", "PriceAfVAT", "WhsCode", "ObjType",
)

DELIVERY_HEADER_FIELDS = (
    "DocEntry", "DocNum", "DocType", "CANCELED", "DocStatus", "ObjType", "DocDate",
    "CardCode", "CardName", "SlpCode", "DocCur", "DocRate", "DocTotal", "CreateDate",
    "UpdateDate", "Series",
)
DELIVERY_LINE_FIELDS = (
    "DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "Price", "Currency",
    "LineTotal", "DocDate", "LineStatus", "BaseType", "BaseEntry", "BaseLine",
    "VatPrcnt", "WhsCode", "ObjType",
)

INVOICE_HEADER_FIELDS = (
    "DocEntry", "DocNum", "DocType", "CANCELED", "DocStatus", "ObjType", "DocDate",
    "CardCode", "CardName", "SlpCode", "DocCur", "DocRate", "DocTotal", "PaidToDate",
    "CreateDate", "UpdateDate", "Series",
)
INVOICE_LINE_FIELDS = (
    "DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "Price", "Currency",
    "LineTotal", "DocDate", "LineStatus", "BaseType", "BaseEntry", "BaseLine",
    "VatPrcnt", "WhsCode", "ObjType",
)


def _select(prefix: str, fields: tuple[str, ...]) -> str:
    return ", ".join(f'{prefix}."{f}" AS "{f}"' for f in fields)


def _header_line_select(h_prefix: str, h_fields: tuple[str, ...],
                        l_prefix: str, l_fields: tuple[str, ...]) -> str:
    parts = [f'{h_prefix}."{f}" AS "Header{f}"' for f in h_fields]
    parts += [f'{l_prefix}."{f}" AS "{f}"' for f in l_fields]
    return ", ".join(parts)


# --------------------------------------------------------------------------- capture

class CommercialPurposeCapture:
    """Bounded read-only capture of October 2026 commercial documentation.

    Reuses :class:`CaptureSession` for per-segment checkpointing, idempotency,
    bounded server cursors and source-vs-captured reconciliation.
    """

    def __init__(self, root: Path | str = RAW_ROOT,
                 source: HanaReadOnlySource | None = None,
                 budget: CommercialBudget = DEFAULT_BUDGET) -> None:
        self.root = Path(root)
        self.source = source or HanaReadOnlySource(limits=budget.transport())
        self.session = CaptureSession(self.root, self.source, budget)

    # -- segment builders ---------------------------------------------------

    def oqut_october_2026(self) -> dict[str, Any]:
        """Quotation headers issued in October 2026."""
        sql = (
            'SELECT ' + _select('H', OQUT_FIELDS) + ' '
            'FROM "OQUT" H '
            'WHERE H."DocDate" >= ? AND H."DocDate" < ? '
            'ORDER BY H."DocEntry"'
        )
        return self.session.capture(
            "oqut_october_2026", sql, (OCTOBER_FROM, OCTOBER_TO),
            keys=("DocEntry",), sums=("DocTotal",),
            semantic_scope="commercial_quotation_headers_october_2026",
        )

    def qut1_october_2026(self) -> dict[str, Any]:
        """Quotation lines issued in October 2026."""
        sql = (
            'SELECT ' + _select('L', QUT1_FIELDS) + ' '
            'FROM "QUT1" L '
            'WHERE L."DocDate" >= ? AND L."DocDate" < ? '
            'ORDER BY L."DocEntry", L."LineNum"'
        )
        return self.session.capture(
            "qut1_october_2026", sql, (OCTOBER_FROM, OCTOBER_TO),
            keys=("DocEntry", "LineNum"), sums=("Quantity", "LineTotal"),
            semantic_scope="commercial_quotation_lines_october_2026",
        )

    def orders_from_quotations(self) -> dict[str, Any]:
        """Order header+lines whose order lines originate from an October 2026 quotation."""
        sql = (
            'SELECT ' + _header_line_select('H', ORDER_HEADER_FIELDS, 'L', ORDER_LINE_FIELDS) + ' '
            'FROM "RDR1" L '
            'JOIN "ORDR" H ON H."DocEntry" = L."DocEntry" '
            'WHERE L."BaseType" = ? AND L."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?) '
            'ORDER BY L."DocEntry", L."LineNum"'
        )
        return self.session.capture(
            "orders_from_quotations", sql,
            (QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO),
            keys=("DocEntry", "LineNum"), sums=("Quantity", "LineTotal"),
            semantic_scope="order_lines_originating_from_october_2026_quotations",
        )

    def deliveries_from_quotations(self) -> dict[str, Any]:
        """Delivery header+lines linked to October 2026 quotations (direct or via order)."""
        sql = (
            'SELECT ' + _header_line_select('H', DELIVERY_HEADER_FIELDS, 'L', DELIVERY_LINE_FIELDS) + ' '
            'FROM "DLN1" L '
            'JOIN "ODLN" H ON H."DocEntry" = L."DocEntry" '
            'WHERE (L."BaseType" = ? AND L."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?)) '
            'OR (L."BaseType" = ? AND L."BaseEntry" IN '
            '(SELECT DISTINCT H2."DocEntry" FROM "ORDR" H2 '
            'JOIN "RDR1" L2 ON L2."DocEntry" = H2."DocEntry" '
            'WHERE L2."BaseType" = ? AND L2."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?))) '
            'ORDER BY L."DocEntry", L."LineNum"'
        )
        return self.session.capture(
            "deliveries_from_quotations", sql,
            (QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO,
             ORDER_OBJ_TYPE, QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO),
            keys=("DocEntry", "LineNum"), sums=("Quantity", "LineTotal"),
            semantic_scope="delivery_lines_originating_from_october_2026_quotations",
        )

    def invoices_from_quotations(self) -> dict[str, Any]:
        """Invoice header+lines linked to October 2026 quotations through any documental path."""
        sql = (
            'SELECT ' + _header_line_select('H', INVOICE_HEADER_FIELDS, 'L', INVOICE_LINE_FIELDS) + ' '
            'FROM "INV1" L '
            'JOIN "OINV" H ON H."DocEntry" = L."DocEntry" '
            'WHERE (L."BaseType" = ? AND L."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?)) '
            'OR (L."BaseType" = ? AND L."BaseEntry" IN '
            '(SELECT DISTINCT H2."DocEntry" FROM "ORDR" H2 '
            'JOIN "RDR1" L2 ON L2."DocEntry" = H2."DocEntry" '
            'WHERE L2."BaseType" = ? AND L2."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?))) '
            'OR (L."BaseType" = ? AND L."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "DLN1" L2 '
            'WHERE (L2."BaseType" = ? AND L2."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?)) '
            'OR (L2."BaseType" = ? AND L2."BaseEntry" IN '
            '(SELECT DISTINCT H2."DocEntry" FROM "ORDR" H2 '
            'JOIN "RDR1" L2 ON L2."DocEntry" = H2."DocEntry" '
            'WHERE L2."BaseType" = ? AND L2."BaseEntry" IN '
            '(SELECT "DocEntry" FROM "OQUT" WHERE "DocDate" >= ? AND "DocDate" < ?))))) '
            'ORDER BY L."DocEntry", L."LineNum"'
        )
        return self.session.capture(
            "invoices_from_quotations", sql,
            (
                QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO,
                ORDER_OBJ_TYPE, QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO,
                DELIVERY_OBJ_TYPE,
                QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO,
                ORDER_OBJ_TYPE, QUOTATION_OBJ_TYPE, OCTOBER_FROM, OCTOBER_TO,
            ),
            keys=("DocEntry", "LineNum"), sums=("Quantity", "LineTotal"),
            semantic_scope="invoice_lines_originating_from_october_2026_quotations",
        )

    def capture_all(self) -> dict[str, Any]:
        """Execute every segment in one bounded session; idempotent per segment."""
        started_at = datetime.now(timezone.utc).isoformat()
        segments = {
            "oqut_october_2026": self.oqut_october_2026(),
            "qut1_october_2026": self.qut1_october_2026(),
            "orders_from_quotations": self.orders_from_quotations(),
            "deliveries_from_quotations": self.deliveries_from_quotations(),
            "invoices_from_quotations": self.invoices_from_quotations(),
        }
        return dict(
            contract=CONTRACT, source_system="SAP_B1_HANA/TELCHI",
            sap_access_mode="READ_ONLY", sap_write_count=self.source.sap_write_count,
            started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat(),
            segments={name: {
                "status": seg["status"], "row_count": seg["row_count"],
                "pages": len(seg["pages"]), "elapsed_seconds": seg["elapsed_seconds"],
            } for name, seg in segments.items()},
        )
