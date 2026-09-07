-- =============================================================================
-- CURRENT BOM (FALLBACK) — TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1
-- =============================================================================
-- Change: TELCHI-EQUIV-004
-- Grain: (Father = FG ItemCode, Code = Component ItemCode)
-- READ ONLY.
-- =============================================================================
-- CURRENT_BOM_EQUIVALENCE (fallback when no production history):
--   qty_per_fg = ITT1.Quantity / OITT.Qauntity (batch-normalized).
--   ITT1.Uom is NULL -> component qty is in the component's own inventory
--   UOM (OITM.InvntryUom). OITT.Qauntity is the SAP column name (typo).
-- =============================================================================
SELECT
    B."Father"     AS fg,
    B."Code"       AS component,
    B."Quantity"   AS component_qty,
    H."Qauntity"   AS batch_qty
FROM TELCHI."ITT1" B
JOIN TELCHI."OITT" H ON H."Code" = B."Father"