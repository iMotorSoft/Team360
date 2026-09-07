-- =============================================================================
-- PRODUCTION OUTPUT (HISTORICAL) — TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1
-- =============================================================================
-- Change: TELCHI-EQUIV-003
-- Grain: FG ItemCode (produced)
-- READ ONLY.
-- =============================================================================
-- produced[fg] = SUM(IGN1.Quantity) where IGN1.ItemCode = OWOR.ItemCode
-- (rework lines where IGN1.ItemCode != OWOR.ItemCode are excluded from the
-- FG output; they are a different received item).
-- =============================================================================
SELECT
    O."ItemCode"     AS fg,
    SUM(I."Quantity") AS produced
FROM TELCHI."IGN1" I
JOIN TELCHI."OWOR" O ON O."DocEntry" = I."BaseEntry"
WHERE I."BaseType" = 202 AND I."ItemCode" = O."ItemCode"
GROUP BY O."ItemCode"