-- =============================================================================
-- PURCHASE ORDER LINE — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-002
-- Grain: POR1.DocEntry + POR1.LineNum (one row per purchase order line)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - 97,350 lines / 10,378 distinct ItemCode / 18,663 orders
--   - OpenQty: 0 = fully received/closed (97,079); == Quantity = fully open
--     (943); no partial-open lines observed (OpenQty strictly between 0 and
--     Quantity = 0). LineStatus mirrors it: C = closed, O = open
--   - BaseType: -1 = no base (95,913); 1470000113 = base PRQ (1,260, linked
--     via BaseEntry = OPRQ.DocEntry); 540000006 = base quotation (177)
--   - U_DOCIMPORT: 'S' = standard (97,318), 'Y' = import doc (21), 'N' (11)
--   - U_PERMIMPORT: 'Si' = import permission (96,075), 'NO' (6), null (1,269)
--   - WhsCode = warehouse receiving; FromWhsCod = source warehouse (usually
--     empty on purchase lines)
--   - U_LOTE / U_VENCLOTE: batch + expiry when the line manages batches
-- =============================================================================
SELECT
    L."DocEntry",
    L."LineNum",
    L."LineStatus",
    L."ItemCode",
    L."Dscription",
    L."Quantity",
    L."OpenQty",
    L."Price",
    L."PriceBefDi",
    L."LineTotal",
    L."TotalFrgn",
    L."BaseType",
    L."BaseEntry",
    L."BaseRef",
    L."BaseLine",
    L."BaseDocNum",
    L."WhsCode",
    L."FromWhsCod",
    L."TaxCode",
    L."VatPrcnt",
    L."U_LOTE",
    L."U_VENCLOTE",
    L."U_DOCIMPORT",
    L."U_PERMIMPORT",
    L."U_PRECIOLIST",
    L."U_COSTO",
    L."U_DESCLIN",
    L."U_PBRUTO"
FROM TELCHI."POR1" L
JOIN TELCHI."OPOR" H ON H."DocEntry" = L."DocEntry"
WHERE H."CANCELED" = 'N'