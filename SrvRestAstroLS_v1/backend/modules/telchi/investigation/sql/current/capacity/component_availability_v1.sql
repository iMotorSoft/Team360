-- =============================================================================
-- COMPONENT AVAILABILITY — TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1
-- =============================================================================
-- Change: TELCHI-CAP-001
-- Grain: OITW.ItemCode + OITW.WhsCode (BOM components only)
-- READ ONLY.
-- =============================================================================
-- AVAILABLE_COMPONENT_FOR_PRODUCTION (immediate):
--   OnHand - IsCommited restricted to RAW_MATERIAL role warehouses
--   (LAB-M1 Materia Prima, SAA-M1/MAG-M1 Granel Procesadora). Packaging and
--   inputs are stored there too. Other roles (PRODUCTION WIP, FINISHED_GOOD
--   LPZ-T1, DISPENSING, BRANCH, DAMAGED, QUARANTINE, MOBILE, TRANSIT) are
--   separate layers (in-process / distributed / transferable / unusable).
--   EQUIVALENT_IN_FG is NOT included (it is transformed material, not usable
--   for new production).
-- =============================================================================
SELECT
    T."ItemCode",
    T."WhsCode",
    T."OnHand",
    T."IsCommited",
    (T."OnHand" - T."IsCommited") AS "AvailableForProduction"
FROM TELCHI."OITW" T
JOIN (SELECT DISTINCT "Code" AS c FROM TELCHI."ITT1") B ON B.c = T."ItemCode"
WHERE T."WhsCode" IN ('LAB-M1', 'SAA-M1', 'MAG-M1')