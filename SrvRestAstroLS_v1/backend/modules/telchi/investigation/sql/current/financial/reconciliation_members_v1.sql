-- =============================================================================
-- RECONCILIATION MEMBERS — FINANCIAL-004
-- =============================================================================
-- Change ID: FINANCIAL-004
-- Motivation: Establish the reconciliation member details.
--   Grain: ReconNum + LineSeq (one row per member document)
--   Purpose: Which documents participate in each reconciliation
-- =============================================================================
-- Fields verified against HANA schema 2026-08-20:
--   ReconNum: links to OITR
--   LineSeq: line sequence within reconciliation
--   TransId: journal transaction ID
--   ShortName: business partner/account code
--   SrcObjTyp: source object type (13=Invoice, 14=Credit Note, 24=Payment, etc.)
--   SrcObjAbs: source object DocEntry
--   ReconSum: reconciliation amount (positive=debit, negative=credit)
--   ReconSumFC: reconciliation amount in foreign currency
--   ReconSumSC: reconciliation amount in system currency
--   IsCredit: credit indicator
--   Account: GL account code
-- =============================================================================
-- Grain: ReconNum + LineSeq
-- Note: ReconSum sign indicates direction (positive=what we receive, negative=what we give)
-- =============================================================================

SELECT
    ITR1."ReconNum",
    ITR1."LineSeq",
    ITR1."TransId",
    ITR1."TransRowId",
    ITR1."ShortName",
    ITR1."SrcObjTyp",
    ITR1."SrcObjAbs",
    ITR1."ReconSum",
    ITR1."ReconSumFC",
    ITR1."ReconSumSC",
    ITR1."SumMthCurr",
    ITR1."IsCredit",
    ITR1."Account",
    ITR1."CashDisSum",
    ITR1."InstID"
FROM TELCHI.ITR1 AS ITR1
INNER JOIN TELCHI.OITR AS OITR ON ITR1."ReconNum" = OITR."ReconNum"
WHERE OITR."ReconDate" >= :start_date
  AND OITR."ReconDate" < :end_date
