"""Deterministic executive Sales queries over one committed Telchi Foundation.

No function in this module imports or calls the SAP adapter.  Semantics are
materialized during ingestion and the query path starts at FoundationReader.
"""
from __future__ import annotations

import time
from datetime import date
from decimal import Decimal
from typing import Any

from .ducklake import DuckLakeConnector
from .foundation_reader import FoundationReader

CORPORATE_CATEGORY_CODE = "2"
CORPORATE_CATEGORY_NAME = "CORPORATIVO"
CORPORATE_SEMANTIC_SOURCE = "SAP_UFD1:OSLP.U_CATVENDEDOR=2:Vendedor Corporativo"
SALESPERSON_ATTRIBUTION_LEVEL = "HEADER"
AMOUNT_BASIS = "SAP document local currency DocTotal where DocCur=BS; cancelled documents excluded"
CURRENCY = "BOB"

# NNM1/OUSR source census (2026): all 14 observed DMS* series are created by
# user dms (145); the four point-of-sale series are created by Retail One
# (soluone, 156). Keep seller type (OSLP) independent from channel.
HORIZONTAL_SERIES = frozenset({1248, 1249, 1250, 1251, 1252, 1253, 1254, 1255, 1256, 1257, 1258, 1259, 1403, 1407})
SALON_SERIES = frozenset({1265, 1266, 1267, 1268})


def classify_sales_channel(series: Any, user_sign: Any = None) -> tuple[str | None, str | None]:
    try:
        series_code = int(series)
    except (TypeError, ValueError):
        return None, None
    if series_code in HORIZONTAL_SERIES:
        return "HORIZONTAL", "CONFIRMED"
    if series_code in SALON_SERIES:
        return "SALON", "SUPPORTED"
    return None, None


def corporate_sales_by_salesperson(
    *,
    year: int,
    month: int,
    connector: DuckLakeConnector | None = None,
) -> dict[str, Any]:
    """Gross invoices, credit memos and net amount, entirely from Foundation."""
    connector = connector or DuckLakeConnector()
    started = time.perf_counter()
    with connector.session(read_only=True) as connection:
        access = FoundationReader(connector).resolve_on(connection)
        resolved_ms = access.foundation_resolution_ms
        query_started = time.perf_counter()
        start = date(year, month, 1)
        end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        salesperson_path = str(access.reference("salespersons")).replace("'", "''")
        sql = f"""
        WITH salesperson AS (
          SELECT CAST(source_native_id AS VARCHAR) slp_code,
                 name salesperson_name,
                 salesperson_category_code,
                 salesperson_category_name
          FROM read_parquet('{salesperson_path}')
          WHERE source_system='SAP_HANA'
        ), invoices AS (
          SELECT CAST(slp_code AS VARCHAR) slp_code,
                 SUM(TRY_CAST(doc_total AS DECIMAL(38,6))) gross
          FROM {access.sales('sales_document')}
          WHERE doc_date >= ? AND doc_date < ?
            AND UPPER(COALESCE(canceled, 'N')) NOT IN ('Y','C','1','TRUE')
            AND UPPER(COALESCE(currency, ''))='BS'
          GROUP BY slp_code
        ), credits AS (
          SELECT CAST(slp_code AS VARCHAR) slp_code,
                 SUM(TRY_CAST(doc_total AS DECIMAL(38,6))) credit
          FROM {access.credit_memo('credit_memo_document')}
          WHERE doc_date >= ? AND doc_date < ?
            AND UPPER(COALESCE(canceled, 'N')) NOT IN ('Y','C','1','TRUE')
            AND UPPER(COALESCE(currency, ''))='BS'
          GROUP BY slp_code
        )
        SELECT s.salesperson_name, s.slp_code,
               COALESCE(i.gross, 0) gross_invoice_sales,
               COALESCE(c.credit, 0) credit_memo_amount,
               COALESCE(i.gross, 0)-COALESCE(c.credit, 0) net_invoice_sales_after_credit_memos
        FROM salesperson s
        LEFT JOIN invoices i USING (slp_code)
        LEFT JOIN credits c USING (slp_code)
        WHERE s.salesperson_category_code=?
          AND (COALESCE(i.gross, 0)<>0 OR COALESCE(c.credit, 0)<>0)
        ORDER BY net_invoice_sales_after_credit_memos DESC, s.slp_code
        """
        result = connection.execute(sql, [start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat(), CORPORATE_CATEGORY_CODE])
        columns = [str(item[0]) for item in result.description or ()]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        query_ms = round((time.perf_counter() - query_started) * 1000, 3)
    for row in rows:
        for key in ("gross_invoice_sales", "credit_memo_amount", "net_invoice_sales_after_credit_memos"):
            row[key] = str(Decimal(str(row[key] or 0)).quantize(Decimal("0.01")))
    total_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "query": "Dame las ventas corporativas de septiembre de mayor a menor, vendedores y montos.",
        "data_source": "DATA_LAKE_FOUNDATION",
        "sap_accessed": "NO",
        "repo_discovery": "NO",
        "foundation_publication_id": access.foundation_publication_id,
        "foundation_source_as_of": access.foundation_data_as_of,
        "period_from": start.isoformat(),
        "period_to_exclusive": end.isoformat(),
        "salesperson_attribution_level": SALESPERSON_ATTRIBUTION_LEVEL,
        "amount_basis": AMOUNT_BASIS,
        "currency": CURRENCY,
        "rows": rows,
        "foundation_resolution_ms": resolved_ms,
        "query_execution_ms": query_ms,
        "total_query_ms": total_ms,
    }
