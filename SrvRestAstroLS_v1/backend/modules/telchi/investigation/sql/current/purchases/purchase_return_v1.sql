-- =============================================================================
-- PURCHASE RETURN (DEVOLUCIÓN A PROVEEDOR) — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-006
-- Grain: ORPD.DocEntry (header) + RPD1.DocEntry+LineNum (line)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - 3,907 returns (3,817 active; 45 Y + 45 C cancellation pairs)
--   - RPD1.BaseType: -1 = no base (4,220); 21 = based on purchase return (50);
--     20 = based on goods receipt (9)
--   - Returns are an adjustment path on the purchase side: they reduce the
--     net received quantity when validating coverage
-- =============================================================================
SELECT
    H."DocEntry",
    H."DocNum",
    H."CANCELED",
    H."DocStatus",
    H."DocDate",
    H."CreateDate",
    H."CardCode",
    H."CardName",
    H."DocCur",
    H."DocRate",
    H."DocTotal",
    L."LineNum",
    L."ItemCode",
    L."Dscription",
    L."Quantity",
    L."OpenQty",
    L."Price",
    L."LineTotal",
    L."BaseType",
    L."BaseEntry",
    L."BaseRef",
    L."BaseLine",
    L."BaseDocNum",
    L."WhsCode",
    L."U_LOTE",
    L."U_VENCLOTE"
FROM TELCHI."ORPD" H
JOIN TELCHI."RPD1" L ON L."DocEntry" = H."DocEntry"
WHERE H."CANCELED" = 'N'