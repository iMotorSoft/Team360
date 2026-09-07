-- =============================================================================
-- PRODUCTS — BOM / ToWH (Latest Warehouse)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeProduct (inline query for dfItemToWH)
-- Tables: TELCHI.OITT
-- Purpose: Get most recent ToWH (target warehouse) per product from BOM
-- Uses ROW_NUMBER() to pick latest by UpdateDate DESC
-- =============================================================================

SELECT
    "ItemCode",
    "ToWH"
FROM (
    SELECT
        "OITT"."Code" AS "ItemCode",
        "OITT"."UpdateDate",
        "OITT"."ToWH",
        ROW_NUMBER() OVER (
            PARTITION BY "OITT"."Code"
            ORDER BY "OITT"."UpdateDate" DESC
        ) AS rn
    FROM "TELCHI"."OITT" "OITT"
) AS subquery
WHERE rn = 1
