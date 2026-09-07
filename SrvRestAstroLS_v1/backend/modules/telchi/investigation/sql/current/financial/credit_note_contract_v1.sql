-- =============================================================================
-- CREDIT NOTE CONTRACT — FINANCIAL-002
-- =============================================================================
-- Change ID: FINANCIAL-002
-- Motivation: Establish the credit note financial contract with SAP traceability.
--   Grain: ORIN.DocEntry (one row per credit note, header level)
--   Purpose: Credit note lifecycle, linkage to invoices, financial impact
-- Impact: New SQL. No modification to existing queries.
-- Regression: Independent of existing sales/credit_notes/payments queries.
-- =============================================================================
-- Fields verified against HANA schema 2026-08-20:
--   DocEntry, DocNum, CardCode, SlpCode: SAP identifiers
--   DocDate, DocDueDate: date dimensions
--   DocTotal: credit note total (POSITIVE in SAP, legacy negates)
--   DocStatus: document status
--   CANCELED: cancellation flag (N=no, Y=yes, C=canceled)
--   TransId: journal transaction ID
--   PaidSum, PaidToDate: payment fields
--   DocCur: document currency
--   DocRate, DocTotalFC, SysRate: currency fields
--   DiscSum, VatSum, WTSum: tax/discount fields
-- =============================================================================
-- Grain: 1 row per DocEntry (header level)
-- Sign: DocTotal is POSITIVE in SAP. Legacy negates for net sales calc.
-- =============================================================================

SELECT
    ORIN."DocEntry",
    ORIN."DocNum",
    ORIN."CardCode",
    ORIN."CardName",
    ORIN."SlpCode",
    (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP
     WHERE ORIN."SlpCode" = OSLP."SlpCode") AS "SellerName",
    ORIN."DocDate",
    ORIN."DocDueDate",
    ORIN."DocTotal",
    ORIN."DocStatus",
    ORIN."CANCELED",
    ORIN."TransId",
    ORIN."PaidSum",
    ORIN."PaidToDate",
    ORIN."DocCur",
    ORIN."DocRate",
    ORIN."DocTotalFC",
    ORIN."SysRate",
    ORIN."DiscSum",
    ORIN."VatSum",
    ORIN."WTSum",
    ORIN."UpdateDate",
    ORIN."NumAtCard"
FROM TELCHI.ORIN AS ORIN
WHERE ORIN."DocDate" >= :start_date
  AND ORIN."DocDate" < :end_date
