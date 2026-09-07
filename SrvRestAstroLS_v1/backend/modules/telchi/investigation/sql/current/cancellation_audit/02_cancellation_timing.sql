-- =============================================================================
-- CANCELLATION AUDIT 02: TIMING DISTRIBUTION
-- =============================================================================
-- Purpose: Classify cancelled invoices by days to cancellation
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
        OINV."UpdateTS" AS "CancellationTimestamp",
        CASE
            WHEN OINV."CANCELED" = 'Y'
            THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
            ELSE NULL
        END AS "DaysToCancellation"
    FROM TELCHI."OINV" AS OINV
    WHERE OINV."CANCELED" = 'Y'
),
timing_buckets AS (
    SELECT
        *,
        CASE
            WHEN "DaysToCancellation" = 0 THEN '00_same_day'
            WHEN "DaysToCancellation" BETWEEN 1 AND 7 THEN '01_1_7'
            WHEN "DaysToCancellation" BETWEEN 8 AND 15 THEN '02_8_15'
            WHEN "DaysToCancellation" BETWEEN 16 AND 30 THEN '03_16_30'
            WHEN "DaysToCancellation" BETWEEN 31 AND 60 THEN '04_31_60'
            WHEN "DaysToCancellation" BETWEEN 61 AND 90 THEN '05_61_90'
            WHEN "DaysToCancellation" BETWEEN 91 AND 120 THEN '06_91_120'
            WHEN "DaysToCancellation" > 120 THEN '07_120_plus'
            ELSE '99_unknown'
        END AS "TimingBucket",

        -- Main classification
        CASE
            WHEN "DaysToCancellation" <= 30 THEN '≤30_days'
            WHEN "DaysToCancellation" > 30 THEN '>30_days'
            ELSE 'unknown'
        END AS "MainTimingClass"

    FROM cancellation_derivation
)
SELECT
    "TimingBucket",
    "MainTimingClass",
    COUNT(*) AS "InvoiceCount",
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS "PctCount",
    SUM("DocTotal") AS "TotalAmount",
    ROUND(AVG("DocTotal"), 2) AS "AvgAmount",
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY "DocTotal"), 2) AS "MedianAmount",
    MIN("DaysToCancellation") AS "MinDays",
    MAX("DaysToCancellation") AS "MaxDays"
FROM timing_buckets
GROUP BY "TimingBucket", "MainTimingClass"
ORDER BY "TimingBucket";
