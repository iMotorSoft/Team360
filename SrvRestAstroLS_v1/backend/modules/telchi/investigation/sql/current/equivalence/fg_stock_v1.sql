-- =============================================================================
-- FINISHED GOOD STOCK — TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1
-- =============================================================================
-- Change: TELCHI-EQUIV-001
-- Grain: OITW.ItemCode + OITW.WhsCode (produced items only)
-- READ ONLY.
-- =============================================================================
-- FG universe = produced items (OWOR.Type='S'); 896 items, 656 with OnHand>0.
-- Warehouse role from the Gate 2 taxonomy (validation/stock/stock_domain.py).
-- Usability split: FINISHED_GOOD/BRANCH/DISTRIBUTION/MOBILE/DISPENSING/
--   CONSIGNMENT/RETURNS = usable; DAMAGED/EXPIRED/QUARANTINE/PRODUCTION(WIP)/
--   RAW/TRANSIT/IMPORT/OTHER = non-usable (kept separate, flagged).
-- =============================================================================
SELECT
    T."ItemCode",
    T."WhsCode",
    T."OnHand",
    T."IsCommited",
    I."InvntryUom" AS "FGUom",
    W."WhsName"
FROM TELCHI."OITW" T
JOIN (SELECT DISTINCT "ItemCode" FROM TELCHI."OWOR" WHERE "Type" = 'S') P
    ON P."ItemCode" = T."ItemCode"
JOIN TELCHI."OITM" I ON I."ItemCode" = T."ItemCode"
JOIN TELCHI."OWHS" W ON W."WhsCode" = T."WhsCode"
WHERE T."OnHand" > 0