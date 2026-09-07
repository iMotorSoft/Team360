-- =============================================================================
-- PRODUCTS — Properties Query (QryGroup expansion)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeProductPropiety
-- Tables: TELCHI.OITM, TELCHI.OITG
-- Purpose: Expand QryGroup1..64 into property codes/names
-- Grain: ItemCode (after aggregation)
-- =============================================================================
-- NOTE: This is executed as 64 separate queries in legacy (one per QryGroup).
-- The template below is for QryGroup{N} where N ranges from 1 to 64.
-- Each query returns items where that QryGroup = 'Y'.
-- =============================================================================

-- Template for N in 1..64:
SELECT
    OITM."ItemCode",
    OITM."ItemName",
    ({N}) AS "ItmsTypCod",
    (SELECT OITG."ItmsGrpNam"
     FROM TELCHI.OITG OITG
     WHERE OITG."ItmsTypCod" = {N}) AS "ItmsGrpNam"
FROM TELCHI.OITM OITM
WHERE OITM."QryGroup{N}" = 'Y'

-- =============================================================================
-- Example for QryGroup1:
-- =============================================================================
-- SELECT
--     OITM."ItemCode",
--     OITM."ItemName",
--     (1) AS "ItmsTypCod",
--     (SELECT OITG."ItmsGrpNam"
--      FROM TELCHI.OITG OITG
--      WHERE OITG."ItmsTypCod" = 1) AS "ItmsGrpNam"
-- FROM TELCHI.OITM OITM
-- WHERE OITM."QryGroup1" = 'Y'
