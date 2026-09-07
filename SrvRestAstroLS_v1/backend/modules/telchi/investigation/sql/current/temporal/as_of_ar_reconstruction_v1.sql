-- =============================================================================
-- AS-OF ACCOUNTS RECEIVABLE RECONSTRUCTION — TEMPORAL-003
-- =============================================================================
-- Change ID: TEMPORAL-003
-- Motivation: Reconstruct AR position at any historical date.
--   Grain: OINV.DocEntry (one row per invoice)
--   Purpose: Enable aging_as_of(fecha) for temporal analysis
-- =============================================================================
-- Critical: This uses ONLY information available at AS_OF_DATE.
--   - Invoices with DocDate <= AS_OF_DATE
--   - Payments with DocDate <= AS_OF_DATE
--   - Reconciliations with ReconDate <= AS_OF_DATE
--   - Cancellations with CancellationDate <= AS_OF_DATE
-- =============================================================================
-- This prevents data leakage from future events.
-- =============================================================================

WITH as_of_params AS (
    SELECT :as_of_date AS "AS_OF_DATE"
),
-- Invoices active as of date (created before, not canceled before)
active_invoices AS (
    SELECT
        OINV."DocEntry",
        OINV."DocNum",
        OINV."CardCode",
        OINV."SlpCode",
        OINV."DocDate",
        OINV."DocDueDate",
        OINV."DocTotal",
        OINV."DocCur",
        OINV."CANCELED",
        OINV."UpdateDate" AS "CancellationDate",
        CASE
            WHEN OINV."CANCELED" = 'Y'
                 AND OINV."UpdateDate" <= (SELECT "AS_OF_DATE" FROM as_of_params)
            THEN 'CANCELED_AS_OF'
            WHEN OINV."CANCELED" = 'N'
            THEN 'ACTIVE'
            WHEN OINV."CANCELED" = 'Y'
                 AND OINV."UpdateDate" > (SELECT "AS_OF_DATE" FROM as_of_params)
            THEN 'ACTIVE_NOT_YET_CANCELED'
            ELSE 'UNKNOWN'
        END AS "StatusAsOf"
    FROM TELCHI."OINV" AS OINV
    WHERE OINV."DocDate" <= (SELECT "AS_OF_DATE" FROM as_of_params)
),
-- Settlement as of date (reconciliations processed before date)
settlement_as_of AS (
    SELECT
        I."SrcObjAbs" AS "InvoiceDocEntry",
        SUM(I."ReconSum") AS "TotalSettlement"
    FROM TELCHI."ITR1" AS I
    INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
    WHERE I."SrcObjTyp" = 13
      AND O."Canceled" = 'N'
      AND O."ReconDate" <= (SELECT "AS_OF_DATE" FROM as_of_params)
    GROUP BY I."SrcObjAbs"
),
-- Calculate outstanding as of date
ar_as_of AS (
    SELECT
        AI."DocEntry",
        AI."DocNum",
        AI."CardCode",
        AI."SlpCode",
        AI."DocDate",
        AI."DocDueDate",
        AI."DocTotal",
        AI."DocCur",
        AI."StatusAsOf",
        AI."CancellationDate",
        COALESCE(SA."TotalSettlement", 0) AS "TotalSettlement",
        (AI."DocTotal" - COALESCE(SA."TotalSettlement", 0)) AS "Outstanding",
        CASE
            WHEN AI."DocDueDate" >= (SELECT "AS_OF_DATE" FROM as_of_params) THEN 0
            ELSE DAYS_BETWEEN(AI."DocDueDate", (SELECT "AS_OF_DATE" FROM as_of_params))
        END AS "DaysOverdue",
        (SELECT "AS_OF_DATE" FROM as_of_params) AS "AS_OF_DATE"
    FROM active_invoices AS AI
    LEFT JOIN settlement_as_of AS SA ON AI."DocEntry" = SA."InvoiceDocEntry"
    WHERE AI."StatusAsOf" IN ('ACTIVE', 'ACTIVE_NOT_YET_CANCELED')
)
SELECT
    "DocEntry",
    "DocNum",
    "CardCode",
    "SlpCode",
    "DocDate",
    "DocDueDate",
    "DocTotal",
    "DocCur",
    "StatusAsOf",
    "CancellationDate",
    "TotalSettlement",
    "Outstanding",
    "DaysOverdue",
    "AS_OF_DATE",

    -- Aging bucket
    CASE
        WHEN "Outstanding" <= 0.01 THEN 'SETTLED'
        WHEN "DaysOverdue" = 0 THEN 'NOT_DUE'
        WHEN "DaysOverdue" <= 30 THEN '1-30'
        WHEN "DaysOverdue" <= 60 THEN '31-60'
        WHEN "DaysOverdue" <= 90 THEN '61-90'
        WHEN "DaysOverdue" <= 120 THEN '91-120'
        ELSE '120+'
    END AS "AgingBucket",

    -- Financial status
    CASE
        WHEN "Outstanding" <= -0.01 THEN 'CREDIT_BALANCE'
        WHEN "Outstanding" <= 0.01 THEN 'SETTLED'
        WHEN "DaysOverdue" = 0 THEN 'OPEN_NOT_DUE'
        ELSE 'OVERDUE'
    END AS "FinancialStatus"

FROM ar_as_of
WHERE "Outstanding" > 0.01  -- Only show invoices with positive outstanding
ORDER BY "Outstanding" DESC
