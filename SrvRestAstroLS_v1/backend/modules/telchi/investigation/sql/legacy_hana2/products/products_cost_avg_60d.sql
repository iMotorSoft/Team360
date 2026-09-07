-- =============================================================================
-- PRODUCTS — Cost Average Query (60-day window)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeProduct (inline query)
-- Tables: TELCHI.OINM
-- Purpose: Average cost per item over last 60 days
-- Decision: 60-day window is a historical decision, not to be changed
-- =============================================================================

SELECT
    "ItemCode",
    AVG("CalcPrice") AS "CostoUAvg60"
FROM TELCHI."OINM"
WHERE "DocDate" >= ADD_DAYS(CURRENT_DATE, -60)
GROUP BY "ItemCode"
