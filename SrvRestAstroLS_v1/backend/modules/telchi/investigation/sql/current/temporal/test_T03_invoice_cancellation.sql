-- =============================================================================
-- TEST T03: INVOICE CANCELLATION — MARCH → JUNE SCENARIO
-- =============================================================================
-- Change ID: TEMPORAL-TEST-003
-- Motivation: Validate that a March invoice canceled in June is correctly
--   handled in both as-reported and restated views.
-- =============================================================================
-- Scenario:
--   1. Invoice F issued in March
--   2. As of March 31: F is included in sales
--   3. In June: F is canceled
--   4. Current restated view: F is excluded from valid March sales
--   5. Timeline: F shows CREATION in March, CANCELLATION in June
-- =============================================================================
-- This test is BLOCKING for temporal architecture validation.
-- =============================================================================

-- Step 1: Find a real case of March invoice canceled in June (or later)
-- We look for invoices with DocDate in March and UpdateDate in June+

WITH march_invoices AS (
    SELECT
        "DocEntry",
        "DocNum",
        "CardCode",
        "DocDate",
        "DocTotal",
        "CANCELED",
        "UpdateDate",
        "UpdateTS",
        "TransId"
    FROM TELCHI."OINV"
    WHERE "DocDate" >= '2026-03-01'
      AND "DocDate" < '2026-04-01'
),
-- Find those that were canceled AFTER March
canceled_later AS (
    SELECT
        MI.*,
        DAYS_BETWEEN(MI."DocDate", MI."UpdateDate") AS "DaysToCancel"
    FROM march_invoices AS MI
    WHERE MI."CANCELED" = 'Y'
      AND MI."UpdateDate" > '2026-03-31'
)
SELECT
    "DocEntry",
    "DocNum",
    "CardCode",
    "DocDate",
    "DocTotal",
    "UpdateDate" AS "CancellationDate",
    "UpdateTS" AS "CancellationTime",
    "DaysToCancel",
    "TransId"
FROM canceled_later
ORDER BY "DaysToCancel" DESC
LIMIT 10;

-- Step 2: For the found case, verify:
--   a) As of March 31: invoice was ACTIVE (not yet canceled)
--   b) As of today: invoice is CANCELED
--   c) Cancellation date is in June (or later)

-- Step 3: Verify the reversal document (C) exists and is linked
-- (This would be a Python test that queries both Y and C documents)

-- Step 4: Calculate what March sales WERE vs WHAT THEY ARE NOW
--   - AS-REPORTED (as of March 31): includes the invoice
--   - RESTATED (current): excludes the invoice
--   - The difference = the cancellation impact
