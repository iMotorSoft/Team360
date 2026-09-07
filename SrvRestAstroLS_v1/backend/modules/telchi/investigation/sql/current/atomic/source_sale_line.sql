-- =============================================================================
-- ATOMIC SOURCE — SALE LINE (P0) — grain INV1.DocEntry + LineNum
-- =============================================================================
-- CONFIRMED fields (§15). BaseType/BaseEntry preserved for DOCUMENT_RELATION.
-- Quantity is INV1."Quantity" (base/warehouse qty; crude sale Qty kept too).
-- =============================================================================
SELECT
    'AR_INVOICE'        AS "source_object_type",
    INV1."DocEntry"     AS "source_document_id",
    INV1."LineNum"      AS "source_line_id",
    INV1."ItemCode"     AS "item_id",
    INV1."Dscription"   AS "item_desc",
    INV1."Quantity"     AS "quantity",
    INV1."UomCode"      AS "uom",
    INV1."WhsCode"      AS "warehouse_id",
    INV1."Price"        AS "price",
    INV1."DiscPrcnt"    AS "disc_prcnt",
    INV1."LineTotal"    AS "line_total",
    INV1."GTotal"       AS "g_total",
    INV1."BaseType"     AS "base_type",
    INV1."BaseEntry"    AS "base_entry",
    INV1."BaseLine"     AS "base_line"
FROM TELCHI.INV1 AS INV1
INNER JOIN TELCHI.OINV AS OINV
    ON INV1."DocEntry" = OINV."DocEntry"
WHERE OINV."DocDate" >= :start_date
  AND OINV."DocDate" < :end_date
-- =============================================================================
-- windowed by invoice header date; lineage: INV1.DocEntry/LineNum
-- =============================================================================