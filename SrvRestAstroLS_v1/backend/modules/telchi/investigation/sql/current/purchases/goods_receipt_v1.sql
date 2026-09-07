-- =============================================================================
-- GOODS RECEIPT PO (ENTRADA DE MERCADERÍA) — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-004
-- Grain: OPDN.DocEntry (header) + PDN1.DocEntry+LineNum (line)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - 19,633 receipts (19,025 active; 304 Y + 304 C cancellation pairs)
--   - PDN1.BaseType: 18 = based on AP invoice (87,577 lines, 100% linked to
--     OPCH via BaseEntry = OPCH.DocEntry); 20 = based on goods receipt PO
--     (2,232); 22 = directly based on PO (54); -1 = no base (104);
--     304 lines with other BaseTypes (production/transfer references)
--   - The operative receipt semantics for coverage is:
--       OPDN.DocDate, quantity = PDN1.Quantity (active, BaseType in
--       (18, 20, 22) or -1 documented)
--   - Receipt timing vs invoice: P50 = 1 day, P90 = 7 days
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
    H."DocCur",
    H."DocRate",
    H."DocTotal",
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
    L."FromWhsCod",
    L."U_LOTE",
    L."U_VENCLOTE"
FROM TELCHI."OPDN" H
JOIN TELCHI."PDN1" L ON L."DocEntry" = H."DocEntry"
WHERE H."CANCELED" = 'N'