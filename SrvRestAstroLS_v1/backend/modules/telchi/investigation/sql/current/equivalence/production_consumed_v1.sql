-- =============================================================================
-- PRODUCTION COMPONENT RATIO (HISTORICAL) — TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1
-- =============================================================================
-- Change: TELCHI-EQUIV-002
-- Grain: (FG ItemCode, Component ItemCode)
-- READ ONLY.
-- =============================================================================
-- HISTORICAL_PRODUCTION_EQUIVALENCE:
--   qty_per_fg = SUM(IGE1.Quantity) / SUM(IGN1.Quantity) per (FG, component)
--   - IGE1: component consumption (BaseType=202, BaseEntry=OWOR.DocEntry)
--   - IGN1: FG output (BaseType=202, ItemCode=OWOR.ItemCode)
--   Reflects actual consumed / actual produced (yield, waste, drift).
-- =============================================================================
SELECT
    O."ItemCode"     AS fg,
    C."ItemCode"     AS component,
    SUM(C."Quantity") AS consumed
FROM TELCHI."IGE1" C
JOIN TELCHI."OWOR" O ON O."DocEntry" = C."BaseEntry"
WHERE C."BaseType" = 202
GROUP BY O."ItemCode", C."ItemCode"