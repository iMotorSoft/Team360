-- =============================================================================
-- ATOMIC RELATION — INVENTORY MOVEMENT -> SOURCE DOCUMENT (OINM -> OINV/ODLN)
-- =============================================================================
-- DOCUMENT_RELATION contract: from = commercial document (AR_INVOICE /
-- DELIVERY), to = INVENTORY_MOVEMENT, relation_type = GENERATES.
--
-- Resolution strategies (validated, never guessed):
--   A) OFFICIAL (ApplObj > 0): AppObjAbs = DocEntry, AppObjLine = LineNum
--      -> match_method = SAP_BASEENTRY, confidence 1.0.
--   B) DOCNUM_RESOLVE (ApplObj = -1): OINM.BASE_REF = DocNum (NOT DocEntry!)
--      -> header.DocEntry, then DocLineNum = LineNum and ItemCode match
--      -> match_method = DIRECT_REFERENCE; confidence 1.0 with line+item,
--         0.5 header-only.
-- DocNum collides across document families (collision_rate 1.0), so the
-- TransType family guard is MANDATORY (13=OINV, 15=ODLN).
SELECT * FROM (
SELECT
    'AR_INVOICE'          AS "from_object_type",
    OINV."DocEntry"       AS "from_document_id",
    INV1."LineNum"        AS "from_line_id",
    'INVENTORY_MOVEMENT'  AS "to_object_type",
    OINM."TransNum"       AS "to_document_id",
    'GENERATES'           AS "relation_type",
    'DIRECT_REFERENCE'    AS "match_method",
    CASE WHEN INV1."LineNum" = OINM."DocLineNum" AND INV1."ItemCode" = OINM."ItemCode"
         THEN 1.0 ELSE 0.5 END AS "confidence",
    OINM."TransType"      AS "trans_type",
    OINM."BASE_REF"       AS "base_ref",
    OINM."DocLineNum"     AS "movement_line",
    OINM."ItemCode"       AS "item_id",
    OINM."DocDate"        AS "event_at",
    OINM."InQty"          AS "in_qty",
    OINM."OutQty"         AS "out_qty",
    OINM."Warehouse"      AS "warehouse_id",
    'DOCNUM_RESOLVE'      AS "strategy"
FROM TELCHI.OINM AS OINM
LEFT JOIN TELCHI.OINV AS OINV
    ON OINV."DocNum" = OINM."BASE_REF"
LEFT JOIN TELCHI.INV1 AS INV1
    ON INV1."DocEntry" = OINV."DocEntry"
   AND INV1."LineNum" = OINM."DocLineNum"
WHERE OINM."TransType" = 13
  AND OINM."ApplObj" <= 0
  AND OINM."DocDate" >= :start_date || ' 00:00:00'
  AND OINM."DocDate" <= :end_date || ' 23:59:59'

UNION ALL

SELECT
    'DELIVERY'            AS "from_object_type",
    ODLN."DocEntry"       AS "from_document_id",
    DLN1."LineNum"        AS "from_line_id",
    'INVENTORY_MOVEMENT'  AS "to_object_type",
    OINM."TransNum"       AS "to_document_id",
    'GENERATES'           AS "relation_type",
    'DIRECT_REFERENCE'    AS "match_method",
    CASE WHEN DLN1."LineNum" = OINM."DocLineNum" AND DLN1."ItemCode" = OINM."ItemCode"
         THEN 1.0 ELSE 0.5 END AS "confidence",
    OINM."TransType"      AS "trans_type",
    OINM."BASE_REF"       AS "base_ref",
    OINM."DocLineNum"     AS "movement_line",
    OINM."ItemCode"       AS "item_id",
    OINM."DocDate"        AS "event_at",
    OINM."InQty"          AS "in_qty",
    OINM."OutQty"         AS "out_qty",
    OINM."Warehouse"      AS "warehouse_id",
    'DOCNUM_RESOLVE'      AS "strategy"
FROM TELCHI.OINM AS OINM
LEFT JOIN TELCHI.ODLN AS ODLN
    ON ODLN."DocNum" = OINM."BASE_REF"
LEFT JOIN TELCHI.DLN1 AS DLN1
    ON DLN1."DocEntry" = ODLN."DocEntry"
   AND DLN1."LineNum" = OINM."DocLineNum"
WHERE OINM."TransType" = 15
  AND OINM."ApplObj" <= 0
  AND OINM."DocDate" >= :start_date || ' 00:00:00'
  AND OINM."DocDate" <= :end_date || ' 23:59:59'

UNION ALL

SELECT
    CASE OINM."TransType"
        WHEN 59 THEN 'PRODUCTION'
        WHEN 60 THEN 'PRODUCTION'
        ELSE CONCAT('OBJTYPE_', TO_NVARCHAR(OINM."TransType"))
    END                   AS "from_object_type",
    OINM."AppObjAbs"      AS "from_document_id",
    OINM."AppObjLine"     AS "from_line_id",
    'INVENTORY_MOVEMENT'  AS "to_object_type",
    OINM."TransNum"       AS "to_document_id",
    'GENERATES'           AS "relation_type",
    'SAP_BASEENTRY'       AS "match_method",
    1.0                   AS "confidence",
    OINM."TransType"      AS "trans_type",
    OINM."BASE_REF"       AS "base_ref",
    OINM."DocLineNum"     AS "movement_line",
    OINM."ItemCode"       AS "item_id",
    OINM."DocDate"        AS "event_at",
    OINM."InQty"          AS "in_qty",
    OINM."OutQty"         AS "out_qty",
    OINM."Warehouse"      AS "warehouse_id",
    'APPLOBJ_OFFICIAL'    AS "strategy"
FROM TELCHI.OINM AS OINM
WHERE OINM."ApplObj" > 0
  AND OINM."DocDate" >= :start_date || ' 00:00:00'
  AND OINM."DocDate" <= :end_date || ' 23:59:59'
) AS R
-- =============================================================================
-- gate: ATOMIC-003 (P0 stock -> document relation)
-- =============================================================================