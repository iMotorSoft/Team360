-- =============================================================================
-- ATOMIC SOURCE — DELIVERY LINE (P0) — grain DLN1.DocEntry + LineNum
-- =============================================================================
SELECT
    'DELIVERY'      AS "source_object_type",
    DLN1."DocEntry" AS "source_document_id",
    DLN1."LineNum"  AS "source_line_id",
    DLN1."ItemCode" AS "item_id",
    DLN1."Quantity" AS "quantity",
    DLN1."UomCode"  AS "uom",
    DLN1."WhsCode"  AS "warehouse_id",
    DLN1."Price"    AS "price",
    DLN1."DiscPrcnt" AS "disc_prcnt",
    DLN1."GTotal"   AS "g_total",
    DLN1."BaseType" AS "base_type",
    DLN1."BaseEntry" AS "base_entry"
FROM TELCHI.DLN1 AS DLN1
INNER JOIN TELCHI.ODLN AS ODLN
    ON DLN1."DocEntry" = ODLN."DocEntry"
WHERE ODLN."DocDate" >= :start_date
  AND ODLN."DocDate" < :end_date
-- =============================================================================