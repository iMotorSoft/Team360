-- =============================================================================
-- CANCELLATION AUDIT 08: COMPLETE LIFECYCLE
-- =============================================================================
-- Purpose: Complete lifecycle view of each cancelled invoice
-- Grain: OINV.DocEntry (one row per cancelled invoice)
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
        OINV."DocDueDate",
        OINV."DocTotal",
        OINV."DocStatus",
        OINV."CANCELED",
        OINV."DocSubType",
        OINV."TransId",
        OINV."PaidSum",
        OINV."PaidToDate",
        OINV."DocCur",
        OINV."UpdateDate",
        OINV."UpdateTS",

        -- Cancellation derivation
        OINV."UpdateDate" AS "CancellationDate",
        OINV."UpdateTS" AS "CancellationTimestamp",
        DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate") AS "DaysToCancellation"

    FROM TELCHI."OINV" AS OINV
    WHERE OINV."CANCELED" = 'Y'
),
-- Find reversal documents (C)
reversal_pairs AS (
    SELECT
        Y."DocEntry" AS "OriginalDocEntry",
        C."DocEntry" AS "ReversalDocEntry",
        C."DocNum" AS "ReversalDocNum",
        C."TransId" AS "ReversalTransId"
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
           AND OITR."Canceled" = 'N'), 0) AS "ActivePaymentAmount",

        (SELECT COUNT(*)
         FROM TELCHI."ITR1" AS ITR1
         INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
         WHERE ITR1."SrcObjAbs" = CD."DocEntry"
           AND ITR1."SrcObjTyp" = 13
           AND OITR."Canceled" = 'Y') AS "CancelledPaymentCount"

    FROM cancellation_derivation AS CD
)
SELECT
    CD."DocEntry",
    CD."DocNum",
    CD."CardCode",
    CD."CardName",
    CD."SlpCode",
    CD."SellerName",
    CD."DocDate",
    CD."DocDueDate",
    CD."DocTotal",
    CD."DocCur",
    CD."CANCELED",
    CD."CancellationDate",
    CD."CancellationTimestamp",
    CD."DaysToCancellation",
    CD."PaidToDate",
    CD."TransId",

    -- Reversal info
    RP."ReversalDocEntry",
    RP."ReversalDocNum",
    RP."ReversalTransId",

    -- Delivery info
    DC."DeliveryLineCount",
    CASE WHEN DC."DeliveryLineCount" > 0 THEN 'HAS_DELIVERY' ELSE 'NO_DELIVERY' END AS "DeliveryStatus",

    -- Payment info
    PC."ActivePaymentAmount",
    PC."CancelledPaymentCount",
    CASE
        WHEN CD."PaidToDate" > 0 AND PC."ActivePaymentAmount" > 0 THEN 'PAYMENT_ACTIVE'
        WHEN CD."PaidToDate" > 0 AND PC."ActivePaymentAmount" = 0 AND PC."CancelledPaymentCount" > 0 THEN 'PAYMENT_CANCELLED'
        WHEN CD."PaidToDate" = 0 THEN 'NO_PAYMENT'
        ELSE 'UNKNOWN'
    END AS "PaymentStatus",

    -- Combined classification
    CASE
        WHEN DC."DeliveryLineCount" > 0 AND PC."ActivePaymentAmount" > 0 THEN 'STOCK_AND_PAYMENT'
        WHEN DC."DeliveryLineCount" > 0 THEN 'STOCK_ONLY'
        WHEN PC."ActivePaymentAmount" > 0 THEN 'PAYMENT_ONLY'
        ELSE 'ADMINISTRATIVE'
    END AS "OperationalImpact"

FROM cancellation_derivation AS CD
LEFT JOIN reversal_pairs AS RP ON CD."DocEntry" = RP."OriginalDocEntry"
LEFT JOIN delivery_check AS DC ON CD."DocEntry" = DC."DocEntry"
LEFT JOIN payment_check AS PC ON CD."DocEntry" = PC."DocEntry"
ORDER BY CD."DaysToCancellation" DESC, CD."DocTotal" DESC;
