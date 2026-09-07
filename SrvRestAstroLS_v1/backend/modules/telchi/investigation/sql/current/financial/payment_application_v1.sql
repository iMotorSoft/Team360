-- =============================================================================
-- PAYMENT APPLICATION — FINANCIAL-003
-- =============================================================================
-- Change ID: FINANCIAL-003
-- Motivation: Establish payment-to-document linkage via RCT2.
--   Grain: RCT2 line level (payment + target document)
--   Purpose: How payments are applied to invoices/credit notes
-- =============================================================================
-- Key Relationships:
--   RCT2.DocEntry = ORCT.DocEntry (payment header)
--   RCT2.InvType = 13 → target is A/R Invoice (OINV)
--   RCT2.InvType = 14 → target is A/R Credit Memo (ORIN)
--   RCT2.InvType = 46 → target is A/R Down Payment
-- =============================================================================
-- Grain: DocEntry + InvoiceId + InvType (may not be unique for on-account)
-- Note: InvoiceId=0 with baseAbs=DocEntry indicates on-account payment
-- =============================================================================

SELECT
    RCT2."DocEntry" AS "PaymentDocEntry",
    RCT2."InvoiceId",
    RCT2."InvType",
    RCT2."SumApplied",
    RCT2."AppliedFC",
    RCT2."AppliedSys",
    RCT2."DocRate",
    RCT2."baseAbs",
    RCT2."DocSubType",
    ORCT."DocDate" AS "PaymentDate",
    ORCT."Canceled" AS "PaymentCanceled",
    ORCT."CardCode" AS "ClientCode",
    ORCT."DocTotal" AS "PaymentDocTotal",
    ORCT."DocCurr" AS "PaymentCurrency"
FROM TELCHI.RCT2 AS RCT2
INNER JOIN TELCHI.ORCT AS ORCT ON RCT2."DocEntry" = ORCT."DocEntry"
WHERE ORCT."DocDate" >= :start_date
  AND ORCT."DocDate" < :end_date
