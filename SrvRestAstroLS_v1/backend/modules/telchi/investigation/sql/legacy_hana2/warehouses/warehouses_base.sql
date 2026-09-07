-- =============================================================================
-- WAREHOUSES — Legacy HANA2 Base Query (Item Warehouse)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeWhareHouse
--         sapb1Tools01.py::makeWhareHouse (identical)
-- Tables: TELCHI.OITW
-- SAP Object: OITW (Item Warehouse)
-- Grain: ItemCode + WhsCode (composite key)
-- SAP Identifiers: ItemCode, WhsCode
-- =============================================================================
-- NOTES:
--   - fillna on createDate/updateDate is ineffective (no assignment)
--   - No date filter — full table scan
-- =============================================================================

SELECT
    OITW."ItemCode",
    OITW."WhsCode",
    OITW."OnHand",
    OITW."IsCommited",
    OITW."OnOrder",
    OITW."MinStock",
    OITW."MaxStock",
    OITW."AvgPrice",
    OITW."createDate",
    OITW."updateDate",
    OITW."userSign2",
    OITW."RevenuesAc",
    OITW."StockValue",
    OITW."WipAcct"
FROM TELCHI.OITW OITW
