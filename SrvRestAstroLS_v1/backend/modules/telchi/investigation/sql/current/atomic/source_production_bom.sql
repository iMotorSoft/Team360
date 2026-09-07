-- =============================================================================
-- ATOMIC SOURCE — PRODUCTION BOM (P1) — OITT (headers) + ITT1 (components)
-- =============================================================================
-- BOM contract (spec §28-30). Grain: OITT.Code (bill of materials header),
-- ITT1.Code = component item, ITT1.Quantity = qty per unit.
-- Component functional classification is NOT inferred from description alone.
SELECT
    OITT."Code"        AS "bom_code",
    OITT."Name"        AS "bom_name",
    OITT."TreeType"    AS "tree_type",
    OITT."Qauntity"    AS "top_quantity",
    OITT."ToWH"        AS "bom_warehouse",
    OITT."CreateDate"  AS "valid_from",
    OITT."UpdateDate"  AS "valid_to",
    ITT1."ChildNum"    AS "component_seq",
    ITT1."Code"        AS "component_item",
    ITT1."ItemName"    AS "component_name",
    ITT1."Quantity"    AS "required_qty_per_unit",
    ITT1."Warehouse"   AS "component_warehouse",
    ITT1."Uom"         AS "uom",
    ITT1."Price"       AS "price"
FROM TELCHI.OITT AS OITT
LEFT JOIN TELCHI.ITT1 AS ITT1
       ON OITT."Code" = ITT1."Father"
WHERE OITT."UpdateDate" >= :start_date
  AND OITT."UpdateDate" < :end_date
-- =============================================================================