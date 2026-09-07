-- =============================================================================
-- FG USABLE STOCK — TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1
-- =============================================================================
-- Change: TELCHI-COV-001
-- Grain: OITW.ItemCode + OITW.WhsCode (produced items with stock/commitment)
-- READ ONLY.
-- =============================================================================
-- Layer A: USABLE_FINISHED_GOODS.
--   FG universe = produced items (OWOR.Type='S'). Usability split by warehouse
--   role (Gate 2 taxonomy, resolved in Python): FINISHED_GOOD/BRANCH/
--   DISTRIBUTION/MOBILE/DISPENSING/CONSIGNMENT/RETURNS are usable for covering
--   future demand; DAMAGED/EXPIRED/QUARANTINE/PRODUCTION(WIP)/RAW/TRANSIT/
--   IMPORT/OTHER are kept separate (flagged).
--   USABLE_FG = SUM(OnHand - IsCommited) over usable roles (IsCommited is
--   already promised to open sales; it is NOT available to cover NEW demand).
--   EQUIVALENT_IN_FG is a DIFFERENT layer (material already transformed); this
--   query exposes only the physical FG units, never the equivalent.
-- =============================================================================
SELECT
    T."ItemCode",
    T."WhsCode",
    T."OnHand",
    T."IsCommited",
    I."InvntryUom",
    W."WhsName",
    W."U_TYPE",
    W."U_TIPO",
    W."Inactive"
FROM TELCHI."OITW" T
JOIN (SELECT DISTINCT "ItemCode" FROM TELCHI."OWOR" WHERE "Type" = 'S') P
    ON P."ItemCode" = T."ItemCode"
JOIN TELCHI."OITM" I ON I."ItemCode" = T."ItemCode"
JOIN TELCHI."OWHS" W ON W."WhsCode" = T."WhsCode"
WHERE T."OnHand" > 0 OR T."IsCommited" > 0
