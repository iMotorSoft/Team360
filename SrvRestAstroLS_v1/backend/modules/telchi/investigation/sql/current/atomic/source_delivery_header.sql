-- =============================================================================
-- ATOMIC SOURCE — DELIVERY HEADER (P0) — grain ODLN.DocEntry
-- =============================================================================
SELECT
    'SAP'               AS "source_system",
    'DELIVERY'          AS "source_object_type",
    ODLN."DocEntry"     AS "source_document_id",
    ODLN."DocNum"       AS "source_document_number",
    ODLN."ObjType"      AS "obj_type",
    ODLN."CardCode"     AS "customer_id",
    ODLN."SlpCode"      AS "seller_id",
    ODLN."DocDate"      AS "business_date",
    ODLN."DocTotal"     AS "amount_document",
    ODLN."CANCELED"     AS "canceled",
    ODLN."DocStatus"    AS "status",
    ODLN."UpdateDate"   AS "updated_at"
FROM TELCHI.ODLN AS ODLN
WHERE ODLN."DocDate" >= :start_date
  AND ODLN."DocDate" < :end_date
-- =============================================================================
-- Note: absence of delivery must NOT imply absence of stock movement (§16).
-- =============================================================================