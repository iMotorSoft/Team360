-- =============================================================================
-- FG COMPONENT REQUIREMENT (HISTORICAL) — TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1
-- =============================================================================
-- Change: TELCHI-CAP-002
-- Grain: (FG ItemCode, Component ItemCode)
-- READ ONLY.
-- =============================================================================
-- requirement per FG unit = SUM(IGE1.Quantity) / SUM(IGN1.Quantity) per
-- (FG, component) over real orders. Same HISTORICAL_PRODUCTION_RATIO as
-- Gate 3. Direct components (raw + semi). Terminal expansion is done in the
-- domain (validation/capacity/capacity_domain.py) for multi-level BOM.
-- =============================================================================
SELECT
    O."ItemCode"       AS fg,
    C."ItemCode"       AS component,
    SUM(C."Quantity")  AS consumed,
    (SELECT SUM(I."Quantity") FROM TELCHI."IGN1" I
      WHERE I."BaseType"=202 AND I."BaseEntry"=O."DocEntry"
        AND I."ItemCode"=O."ItemCode") AS produced
FROM TELCHI."IGE1" C
JOIN TELCHI."OWOR" O ON O."DocEntry" = C."BaseEntry"
WHERE C."BaseType" = 202
GROUP BY O."DocEntry", O."ItemCode", C."ItemCode"