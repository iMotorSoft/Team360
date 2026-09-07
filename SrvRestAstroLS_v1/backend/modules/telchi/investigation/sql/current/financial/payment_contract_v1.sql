-- =============================================================================
-- PAYMENT CONTRACT — FINANCIAL-003
-- =============================================================================
-- Change ID: FINANCIAL-003
-- Motivation: Establish the payment document contract with SAP traceability.
--   Grain: ORCT.DocEntry (one row per payment, header level)
--   Purpose: Payment lifecycle, cancellation, financial impact
-- Impact: New SQL. No modification to existing queries.
-- =============================================================================
-- Fields verified against HANA schema 2026-08-20:
--   DocEntry, DocNum, CardCode, CardName: SAP identifiers
--   DocDate, TaxDate, DocDueDate: date dimensions
--   DocTotal: payment total
--   DocCurr: document currency (NOT DocCur)
--   Canceled: cancellation flag
--   TransId: journal transaction ID
--   CashSum, CheckSum, TrsfrSum, CreditSum: payment method components
-- =============================================================================
-- Grain: 1 row per DocEntry (header level)
-- Note: ORCT uses DocCurr (not DocCur) for currency
-- =============================================================================

SELECT
    ORCT."DocEntry",
    ORCT."DocNum",
    ORCT."CardCode" AS "ClientCode",
    ORCT."CardName" AS "ClientName",
    ORCT."DocDate",
    ORCT."TaxDate",
    ORCT."DocTotal",
    ORCT."DocCurr",
    ORCT."DocRate",
    ORCT."DocTotalFC",
    ORCT."DocTotalSy",
    ORCT."Canceled",
    ORCT."TransId",
    ORCT."CashSum",
    ORCT."CheckSum",
    ORCT."TrsfrSum",
    ORCT."CreditSum",
    ORCT."Comments",
    ORCT."JrnlMemo",
    ORCT."UpdateDate",
    ORCT."Ref1"
FROM TELCHI.ORCT AS ORCT
WHERE ORCT."DocDate" >= :start_date
  AND ORCT."DocDate" < :end_date
