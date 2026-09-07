-- =============================================================================
-- RECONCILIATION — Legacy HANA2 Base Query
-- =============================================================================
-- Source: sapb1Tools01.py::makeReconRange
-- Tables: TELCHI.OITR, TELCHI.ITR1, TELCHI.OUSR (subquery)
-- SAP Object: OITR (Reconciliation)
-- Grain: ReconNum + ITR1 line (ReconNum + LineSeq)
-- SAP Identifiers: ReconNum, TransId, TransRowId, SrcObjAbs, CancelAbs
-- Date Filter: OITR.ReconDate
-- =============================================================================
-- NOTES:
--   - Canceled field is preserved
--   - CancelAbs indicates reversal reconciliation
--   - Inner join OITR-ITR1 means only reconciliations with lines
-- =============================================================================

SELECT
    OITR."ReconNum",
    OITR."IsCard",
    OITR."ReconType",
    OITR."ReconDate",
    OITR."Total",
    OITR."ReconCurr",
    OITR."Canceled",
    OITR."CancelAbs",
    OITR."IsSystem",
    OITR."InitObjTyp",
    OITR."CreateDate",
    OITR."CreateTime",
    OITR."UserSign",
    (SELECT OUSR."USER_CODE"
     FROM TELCHI."OUSR" OUSR
     WHERE OUSR."USERID" = OITR."UserSign") AS "OUSR-USER_CODE",
    OITR."IsMultiBP",
    OITR."IsElectr",
    OITR."CreateTS",
    OITR."UpdateTS",
    OITR."ObjType",
    ITR1."ReconNum" AS "ITR1-ReconNum",
    ITR1."LineSeq",
    ITR1."ShortName",
    ITR1."TransId",
    ITR1."TransRowId",
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
FROM TELCHI.OITR AS OITR
INNER JOIN TELCHI.ITR1 AS ITR1
    ON ITR1."ReconNum" = OITR."ReconNum"
WHERE OITR."ReconDate" >= :start_date
  AND OITR."ReconDate" <= :end_date || ' 23:59:59'
