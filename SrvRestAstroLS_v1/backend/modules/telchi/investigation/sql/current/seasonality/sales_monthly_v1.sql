-- =============================================================================
-- MONTHLY NET SALES — TELCHI_PRODUCT_SEASONALITY_V1
-- =============================================================================
-- Change: TELCHI-SEAS-001
-- Grain: (ItemCode, Year, Month) for sold items.
-- READ ONLY.
-- =============================================================================
-- Canonical demand source:
--   GROSS_UNITS  = SUM(INV1.Quantity) on non-canceled invoices (OINV)
--   RETURNED_UNITS = SUM(RIN1.Quantity) on non-canceled credit notes (ORIN)
--   NET_UNITS    = GROSS - RETURNED (credit notes = returns; DEC-R001 NetSales)
-- Zero-month filling is done in Python (a month with no row means 0, not
-- absence of the month).
-- =============================================================================
SELECT
    y."Year"  AS "Year",
    y."Month" AS "Month",
    y."ItemCode",
    y."GrossQty",
    COALESCE(n."ReturnedQty", 0) AS "ReturnedQty",
    y."GrossQty" - COALESCE(n."ReturnedQty", 0) AS "NetQty"
FROM (
    SELECT YEAR(H."DocDate") AS "Year", MONTH(H."DocDate") AS "Month",
           L."ItemCode", SUM(L."Quantity") AS "GrossQty"
    FROM TELCHI."OINV" H JOIN TELCHI."INV1" L ON L."DocEntry" = H."DocEntry"
    WHERE H."CANCELED" = 'N'
    GROUP BY YEAR(H."DocDate"), MONTH(H."DocDate"), L."ItemCode"
) y
LEFT JOIN (
    SELECT YEAR(H."DocDate") AS "Year", MONTH(H."DocDate") AS "Month",
           L."ItemCode", SUM(L."Quantity") AS "ReturnedQty"
    FROM TELCHI."ORIN" H JOIN TELCHI."RIN1" L ON L."DocEntry" = H."DocEntry"
    WHERE H."CANCELED" = 'N'
    GROUP BY YEAR(H."DocDate"), MONTH(H."DocDate"), L."ItemCode"
) n ON n."Year" = y."Year" AND n."Month" = y."Month" AND n."ItemCode" = y."ItemCode"