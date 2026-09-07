-- =============================================================================
-- CANCELLATION AUDIT 04: CUSTOMER CONCENTRATION
-- =============================================================================
-- Purpose: Analyze which customers have the most cancelled invoices
-- Grain: OINV.CardCode (one row per customer)
-- =============================================================================

WITH cancellation_derivation AS (
    SELECT
        OINV."DocEntry",
        OINV."CardCode",
        OINV."CardName",
        OINV."DocTotal",
        OINV."CANCELED",
        OINV."UpdateDate" AS "CancellationDate",
        CASE
            WHEN OINV."CANCELED" = 'Y'
            THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
            ELSE NULL
        END AS "DaysToCancellation"
    FROM TELCHI."OINV" AS OINV
),
-- Total invoices per customer (all time)
customer_totals AS (
    SELECT
        "CardCode",
        COUNT(*) AS "TotalInvoices",
        SUM("DocTotal") AS "TotalDocTotal"
    FROM cancellation_derivation
    WHERE "CANCELED" = 'N'
    GROUP BY "CardCode"
),
-- Cancelled invoices per customer
customer_cancelled AS (
    SELECT
        "CardCode",
        "CardName",
        COUNT(*) AS "CancelledCount",
        SUM("DocTotal") AS "CancelledAmount",
        AVG("DocTotal") AS "AvgCancelledAmount",
        MAX("DocTotal") AS "MaxCancelledAmount",
        AVG("DaysToCancellation") AS "AvgDaysToCancel",
        SUM(CASE WHEN "DaysToCancellation" > 30 THEN 1 ELSE 0 END) AS "CancelledOver30Days"
    FROM cancellation_derivation
    WHERE "CANCELED" = 'Y'
    GROUP BY "CardCode", "CardName"
)
SELECT
    CC."CardCode",
    CC."CardName",
    CC."CancelledCount",
    CC."CancelledAmount",
    ROUND(CC."AvgCancelledAmount", 2) AS "AvgCancelledAmount",
    CC."MaxCancelledAmount",
    ROUND(CC."AvgDaysToCancel", 1) AS "AvgDaysToCancel",
    CC."CancelledOver30Days",

    -- Total invoices (for rate calculation)
    COALESCE(CT."TotalInvoices", 0) AS "TotalInvoices",
    COALESCE(CT."TotalDocTotal", 0) AS "TotalDocTotal",

    -- Rates
    ROUND(CC."CancelledCount" * 100.0 / NULLIF(COALESCE(CT."TotalInvoices", 0), 0), 2) AS "CancellationRatePct",
    ROUND(CC."CancelledAmount" * 100.0 / NULLIF(COALESCE(CT."TotalDocTotal", 0), 0), 2) AS "MonetaryRatePct"

FROM customer_cancelled AS CC
LEFT JOIN customer_totals AS CT ON CC."CardCode" = CT."CardCode"
ORDER BY CC."CancelledCount" DESC
LIMIT 50;
