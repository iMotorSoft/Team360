-- =============================================================================
-- CURRENT ACCOUNTS RECEIVABLE — FINANCIAL-005
-- =============================================================================
-- Change ID: FINANCIAL-005
-- Motivation: Calculate current AR with aging by invoice.
--   Grain: OINV.DocEntry (one row per invoice)
--   AS_OF_DATE: latest ReconDate in OITR
-- =============================================================================
-- Logic:
--   1. Get all active invoices (CANCELED = 'N', DocStatus = 'O')
--   2. Calculate settlement from ITR1 (SrcObjTyp=13 ReconSum)
--   3. Calculate outstanding = DocTotal - Settlement
--   4. Calculate days overdue = AS_OF_DATE - DocDueDate
--   5. Assign aging bucket
--   6. Classify financial status
-- =============================================================================
-- Aging Buckets:
--   NOT_DUE: DocDueDate >= AS_OF_DATE
--   1-30: 0 < days_overdue <= 30
--   31-60: 30 < days_overdue <= 60
--   61-90: 60 < days_overdue <= 90
--   91-120: 90 < days_overdue <= 120
--   120+: days_overdue > 120
-- =============================================================================

WITH as_of AS (
    -- Get the latest reconciliation date as AS_OF_DATE
    SELECT MAX("ReconDate") AS "AS_OF_DATE"
    FROM TELCHI."OITR"
),
invoice_settlement AS (
    -- Calculate total settlement per invoice from all reconciliations
    SELECT
        I."SrcObjAbs" AS "InvoiceDocEntry",
        SUM(I."ReconSum") AS "TotalSettlement",
        COUNT(DISTINCT I."ReconNum") AS "ReconCount"
    FROM TELCHI."ITR1" AS I
    INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
    WHERE I."SrcObjTyp" = 13  -- Invoice lines
      AND O."Canceled" = 'N'  -- Active reconciliations
    GROUP BY I."SrcObjAbs"
),
ar_calculation AS (
    -- Calculate outstanding and aging for each invoice
    SELECT
        OINV."DocEntry",
        OINV."DocNum",
        OINV."CardCode",
        OINV."SlpCode",
        OINV."DocDate",
        OINV."DocDueDate",
        OINV."DocTotal",
        OINV."DocCur",
        OINV."DocStatus",
        OINV."CANCELED",
        COALESCE(IS2."TotalSettlement", 0) AS "TotalSettlement",
        COALESCE(IS2."ReconCount", 0) AS "ReconCount",
        (OINV."DocTotal" - COALESCE(IS2."TotalSettlement", 0)) AS "Outstanding",
        CASE
            WHEN OINV."DocDueDate" >= (SELECT "AS_OF_DATE" FROM as_of) THEN 0
            ELSE DATEDIFF('DAY', OINV."DocDueDate", (SELECT "AS_OF_DATE" FROM as_of))
        END AS "DaysOverdue",
        (SELECT "AS_OF_DATE" FROM as_of) AS "AS_OF_DATE"
    FROM TELCHI."OINV"
    LEFT JOIN invoice_settlement AS IS2 ON OINV."DocEntry" = IS2."InvoiceDocEntry"
    WHERE OINV."CANCELED" = 'N'
      AND OINV."DocStatus" = 'O'
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
    "TotalSettlement",
    "ReconCount",
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
    END AS "FinancialStatus",
    -- Simple status for reporting
    CASE
        WHEN "Outstanding" <= -0.01 THEN 'SALDO_A_FAVOR'
        WHEN "Outstanding" <= 0.01 THEN 'PAGADA'
        WHEN "DaysOverdue" = 0 THEN 'PENDIENTE'
        ELSE 'VENCIDA'
    END AS "SimpleStatus"
FROM ar_calculation
ORDER BY "Outstanding" DESC
