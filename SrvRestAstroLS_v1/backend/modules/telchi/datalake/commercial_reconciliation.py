"""Quotation-grain reconciliation over already captured SAP relations.

No SAP access or publication writes. Document identity is (DocEntry, LineNum)
within each object type; amounts are local-currency net LineTotal, not DocTotal.
"""
from __future__ import annotations


def create_conversion_views(con):
    """Resolve each document line once before aggregating to quotation grain."""
    con.execute('''
        CREATE OR REPLACE VIEW quotation_document_links AS
        WITH orders AS (
            SELECT "BaseEntry" qdoc, "BaseLine" qline, 17 obj,
                   "DocEntry" doc, "LineNum" line
            FROM orders_from_quotations WHERE "BaseType" = 23
        ), deliveries AS (
            SELECT "BaseEntry" qdoc, "BaseLine" qline, 15 obj,
                   "DocEntry" doc, "LineNum" line
            FROM deliveries_from_quotations WHERE "BaseType" = 23
            UNION
            SELECT o.qdoc, o.qline, 15, d."DocEntry", d."LineNum"
            FROM deliveries_from_quotations d JOIN orders o
              ON d."BaseType" = 17 AND d."BaseEntry" = o.doc AND d."BaseLine" = o.line
        ), invoices AS (
            SELECT "BaseEntry" qdoc, "BaseLine" qline, 13 obj,
                   "DocEntry" doc, "LineNum" line
            FROM invoices_from_quotations WHERE "BaseType" = 23
            UNION
            SELECT o.qdoc, o.qline, 13, i."DocEntry", i."LineNum"
            FROM invoices_from_quotations i JOIN orders o
              ON i."BaseType" = 17 AND i."BaseEntry" = o.doc AND i."BaseLine" = o.line
            UNION
            SELECT d.qdoc, d.qline, 13, i."DocEntry", i."LineNum"
            FROM invoices_from_quotations i JOIN deliveries d
              ON i."BaseType" = 15 AND i."BaseEntry" = d.doc AND i."BaseLine" = d.line
        )
        SELECT * FROM orders UNION SELECT * FROM deliveries UNION SELECT * FROM invoices
    ''')
    con.execute('''
        CREATE OR REPLACE VIEW quotation_conversion AS
        WITH invoices AS (
            SELECT l.qdoc, l.qline, count(*) InvoiceLines,
                sum(cast(i."Quantity" AS DECIMAL(24,6))) InvoiceQty,
                sum(cast(i."LineTotal" AS DECIMAL(24,6))) InvoicedAmount
            FROM quotation_document_links l JOIN invoices_from_quotations i
              ON l.obj=13 AND l.doc=i."DocEntry" AND l.line=i."LineNum"
            WHERE i."HeaderCANCELED"='N'
            GROUP BY l.qdoc, l.qline
        ), stages AS (
            SELECT qdoc, qline,
                count(*) FILTER (WHERE obj=17) OrderLines,
                count(*) FILTER (WHERE obj=15) DeliveryLines
            FROM quotation_document_links l
            WHERE (obj=17 AND EXISTS (SELECT 1 FROM orders_from_quotations o
                WHERE o."DocEntry"=l.doc AND o."LineNum"=l.line AND o."HeaderCANCELED"='N'))
               OR (obj=15 AND EXISTS (SELECT 1 FROM deliveries_from_quotations d
                WHERE d."DocEntry"=l.doc AND d."LineNum"=l.line AND d."HeaderCANCELED"='N'))
            GROUP BY qdoc, qline
        ), amounts AS (
            SELECT q."DocEntry" QuoteDocEntry, q."LineNum" QuoteLineNum,
                q."ItemCode", q."Dscription", h."CardCode", h."CardName",
                q."LineStatus" QuoteLineStatus, h."DocStatus" HeaderDocStatus,
                h."CANCELED" HeaderCanceled,
                cast(q."Quantity" AS DECIMAL(24,6)) QuoteQty,
                cast(q."LineTotal" AS DECIMAL(24,6)) BudgetedAmount,
                coalesce(i.InvoiceQty,0) InvoiceQty,
                coalesce(i.InvoicedAmount,0) InvoicedAmount,
                coalesce(i.InvoiceLines,0) InvoiceLines,
                coalesce(s.OrderLines,0) OrderLines,
                coalesce(s.DeliveryLines,0) DeliveryLines
            FROM qut1_october_2026 q
            JOIN oqut_october_2026 h ON h."DocEntry"=q."DocEntry"
            LEFT JOIN invoices i ON i.qdoc=q."DocEntry" AND i.qline=q."LineNum"
            LEFT JOIN stages s ON s.qdoc=q."DocEntry" AND s.qline=q."LineNum"
        )
        SELECT *,
            greatest(BudgetedAmount-InvoicedAmount,0) PendingAmount,
            greatest(InvoicedAmount-BudgetedAmount,0) ExcessInvoicedAmount,
            CASE WHEN InvoiceLines>0 AND InvoiceQty>=QuoteQty THEN 'CONVERTED_FULLY'
                 WHEN InvoiceLines>0 THEN 'CONVERTED_PARTIALLY'
                 WHEN DeliveryLines>0 THEN 'DELIVERY_NO_INVOICE'
                 WHEN OrderLines>0 THEN 'ORDER_NO_INVOICE'
                 ELSE 'NO_DOCUMENTAL_CONVERSION' END ConversionCategory,
            CASE WHEN HeaderCanceled<>'N' THEN 'CANCELED'
                 WHEN QuoteLineStatus='O' THEN 'OPEN'
                 ELSE 'CLOSED' END QuoteState
        FROM amounts
    ''')


def validate_conversion(con):
    """Fail closed on duplicate source keys, ambiguous lineage or missing headers."""
    for dataset in ('qut1_october_2026', 'orders_from_quotations',
                    'deliveries_from_quotations', 'invoices_from_quotations'):
        rows, keys = con.execute(f'SELECT count(*), count(distinct ("DocEntry","LineNum")) FROM {dataset}').fetchone()
        if rows != keys:
            raise ValueError('DUPLICATE_DOCUMENT_LINE: ' + dataset)
    rows, keys = con.execute('SELECT count(*),count(distinct "DocEntry") FROM oqut_october_2026').fetchone()
    if rows != keys:
        raise ValueError('DUPLICATE_QUOTATION_HEADER')
    if con.execute('''SELECT count(*) FROM (
        SELECT obj,doc,line FROM quotation_document_links
        GROUP BY ALL HAVING count(*)>1)''').fetchone()[0]:
        raise ValueError('AMBIGUOUS_DOCUMENT_LINEAGE')
    source = con.execute('SELECT count(*),sum(cast("LineTotal" AS DECIMAL(24,6))) FROM qut1_october_2026').fetchone()
    result = con.execute('SELECT count(*),sum(BudgetedAmount) FROM quotation_conversion').fetchone()
    if source != result:
        raise ValueError('QUOTATION_GRAIN_RECONCILIATION_FAILED')
    # Unknown quotation references are retained as explicit capture-scope gaps,
    # never silently attributed to another October quotation.
    outside = con.execute('''SELECT count(*),coalesce(sum(cast(i."LineTotal" AS DECIMAL(24,6))),0)
        FROM invoices_from_quotations i WHERE i."HeaderCANCELED"='N' AND NOT EXISTS (
          SELECT 1 FROM quotation_document_links l JOIN qut1_october_2026 q
            ON q."DocEntry"=l.qdoc AND q."LineNum"=l.qline
          WHERE l.obj=13 AND l.doc=i."DocEntry" AND l.line=i."LineNum")''').fetchone()
    totals = con.execute('''SELECT sum(BudgetedAmount),sum(InvoicedAmount),
        sum(PendingAmount),sum(ExcessInvoicedAmount) FROM quotation_conversion''').fetchone()
    captured_invoiced = con.execute('''SELECT coalesce(sum(cast("LineTotal" AS DECIMAL(24,6))),0)
        FROM invoices_from_quotations WHERE "HeaderCANCELED"='N' ''').fetchone()[0]
    if captured_invoiced != totals[1] + outside[1]:
        raise ValueError('INVOICE_ATTRIBUTION_RECONCILIATION_FAILED')
    if totals[0] != totals[1] + totals[2] - totals[3]:
        raise ValueError('AMOUNT_RECONCILIATION_FAILED')
    return dict(quotation_lines=result[0], budgeted=totals[0], invoiced=totals[1],
                pending=totals[2], excess_invoiced=totals[3],
                outside_scope_invoice_lines=outside[0], outside_scope_invoice_amount=outside[1])
