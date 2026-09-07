-- =============================================================================
-- CUSTOMERS — Legacy HANA2 Base Query
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeClient
-- Tables: TELCHI.OCRD, TELCHI.OPLN (subquery)
-- SAP Object: OCRD (Business Partner)
-- Grain: CardCode
-- SAP Identifiers: CardCode (aliased as ClientCode)
-- =============================================================================
-- NOTES:
--   - Includes ListNum and PriceListName lookup
--   - Properties (QryGroup1..64) are in separate function makeClientPropiety
--   - Legacy has 'except e:' bug — bare except with variable
-- =============================================================================

SELECT
    OCRD."CardCode" AS "ClientCode",
    OCRD."CardName" AS "ClientName",
    OCRD."CardType" AS "ClientType",
    OCRD."GroupCode" AS "ClientGroupCode",
    OCRD."City" AS "ClientCity",
    OCRD."ListNum",
    (SELECT OPLN."ListName"
     FROM TELCHI.OPLN OPLN
     WHERE OPLN."ListNum" = OCRD."ListNum") AS "PriceListName"
FROM TELCHI.OCRD OCRD
