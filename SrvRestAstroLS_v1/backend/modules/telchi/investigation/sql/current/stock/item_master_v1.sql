-- =============================================================================
-- ITEM MASTER (CLASIFICACIÓN) — TELCHI_MATERIAL_STOCK_POSITION_V1
-- =============================================================================
-- Change: TELCHI-STOCK-002
-- Grain: OITM.ItemCode (one row per item)
-- READ ONLY.
-- =============================================================================
-- Item classification evidence (resolved in Python domain):
--   - ItemType: I = item (16,792), F = fixed asset (1)
--   - InvntItem/SellItem/PrchseItem flags: 12,163 all-Y; 2,382 inv+sell;
--     1,354 inv+pur (materia prima/insumo); 765 inv-only; 75 pur-only
--   - ItmsGrpCod: 104 AGEMED MED (4,571), 100 Artículos (3,799),
--     111 INSUMOS HOSPT, 129 INSUMO, 130 MAT. ACONDICIONADO (envases),
--     131 MATERIAL LABORATORIO, 125-128 FRACCIONADO x Gr/Kg/L/mL (MP a granel),
--     119 IMPORTACION, 141 SERVICIOS, 144 ACTIVO FIJO
--   - U_PRODUCE: NA (15,167), LAB (763), MAG (499), SAA (364)
--   - produced = ItemCode in OWOR (Type='S') distinct set (896)
--   - BOM component = ItemCode in ITT1 (recetas)
--   - OITB.ItemClass / RawMtrl are NOT discriminating (all '2'/'N') ->
--     group name + production + BOM + flags are the operative evidence
-- =============================================================================
SELECT
    "ItemCode",
    "ItemName",
    "FrgnName",
    "ItemType",
    "ItmsGrpCod",
    "InvntItem",
    "SellItem",
    "PrchseItem",
    "InvntryUom",
    "BuyUnitMsr",
    "SalUnitMsr",
    "U_PRODUCE",
    "U_TYPE",
    "U_AREA",
    "U_LINEA",
    "U_GS_UM"
FROM TELCHI."OITM"
ORDER BY "ItemCode"