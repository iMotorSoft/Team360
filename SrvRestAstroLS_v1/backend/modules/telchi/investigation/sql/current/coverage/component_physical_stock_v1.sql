-- =============================================================================
-- COMPONENT PHYSICAL STOCK — TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1
-- =============================================================================
-- Change: TELCHI-COV-002
-- Grain: OITW.ItemCode + OITW.WhsCode (BOM components in raw warehouses)
-- READ ONLY.
-- =============================================================================
-- Layer B: PHYSICAL_COMPONENT_STOCK (available for production).
--   AVAILABLE = OnHand - IsCommited restricted to RAW_MATERIAL role warehouses
--   (LAB-M1 Materia Prima, SAA-M1/MAG-M1 Granel). OnOrder is exposed ONLY for
--   reconciliation against OPEN_PURCHASE_POSITION (never summed into physical).
--   EQUIVALENT_IN_FG is computed in Python (Gate 3); never part of this layer.
-- =============================================================================
SELECT
    T."ItemCode",
    T."WhsCode",
    T."OnHand",
    T."IsCommited",
    T."OnOrder"
FROM TELCHI."OITW" T
JOIN (SELECT DISTINCT "Code" AS c FROM TELCHI."ITT1") B ON B.c = T."ItemCode"
WHERE T."WhsCode" IN ('LAB-M1', 'SAA-M1', 'MAG-M1')
