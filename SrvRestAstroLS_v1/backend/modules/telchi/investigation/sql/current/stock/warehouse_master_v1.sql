-- =============================================================================
-- WAREHOUSE MASTER — TELCHI_MATERIAL_STOCK_POSITION_V1
-- =============================================================================
-- Change: TELCHI-STOCK-001
-- Grain: OWHS.WhsCode (one row per warehouse)
-- READ ONLY.
-- =============================================================================
-- 82 warehouses. Warehouse function is resolved in the Python domain
-- (validation/stock/stock_domain.py) using: name + U_TYPE (SAP vs DMS) +
-- U_TIPO (01=import vs 03=regular) + Inactive + production/transfer evidence.
-- This SQL exposes the raw evidence columns needed by that classifier.
-- =============================================================================
SELECT
    "WhsCode",
    "WhsName",
    "U_TYPE",
    "U_TIPO",
    "Locked",
    "Inactive",
    "DropShip",
    "U_WAREHOUSE_DMS",
    "U_SO1_01SUCURSAL"
FROM TELCHI."OWHS"
ORDER BY "WhsCode"