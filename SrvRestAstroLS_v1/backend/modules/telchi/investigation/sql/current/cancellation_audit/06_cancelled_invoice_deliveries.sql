-- =============================================================================
-- CANCELLATION AUDIT 06: DELIVERY LINKAGE (STOCK EFFECTS)
-- =============================================================================
-- Purpose: Determine if cancelled invoices had delivery/stock effects
-- Grain: OINV.DocEntry (one row per cancelled invoice)
-- =============================================================================

-- First, check if there are delivery tables (ODLN/DLN1) in Telchi schema
-- This query will be adapted based on actual schema

WITH cancellation_derivation AS (
    SELECT
        OINV."DocEntry",
        OINV."DocNum",
        OINV."CardCode",
        OINV."CardName",
        OINV."SlpCode",
        OINV."DocDate",
        OINV."DocTotal",
        OINV."CANCELED",
        OINV."UpdateDate" AS "CancellationDate",
        CASE
            WHEN OINV."CANCELED" = 'Y'
            THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
            ELSE NULL
        END AS "DaysToCancellation"
    FROM TELCHI."OINV" AS OINV
    WHERE OINV."CANCELED" = 'Y'
),
-- Check for delivery documents linked to invoices
-- Option 1: Direct link via INV1.BaseEntry (if invoice was created from delivery)
-- Option 2: Check ODLN (Delivery) documents
delivery_check AS (
    SELECT
        CD."DocEntry" AS "InvoiceDocEntry",
        CD."DocNum" AS "InvoiceDocNum",
        CD."CardCode",
        CD."CardName",
        CD."SlpCode",
        CD."DocDate" AS "InvoiceDate",
        CD."CancellationDate",
        CD."DaysToCancellation",
        CD."DocTotal" AS "InvoiceAmount",

        -- Check if invoice has lines with delivery reference
        (SELECT COUNT(*)
         FROM TELCHI."INV1" AS INV1
         WHERE INV1."DocEntry" = CD."DocEntry"
           AND INV1."BaseEntry" IS NOT NULL
           AND INV1."BaseType" = 15) AS "DeliveryLineCount",  -- BaseType 15 = Delivery

        -- Check total lines
        (SELECT COUNT(*)
         FROM TELCHI."INV1" AS INV1
         WHERE INV1."DocEntry" = CD."DocEntry") AS "TotalLineCount"

    FROM cancellation_derivation AS CD
)
SELECT
    *,
    CASE
        WHEN "DeliveryLineCount" > 0 THEN 'HAS_DELIVERY'
        WHEN "TotalLineCount" > 0 AND "DeliveryLineCount" = 0 THEN 'NO_DELIVERY'
        ELSE 'NO_LINES'
    END AS "DeliveryStatus"
FROM delivery_check
ORDER BY "InvoiceAmount" DESC
LIMIT 100;
