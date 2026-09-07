-- =============================================================================
-- CUSTOMERS — Properties Query (QryGroup expansion)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeClientPropiety
-- Tables: TELCHI.OCRD, TELCHI.OCQG
-- Purpose: Expand QryGroup1..64 into customer group codes/names
-- Grain: CardCode (after aggregation)
-- =============================================================================
-- Template for N in 1..64:
-- =============================================================================

SELECT
    OCRD."CardCode" AS "ClientCode",
    ({N}) AS "ClientGroupCode",
    (SELECT OCQG."GroupName"
     FROM telchi.OCQG OCQG
     WHERE OCQG."GroupCode" = {N}) AS "ClientGroupName"
FROM telchi.OCRD AS OCRD
WHERE OCRD."QryGroup{N}" = 'Y'
