-- =============================================================================
-- AP INVOICE (FACTURA PROVEEDOR) — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-003
-- Grain: OPCH.DocEntry (header) + PCH1.DocEntry+LineNum (line)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - 32,131 invoices (29,827 active; 1,152 Y + 1,152 C cancellation pairs)
--   - PCH1.BaseType: 22 = based on purchase order (90,959 lines, 100% linked
--     to OPOR via BaseEntry = OPOR.DocEntry); -1 = no base (17,215 lines,
--     direct invoices, mostly expense/service lines with Quantity=0); 18 =
--     based on another AP invoice (5,668)
--   - Operative flow: OPOR -> OPCH (invoice first) -> OPDN (goods receipt)
--   - DocCur: BS (31,771) / USD (360)
--   - LineStatus O/C is NOT a useful open indicator on invoices (102,382 'O'
--     on active invoices); use PCH1.BaseType + chain linkage instead
-- =============================================================================
SELECT
    H."DocEntry",
    H."DocNum",
    H."ObjType",
    H."CANCELED",
    H."DocStatus",
    H."DocDate",
    H."DocDueDate",
    H."CreateDate",
    H."CardCode",
    H."CardName",
    H."NumAtCard",
    H."DocCur",
    H."DocRate",
    H."DocTotal",
    H."DocTotalFC",
    H."DocTotalSy",
    H."VatSum",
    H."U_TIPOCOMPRA",
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
FROM TELCHI."OPCH" H
JOIN TELCHI."PCH1" L ON L."DocEntry" = H."DocEntry"
WHERE H."CANCELED" = 'N'