-- =============================================================================
-- CANCELLATION AUDIT 09: HIGH PRIORITY CASES
-- =============================================================================
-- Purpose: Identify cases requiring manual investigation
-- Grain: OINV.DocEntry (one row per cancelled invoice)
-- Priority: >30 days + high amount + delivery + payment
-- =============================================================================

WITH cancellation_derivation AS (
    SELECT
        OINV."DocEntry",
        OINV."DocNum",
        OINV."CardCode",
        OINV."CardName",
        OINV."SlpCode",
        (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP WHERE OINV."SlpCode" = OSLP."SlpCode") AS "SellerName",
        OINV."DocDate",
        OINV."DocTotal",
        OINV."CANCELED",
        OINV."PaidToDate",
        OINV."UpdateDate" AS "CancellationDate",
        OINV."UpdateTS" AS "CancellationTimestamp",
        DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate") AS "DaysToCancellation"
    FROM TELCHI."OINV" AS OINV
    WHERE OINV."CANCELED" = 'Y'
),
-- Find reversal documents
reversal_pairs AS (
    SELECT
        Y."DocEntry" AS "OriginalDocEntry",
        C."DocEntry" AS "ReversalDocEntry",
        C."DocNum" AS "ReversalDocNum"
    FROM TELCHI."OINV" AS Y
    INNER JOIN TELCHI."OINV" AS C
        ON Y."CardCode" = C."CardCode"
        AND Y."DocTotal" = C."DocTotal"
        AND C."CANCELED" = 'C'
        AND ABS(DAYS_BETWEEN(Y."UpdateDate", C."DocDate")) <= 7
    WHERE Y."CANCELED" = 'Y'
),
-- Check for deliveries
delivery_check AS (
    SELECT
        CD."DocEntry",
        (SELECT COUNT(*)
         FROM TELCHI."INV1" AS INV1
         WHERE INV1."DocEntry" = CD."DocEntry"
           AND INV1."BaseEntry" IS NOT NULL
           AND INV1."BaseType" = 15) AS "DeliveryLineCount"
    FROM cancellation_derivation AS CD
),
-- Check for payments
payment_check AS (
    SELECT
        CD."DocEntry",
        COALESCE((SELECT SUM(ABS(ITR1."ReconSum"))
         FROM TELCHI."ITR1" AS ITR1
         INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
         WHERE ITR1."SrcObjAbs" = CD."DocEntry"
           AND ITR1."SrcObjTyp" = 13
           AND OITR."Canceled" = 'N'), 0) AS "ActivePaymentAmount"
    FROM cancellation_derivation AS CD
),
-- Calculate priority score
priority_cases AS (
    SELECT
        CD.*,
        RP."ReversalDocEntry",
        RP."ReversalDocNum",
        DC."DeliveryLineCount",
        PC."ActivePaymentAmount",

        -- Priority scoring
        (CASE WHEN CD."DaysToCancellation" > 30 THEN 1 ELSE 0 END +
         CASE WHEN CD."DocTotal" > 10000 THEN 1 ELSE 0 END +
         CASE WHEN DC."DeliveryLineCount" > 0 THEN 1 ELSE 0 END +
         CASE WHEN PC."ActivePaymentAmount" > 0 THEN 1 ELSE 0 END) AS "PriorityScore"

    FROM cancellation_derivation AS CD
    LEFT JOIN reversal_pairs AS RP ON CD."DocEntry" = RP."OriginalDocEntry"
    LEFT JOIN delivery_check AS DC ON CD."DocEntry" = DC."DocEntry"
    LEFT JOIN payment_check AS PC ON CD."DocEntry" = PC."DocEntry"
)
SELECT
    "DocEntry",
    "DocNum",
    "CardCode",
    "CardName",
    "SlpCode",
    "SellerName",
    "DocDate",
    "CancellationDate",
    "DaysToCancellation",
    "DocTotal",
    "PaidToDate",
    "ReversalDocEntry",
    "ReversalDocNum",
    "DeliveryLineCount",
    "ActivePaymentAmount",
    "PriorityScore",

    -- Classification
    CASE
        WHEN "DaysToCancellation" > 30 AND "DeliveryLineCount" > 0 AND "ActivePaymentAmount" > 0
            THEN 'CRITICAL'
        WHEN "DaysToCancellation" > 30 AND "DeliveryLineCount" > 0
            THEN 'HIGH_STOCK'
        WHEN "DaysToCancellation" > 30 AND "ActivePaymentAmount" > 0
            THEN 'HIGH_PAYMENT'
        WHEN "DaysToCancellation" > 30
            THEN 'HIGH_DELAY'
        WHEN "DocTotal" > 10000
            THEN 'HIGH_VALUE'
        ELSE 'STANDARD'
    END AS "PriorityClass"

FROM priority_cases
WHERE "PriorityScore" >= 2
ORDER BY "PriorityScore" DESC, "DocTotal" DESC
LIMIT 50;
