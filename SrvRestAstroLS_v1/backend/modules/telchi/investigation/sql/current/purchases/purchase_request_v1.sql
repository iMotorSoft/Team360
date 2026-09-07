-- =============================================================================
-- PURCHASE REQUEST — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-005
-- Grain: OPRQ.DocEntry (header) + PRQ1.DocEntry+LineNum (line)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - 732 requests (717 active; 15 'Y' canceled; DocStatus 1 open)
--   - U_SOLCOMPRA (link to the original solicitud): NOT OPERATIVE (0 fill)
--   - PRQ1.BaseType: -1 = no base (3,166); 1470000113 = request base (5)
--   - POR1.BaseType = 1470000113 links purchase order lines to PRQ lines
--     (1,260 lines / 699 orders)
--   - Requests are a minor path: the operative purchase is PO-driven
-- =============================================================================
SELECT
    H."DocEntry",
    H."DocNum",
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
    L."WhsCode"
FROM TELCHI."OPRQ" H
JOIN TELCHI."PRQ1" L ON L."DocEntry" = H."DocEntry"
WHERE H."CANCELED" = 'N'