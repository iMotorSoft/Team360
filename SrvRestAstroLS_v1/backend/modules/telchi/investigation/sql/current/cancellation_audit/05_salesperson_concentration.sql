-- =============================================================================
-- CANCELLATION AUDIT 05: SALESPERSON CONCENTRATION
-- =============================================================================
-- Purpose: Analyze which salespersons have the most cancelled invoices
-- Grain: OINV.SlpCode (one row per salesperson)
-- =============================================================================

WITH cancellation_derivation AS (
    SELECT
        OINV."DocEntry",
        OINV."SlpCode",
        (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP WHERE OINV."SlpCode" = OSLP."SlpCode") AS "SellerName",
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
-- Total invoices per salesperson (all time)
seller_totals AS (
    SELECT
        "SlpCode",
        COUNT(*) AS "TotalInvoices",
        SUM("DocTotal") AS "TotalDocTotal"
    FROM cancellation_derivation
    WHERE "CANCELED" = 'N'
    GROUP BY "SlpCode"
),
-- Cancelled invoices per salesperson
seller_cancelled AS (
    SELECT
        "SlpCode",
        MAX("SellerName") AS "SellerName",
        COUNT(*) AS "CancelledCount",
        SUM("DocTotal") AS "CancelledAmount",
        AVG("DocTotal") AS "AvgCancelledAmount",
        MAX("DocTotal") AS "MaxCancelledAmount",
        AVG("DaysToCancellation") AS "AvgDaysToCancel",
        SUM(CASE WHEN "DaysToCancellation" > 30 THEN 1 ELSE 0 END) AS "CancelledOver30Days"
    FROM cancellation_derivation
    WHERE "CANCELED" = 'Y'
    GROUP BY "SlpCode"
)
SELECT
    SC."SlpCode",
    SC."SellerName",
    SC."CancelledCount",
    SC."CancelledAmount",
    ROUND(SC."AvgCancelledAmount", 2) AS "AvgCancelledAmount",
    SC."MaxCancelledAmount",
    ROUND(SC."AvgDaysToCancel", 1) AS "AvgDaysToCancel",
    SC."CancelledOver30Days",

    -- Total invoices (for rate calculation)
    COALESCE(ST."TotalInvoices", 0) AS "TotalInvoices",
    COALESCE(ST."TotalDocTotal", 0) AS "TotalDocTotal",

    -- Rates
    ROUND(SC."CancelledCount" * 100.0 / NULLIF(COALESCE(ST."TotalInvoices", 0), 0), 2) AS "CancellationRatePct",
    ROUND(SC."CancelledAmount" * 100.0 / NULLIF(COALESCE(ST."TotalDocTotal", 0), 0), 2) AS "MonetaryRatePct"

FROM seller_cancelled AS SC
LEFT JOIN seller_totals AS ST ON SC."SlpCode" = ST."SlpCode"
ORDER BY SC."CancelledCount" DESC
LIMIT 50;
