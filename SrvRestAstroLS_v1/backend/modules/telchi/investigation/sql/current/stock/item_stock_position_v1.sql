-- =============================================================================
-- ITEM STOCK POSITION — TELCHI_MATERIAL_STOCK_POSITION_V1
-- =============================================================================
-- Change: TELCHI-STOCK-003
-- Grain: OITW.ItemCode + OITW.WhsCode (one row per item x warehouse)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   OnHand   = physical stock (net ledger). EXACT vs OINM:
--              OITW.OnHand == SUM(OINM.InQty) - SUM(OINM.OutQty) over the full
--              OINM window (sample: L02475@LAB-M1 447,891 == 447,891).
--              0 negative OnHand; 32 locked rows.
--   IsCommited = committed to open sales/delivery documents (487,193 total).
--   OnOrder   = on open purchase orders (1,791,142 total) -> ordered, NOT
--               yet received (separate layer; do not sum to physical).
--   Consig    = consignment stock (78 rows; total negative -> anomaly flag).
--   AVAILABLE_PHYSICAL_STOCK = OnHand - IsCommited (SAP B1 semantics).
--   UOM (InvntryUom): UNI, FCO, COMP, PZA, TBO, CAPS, KG, AMP, SOB, BOLSA,
--     CAJA, ENV, TAB, LT, PQTE, GR, LATA, PAR, ML ... -> do NOT sum across
--     incompatible UOMs (invariant).
-- =============================================================================
SELECT
    T."ItemCode",
    T."WhsCode",
    T."OnHand",
    T."IsCommited",
    T."OnOrder",
    T."Consig",
    T."Counted",
    T."Locked",
    T."MinStock",
    T."MaxStock",
    T."AvgPrice",
    T."StockValue",
    I."ItemName",
    I."ItemType",
    I."ItmsGrpCod",
    I."InvntItem",
    I."SellItem",
    I."PrchseItem",
    I."InvntryUom",
    W."WhsName",
    W."U_TYPE",
    W."U_TIPO",
    W."Inactive"
FROM TELCHI."OITW" T
JOIN TELCHI."OITM" I ON I."ItemCode" = T."ItemCode"
JOIN TELCHI."OWHS" W ON W."WhsCode" = T."WhsCode"