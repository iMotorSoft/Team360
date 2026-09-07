-- =============================================================================
-- CANCELLATION AUDIT 07: PAYMENT LINKAGE
-- =============================================================================
-- Purpose: Determine if cancelled invoices had payment effects
-- Grain: OINV.DocEntry (one row per cancelled invoice)
-- =============================================================================

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
        OINV."PaidToDate",
        OINV."UpdateDate" AS "CancellationDate",
        CASE
            WHEN OINV."CANCELED" = 'Y'
            THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
            ELSE NULL
        END AS "DaysToCancellation"
    FROM TELCHI."OINV" AS OINV
    WHERE OINV."CANCELED" = 'Y'
),
-- Check for reconciliation entries (payments applied to invoices)
payment_check AS (
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
        CD."PaidToDate",

        -- Check reconciliation entries
        COALESCE((SELECT SUM(ABS(ITR1."ReconSum"))
         FROM TELCHI."ITR1" AS ITR1
         INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
         WHERE ITR1."SrcObjAbs" = CD."DocEntry"
           AND ITR1."SrcObjTyp" = 13
           AND OITR."Canceled" = 'N'), 0) AS "ActiveReconciliationAmount",

        -- Check if there are any reconciliation entries at all
        (SELECT COUNT(*)
         FROM TELCHI."ITR1" AS ITR1
         INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
         WHERE ITR1."SrcObjAbs" = CD."DocEntry"
           AND ITR1."SrcObjTyp" = 13) AS "TotalReconciliationCount",

        -- Check if any payments are cancelled
        (SELECT COUNT(*)
         FROM TELCHI."ITR1" AS ITR1
         INNER JOIN TELCHI."OITR" AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
         WHERE ITR1."SrcObjAbs" = CD."DocEntry"
           AND ITR1."SrcObjTyp" = 13
           AND OITR."Canceled" = 'Y') AS "CancelledReconciliationCount"

    FROM cancellation_derivation AS CD
)
SELECT
    *,
    CASE
        WHEN "PaidToDate" > 0 AND "ActiveReconciliationAmount" > 0 THEN 'PAYMENT_ACTIVE'
        WHEN "PaidToDate" > 0 AND "ActiveReconciliationAmount" = 0 AND "CancelledReconciliationCount" > 0 THEN 'PAYMENT_CANCELLED'
        WHEN "PaidToDate" > 0 AND "ActiveReconciliationAmount" = 0 THEN 'PAID_NO_ACTIVE_RECON'
        WHEN "PaidToDate" = 0 AND "TotalReconciliationCount" > 0 THEN 'RECON_EXISTS_BUT_ZERO_PAID'
        ELSE 'NO_PAYMENT'
    END AS "PaymentStatus"
FROM payment_check
ORDER BY "InvoiceAmount" DESC
LIMIT 100;
