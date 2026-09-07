-- =============================================================================
-- SETTLEMENT AGGREGATION BY INVOICE — FINANCIAL-005
-- =============================================================================
-- Change ID: FINANCIAL-005
-- Motivation: Build per-invoice settlement from reconciliation data.
--   Grain: OINV.DocEntry (one row per invoice)
--   Purpose: Calculate total settlement per invoice by component type
-- =============================================================================
-- Logic:
--   1. Find all invoices (SrcObjTyp=13) in ITR1
--   2. For each invoice's ReconNum, find all OTHER members
--   3. Classify other members by SrcObjTyp
--   4. Aggregate settlement amounts by invoice and type
-- =============================================================================
-- Settlement Components:
--   PaymentSettlement: SrcObjTyp IN (24, 46) — incoming payments
--   CreditSettlement: SrcObjTyp = 14 — A/R credit memos
--   DownPaymentSettlement: SrcObjTyp = 25 — down payments received
--   JournalSettlement: SrcObjTyp = 30 — journal entries
--   OtherSettlement: everything else
-- =============================================================================
-- Note: ReconSum sign indicates direction.
--   For invoices (SrcObjTyp=13): negative = settled, positive = unsettled
--   For payments (SrcObjTyp=24): positive = amount applied
--   We use ABS() for aggregation to get absolute settlement amounts.
-- =============================================================================

WITH invoice_recons AS (
    -- Step 1: Find all invoices in reconciliations
    SELECT
        I."SrcObjAbs" AS "InvoiceDocEntry",
        I."ReconNum",
        I."ReconSum" AS "InvoiceReconSum",
        I."IsCredit" AS "InvoiceIsCredit"
    FROM TELCHI."ITR1" AS I
    INNER JOIN TELCHI."OITR" AS O ON I."ReconNum" = O."ReconNum"
    WHERE I."SrcObjTyp" = 13  -- A/R Invoice
      AND O."Canceled" = 'N'  -- Only active reconciliations
),
settlement_members AS (
    -- Step 2: Find all non-invoice members in those reconciliations
    SELECT
        IR."InvoiceDocEntry",
        IR."ReconNum",
        I."SrcObjTyp",
        I."SrcObjAbs",
        I."ReconSum",
        I."ReconSumFC",
        I."ReconSumSC",
        I."IsCredit",
        I."ShortName",
        I."Account"
    FROM invoice_recons AS IR
    INNER JOIN TELCHI."ITR1" AS I ON IR."ReconNum" = I."ReconNum"
    WHERE I."SrcObjTyp" != 13  -- Exclude invoice lines (we want settlement)
),
classified_settlements AS (
    -- Step 3: Classify settlement types
    SELECT
        "InvoiceDocEntry",
        "ReconNum",
        "SrcObjTyp",
        "SrcObjAbs",
        "ReconSum",
        "ReconSumFC",
        "ReconSumSC",
        "IsCredit",
        "ShortName",
        "Account",
        CASE
            WHEN "SrcObjTyp" IN (24, 46) THEN 'PAYMENT'
            WHEN "SrcObjTyp" = 14 THEN 'CREDIT_NOTE'
            WHEN "SrcObjTyp" = 25 THEN 'DOWN_PAYMENT'
            WHEN "SrcObjTyp" = 30 THEN 'JOURNAL'
            ELSE 'OTHER'
        END AS "SettlementType"
    FROM settlement_members
)
-- Step 4: Aggregate by invoice and settlement type
SELECT
    "InvoiceDocEntry",
    "SettlementType",
    COUNT(DISTINCT "ReconNum") AS "ReconCount",
    COUNT(*) AS "LineCount",
    SUM(ABS("ReconSum")) AS "TotalSettlement",
    SUM(ABS("ReconSumFC")) AS "TotalSettlementFC",
    SUM(ABS("ReconSumSC")) AS "TotalSettlementSC"
FROM classified_settlements
GROUP BY "InvoiceDocEntry", "SettlementType"
ORDER BY "InvoiceDocEntry", "SettlementType"
