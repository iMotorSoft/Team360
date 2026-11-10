"""Read-only business reader for captured October quotations; no SAP access.

This diagnostic reader is NOT proof of CURRENT publication. Production consumers
must resolve and validate the exact Foundation manifest before passing its files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import duckdb

from .commercial_purpose_capture import RAW_ROOT
from .commercial_reconciliation import create_conversion_views, validate_conversion

QUOTATION_OBJ_TYPE = "23"
ORDER_OBJ_TYPE = "17"
DELIVERY_OBJ_TYPE = "15"
INVOICE_OBJ_TYPE = "13"
DATASETS = ('oqut_october_2026', 'qut1_october_2026', 'orders_from_quotations',
            'deliveries_from_quotations', 'invoices_from_quotations')


class CommercialPurposeViews:
    """In-memory views; source Parquet is never modified.

    ``datasets`` pins explicit manifest files. Without it, root is diagnostic
    capture input only; no fallback between a pinned manifest and directory scan.
    """

    def __init__(self, root: Path | str = RAW_ROOT, read_only: bool = True, *,
                 datasets: Mapping[str, Any] | None = None, threads: int = 2) -> None:
        self.root = Path(root)
        if type(threads) is not int or not 1 <= threads <= 4:
            raise ValueError('bounded thread budget required')
        self.con = duckdb.connect(database=':memory:')
        try:
            self.con.execute(f'SET threads={threads}')
            self.con.execute("SET memory_limit='512MB'")
            for dataset in DATASETS:
                if datasets is None:
                    files = sorted((self.root / dataset / 'raw').rglob('*.parquet'))
                else:
                    files = [Path(p) for p in datasets[dataset]['file_references']]
                if not files or any(not p.is_file() for p in files):
                    raise ValueError('MISSING_CAPTURE_FILES: ' + dataset)
                paths = '[' + ','.join("'" + str(p).replace("'", "''") + "'" for p in files) + ']'
                self.con.execute(f'CREATE VIEW "{dataset}" AS SELECT * FROM read_parquet({paths}, union_by_name=true)')
            create_conversion_views(self.con)
            self.reconciliation = validate_conversion(self.con)
        except BaseException:
            self.con.close()
            raise

    def close(self) -> None:
        self.con.close()

    def quotation_header(self) -> Any:
        return self.con.table('oqut_october_2026')

    def quotation_line(self) -> Any:
        return self.con.table('qut1_october_2026')

    def order_trace(self) -> Any:
        return self.con.table('orders_from_quotations')

    def delivery_trace(self) -> Any:
        return self.con.table('deliveries_from_quotations')

    def invoice_trace(self) -> Any:
        return self.con.table('invoices_from_quotations')

    def conversion_trace_df(self) -> Any:
        """One row per quotation line; document keys live in quotation_document_links."""
        return self.con.table('quotation_conversion')

    def quotation_lines_with_header_df(self) -> Any:
        return self.con.table('quotation_conversion')

    def product_budget_summary(self) -> Any:
        return self.con.sql('''SELECT "ItemCode", max("Dscription") "Dscription",
            count(*) "QuoteLines", sum(QuoteQty) "BudgetedQty",
            sum(BudgetedAmount) "BudgetedAmount", sum(InvoicedAmount) "ConvertedAmount",
            sum(PendingAmount) "PendingAmount", sum(ExcessInvoicedAmount) "ExcessInvoicedAmount"
            FROM quotation_conversion GROUP BY "ItemCode"
            ORDER BY "PendingAmount" DESC, "ItemCode"''')

    def top_products_unconverted(self, limit: int = 20) -> Any:
        """Rank PRODUCTS by pending amount, not original budget or customer rows.

        Canceled quotes are excluded. Positive price differences on fully invoiced
        quantities are exposed separately, not labeled pending commercial demand.
        """
        return self.con.execute('''SELECT "ItemCode", max("Dscription") "Dscription",
            count(*) "QuoteLines", sum(BudgetedAmount) "BudgetedAmount",
            sum(InvoicedAmount) "ConvertedAmount", sum(PendingAmount) "PendingAmount",
            sum(PendingAmount) FILTER (WHERE ConversionCategory='CONVERTED_FULLY') "FullyInvoicedValueGap",
            count(*) FILTER (WHERE ConversionCategory='CONVERTED_PARTIALLY') "PartialLines",
            count(*) FILTER (WHERE ConversionCategory='ORDER_NO_INVOICE') "OrderOnlyLines",
            count(*) FILTER (WHERE ConversionCategory='DELIVERY_NO_INVOICE') "DeliveryOnlyLines",
            count(*) FILTER (WHERE ConversionCategory='NO_DOCUMENTAL_CONVERSION') "UnconvertedLines"
            FROM quotation_conversion WHERE HeaderCanceled='N'
            GROUP BY "ItemCode" HAVING sum(PendingAmount)>0
            ORDER BY "PendingAmount" DESC, "ItemCode" LIMIT ?''', [limit])

    def conversion_category_counts(self) -> Any:
        """Mutually exclusive quotation-grain groups; retain canceled/open/closed."""
        return self.con.sql('''SELECT ConversionCategory, QuoteState,
            count(*) "QuoteLines", sum(BudgetedAmount) "BudgetedAmount",
            sum(InvoicedAmount) "ConvertedAmount", sum(PendingAmount) "PendingAmount",
            sum(ExcessInvoicedAmount) "ExcessInvoicedAmount"
            FROM quotation_conversion GROUP BY ALL
            ORDER BY "BudgetedAmount" DESC''')

    def clients_for_top_products(self, limit: int = 20) -> Any:
        """Customer/state detail for the product ranking; never MAX(client)."""
        products = [r[0] for r in self.top_products_unconverted(limit).fetchall()]
        return self.con.execute('''SELECT "ItemCode", max("Dscription") "Dscription",
            "CardCode", "CardName", ConversionCategory, QuoteState,
            sum(BudgetedAmount) "BudgetedAmount", sum(InvoicedAmount) "InvoicedAmount",
            sum(PendingAmount) "PendingAmount", sum(ExcessInvoicedAmount) "ExcessInvoicedAmount"
            FROM quotation_conversion WHERE HeaderCanceled='N' AND "ItemCode" IN (SELECT unnest(?))
            GROUP BY "ItemCode", "CardCode", "CardName", ConversionCategory, QuoteState
            ORDER BY "ItemCode", "PendingAmount" DESC, "CardCode", ConversionCategory, QuoteState''', [products])
