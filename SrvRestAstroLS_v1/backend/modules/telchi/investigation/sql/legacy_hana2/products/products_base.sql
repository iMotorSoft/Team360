-- =============================================================================
-- PRODUCTS — Legacy HANA2 Base Query
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeProduct
--         sapb1Tools01.py::makeProduct (identical)
-- Tables: TELCHI.OITM, TELCHI.OITB (subquery), TELCHI.OMRC (subquery)
-- SAP Object: OITM (Item Master)
-- Grain: ItemCode
-- SAP Identifiers: ItemCode, ItmsGrpCod, FirmCode, U_CODACTIVE
-- =============================================================================
-- KNOWN ISSUES:
--   1. Python accesses 'u_produce' (lowercase) but SQL selects 'U_PRODUCE'
--      — CASE MISMATCH BUG (LEGACY_BUG_U_PRODUCE_CASE)
--   2. assign_value() function derives ItemUN from first letter of ItemCode
--   3. FormaFarmac mapping is done in Python, not SQL
-- =============================================================================

SELECT
    OITM."ItemCode",
    OITM."ItemName",
    OITM."U_CODACTIVE",
    OITM."U_PRODUCE",
    OITM."LastPurPrc",
    OITM."LastPurCur",
    OITM."LastPurDat",
    OITM."OnHand",
    OITM."ItmsGrpCod",
    (SELECT OITB."ItmsGrpNam"
     FROM TELCHI.OITB AS OITB
     WHERE OITM."ItmsGrpCod" = OITB."ItmsGrpCod") AS "Grupo",
    OITM."InvntryUom",
    OITM."FirmCode",
    (SELECT OMRC."FirmName"
     FROM TELCHI.OMRC AS OMRC
     WHERE OITM."FirmCode" = OMRC."FirmCode") AS "Linea",
    OITM."frozenFor",
    OITM."U_FormaFarmac",
    OITM."U_SUBGRUPO" AS "SubGrupo"
FROM TELCHI.OITM AS OITM
