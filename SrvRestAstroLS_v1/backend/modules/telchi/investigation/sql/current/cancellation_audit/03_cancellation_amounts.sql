-- =============================================================================
-- CANCELLATION AUDIT 03: AMOUNT DISTRIBUTION
-- =============================================================================
-- Purpose: Analyze the monetary distribution of cancelled invoices
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
        OINV."UpdateDate" AS "CancellationDate",
        CASE
            WHEN OINV."CANCELED" = 'Y'
            THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
            ELSE NULL
        END AS "DaysToCancellation"
    FROM TELCHI."OINV" AS OINV
    WHERE OINV."CANCELED" = 'Y'
),
-- Calculate percentiles for dynamic buckets
percentiles AS (
    SELECT
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "DocTotal") AS p25,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY "DocTotal") AS p50,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "DocTotal") AS p75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY "DocTotal") AS p90,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY "DocTotal") AS p95,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY "DocTotal") AS p99
    FROM cancellation_derivation
),
amount_buckets AS (
    SELECT
        CD.*,
        P.p25, P.p50, P.p75, P.p90, P.p95, P.p99,
        CASE
            WHEN CD."DocTotal" <= P.p25 THEN '01_lowest_25pct'
            WHEN CD."DocTotal" <= P.p50 THEN '02_p25_p50'
            WHEN CD."DocTotal" <= P.p75 THEN '03_p50_p75'
            WHEN CD."DocTotal" <= P.p90 THEN '04_p75_p90'
            WHEN CD."DocTotal" <= P.p95 THEN '05_p90_p95'
            WHEN CD."DocTotal" <= P.p99 THEN '06_p95_p99'
            ELSE '07_above_p99'
        END AS "AmountBucket"
    FROM cancellation_derivation AS CD
    CROSS JOIN percentiles AS P
)
SELECT
    "AmountBucket",
    COUNT(*) AS "InvoiceCount",
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS "PctCount",
    SUM("DocTotal") AS "TotalAmount",
    ROUND(SUM("DocTotal") * 100.0 / SUM(SUM("DocTotal")) OVER (), 2) AS "PctAmount",
    ROUND(AVG("DocTotal"), 2) AS "AvgAmount",
    MIN("DocTotal") AS "MinAmount",
    MAX("DocTotal") AS "MaxAmount",
    ROUND(AVG("DaysToCancellation"), 1) AS "AvgDaysToCancel"
FROM amount_buckets
GROUP BY "AmountBucket"
ORDER BY "AmountBucket";
