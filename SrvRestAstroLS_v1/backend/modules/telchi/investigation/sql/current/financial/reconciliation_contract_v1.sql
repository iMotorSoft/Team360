-- =============================================================================
-- RECONCILIATION CONTRACT — FINANCIAL-004
-- =============================================================================
-- Change ID: FINANCIAL-004
-- Motivation: Establish the reconciliation/settlement contract.
--   Grain: OITR.ReconNum (one row per reconciliation)
--   Purpose: Settlement layer that links payments to invoices
-- =============================================================================
-- Fields verified against HANA schema 2026-08-20:
--   ReconNum: reconciliation identifier
--   ReconDate: reconciliation date
--   Total: total amount
--   ReconCurr: reconciliation currency
--   Canceled: N=active, C=canceled, Y=canceled
--   CancelAbs: references reversal reconciliation
--   IsCard, ReconType, IsSystem: classification fields
--   UserSign: user who created
-- =============================================================================
-- Grain: 1 row per ReconNum
-- Note: Canceled=N is active, C and Y are canceled
-- =============================================================================

SELECT
    OITR."ReconNum",
    OITR."ReconDate",
    OITR."Total",
    OITR."ReconCurr",
    OITR."Canceled",
    OITR."CancelAbs",
    OITR."IsCard",
    OITR."ReconType",
    OITR."IsSystem",
    OITR."IsMultiBP",
    OITR."IsElectr",
    OITR."InitObjTyp",
    OITR."CreateDate",
    OITR."CreateTime",
    OITR."UserSign",
    OITR."ObjType",
    OITR."CreateTS",
    OITR."UpdateTS"
FROM TELCHI.OITR AS OITR
WHERE OITR."ReconDate" >= :start_date
  AND OITR."ReconDate" < :end_date
