-- =============================================================================
-- CANCELLATION AUDIT 01: TOTAL UNIVERSE OF CANCELLED INVOICES
-- =============================================================================
-- Purpose: Determine the complete universe of cancelled invoices
-- Grain: OINV.DocEntry (one row per invoice)
-- =============================================================================

WITH cancellation_derivation AS (
    SELECT
        OINV."DocEntry",
        OINV."DocNum",
        OINV."CardCode",
        OINV."CardName",
        OINV."SlpCode",
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
        CASE
            WHEN OINV."CANCELED" = 'Y' THEN OINV."UpdateDate"
            ELSE NULL
        END AS "CancellationDate",

        CASE
            WHEN OINV."CANCELED" = 'Y'
            THEN DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate")
            ELSE NULL
        END AS "DaysToCancellation"

    FROM TELCHI."OINV" AS OINV
)
SELECT
    -- Universe totals
    COUNT(*) AS "TotalInvoices",
    SUM(CASE WHEN "CANCELED" = 'N' THEN 1 ELSE 0 END) AS "ActiveInvoices",
    SUM(CASE WHEN "CANCELED" = 'Y' THEN 1 ELSE 0 END) AS "CanceledOriginal",
    SUM(CASE WHEN "CANCELED" = 'C' THEN 1 ELSE 0 END) AS "CanceledReversal",
    SUM(CASE WHEN "CANCELED" IN ('Y', 'C') THEN 1 ELSE 0 END) AS "TotalCanceled",

    -- Amount totals
    SUM("DocTotal") AS "TotalDocTotal",
    SUM(CASE WHEN "CANCELED" = 'N' THEN "DocTotal" ELSE 0 END) AS "ActiveDocTotal",
    SUM(CASE WHEN "CANCELED" = 'Y' THEN "DocTotal" ELSE 0 END) AS "CanceledDocTotal",

    -- Cancellation rate
    ROUND(SUM(CASE WHEN "CANCELED" IN ('Y', 'C') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4) AS "CancellationRatePct",
    ROUND(SUM(CASE WHEN "CANCELED" = 'Y' THEN "DocTotal" ELSE 0 END) * 100.0 / SUM("DocTotal"), 4) AS "MonetaryCancellationRatePct"

FROM cancellation_derivation;
