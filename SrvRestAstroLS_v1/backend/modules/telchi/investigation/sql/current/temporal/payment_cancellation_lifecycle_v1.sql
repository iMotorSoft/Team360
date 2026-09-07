-- =============================================================================
-- PAYMENT CANCELLATION LIFECYCLE — TEMPORAL-002
-- =============================================================================
-- Change ID: TEMPORAL-002
-- Motivation: Model payment cancellations with precise timing.
--   Grain: ORCT.DocEntry (one row per payment)
--   Purpose: Identify canceled payments and their impact on AR
-- =============================================================================
-- Key Finding: 10,689 payments are canceled (0.6% of total)
--   These must be excluded from valid collection analysis.
-- =============================================================================

SELECT
    ORCT."DocEntry",
    ORCT."DocNum",
    ORCT."CardCode",
    ORCT."DocDate",
    ORCT."DocTotal",
    ORCT."DocCurr",
    ORCT."Canceled",
    ORCT."TransId",
    ORCT."UpdateDate",
    ORCT."UpdateTS",

    -- Cancellation derivation
    CASE
        WHEN ORCT."Canceled" = 'Y' THEN ORCT."UpdateDate"
        ELSE NULL
    END AS "CancellationDate",

    CASE
        WHEN ORCT."Canceled" = 'Y' THEN ORCT."UpdateTS"
        ELSE NULL
    END AS "CancellationTimestamp",

    CASE
        WHEN ORCT."Canceled" = 'Y'
        THEN DAYS_BETWEEN(ORCT."DocDate", ORCT."UpdateDate")
        ELSE 0
    END AS "DaysToCancellation",

    -- Lifecycle classification
    CASE
        WHEN ORCT."Canceled" = 'N' THEN 'ACTIVE'
        WHEN ORCT."Canceled" = 'Y' THEN 'CANCELED'
        ELSE 'UNKNOWN'
    END AS "LifecycleStatus"

FROM TELCHI."ORCT" AS ORCT
WHERE ORCT."DocDate" >= :start_date
  AND ORCT."DocDate" < :end_date
ORDER BY ORCT."DocDate" DESC, ORCT."DocEntry"
